from sqlite3 import connect
import time
from pandas import DataFrame
from colorama import Fore, Style
from setup_database import initialize_mongodb_client, close_mongodb_client


def buffer_to_db(persistent_buffer, sqlite_db_path, config, max_retries=5, initial_delay=0.5):
    """
    Inserts data into the SQLite3 database.
    """
    attempt = 0
    delay = initial_delay

    while attempt < max_retries:
        try:
            # Conexión a SQLite3
            conn = connect(sqlite_db_path)
            cursor = conn.cursor()

            # Activar WAL
            cursor.execute("PRAGMA journal_mode=WAL;")

            # Crear DataFrame para manejar los datos
            df = DataFrame(persistent_buffer)

            if config["debug"]:
                print(f"5) Data passing through the database: {len(df)} records per sensor.")

            # Obtener timestamps únicos e insertar en `timestamps`
            timestamps = df['time'].unique()
            cursor.executemany("INSERT OR IGNORE INTO timestamps (timestamp) VALUES (?)", [(ts,) for ts in timestamps])
            conn.commit()

            # Generar mapeo de timestamps con sus IDs
            timestamp_ids = {
                ts: cursor.execute("SELECT id FROM timestamps WHERE timestamp = ?", (ts,)).fetchone()[0]
                for ts in timestamps
            }

            # Generar mapeo de sensores con sus IDs
            sensor_ids = {
                col: cursor.execute("SELECT id FROM sensors WHERE sensor_number = ?", (col,)).fetchone()[0]
                for col in df.columns if col != 'time'
            }

            # Preparar datos para insertar en `accelerations`
            sensor_data = []
            for index, row in df.iterrows():
                timestamp = row['time']
                timestamp_id = timestamp_ids[timestamp]
                for col in df.columns:
                    if col != 'time':  # Ignorar la columna de tiempo
                        sensor_number = col
                        sensor_id = sensor_ids[sensor_number]
                        sensor_data.append((timestamp_id, sensor_id, row[col]))

            # Insertar los datos en la tabla `accelerations`
            cursor.executemany(
                "INSERT INTO accelerations (timestamp_id, sensor_id, acceleration_value) VALUES (?, ?, ?)",
                sensor_data
            )
            conn.commit()  # Confirmar las transacciones
            conn.close()

            persistent_buffer.clear()

            if config["debug"]:
                print(f"6) Buffer to SQLite3 successful. {len(sensor_data)} accelerations inserted.")
            break

        except Exception as e:
            print(f"Error: {e}")
            attempt += 1
            if attempt < max_retries:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2
            else:
                print("Maximum attempts reached. Data could not be saved.")
            break

        finally:
            if 'conn' in locals() and conn:
                conn.close()

def backup_data(db_config, sqlite_db_path, raw_db, config, sensor_numbers, stop_event, backup_time, persistent_buffer, total_capture_time):
    """
    Performs a backup of all data from the SQLite3 database (buffer) to the MongoDB (raw) database.
    Processes data in batches based on timestamps and correctly deletes processed records.
    """

    if backup_time == 0:
        
        print(Fore.RED + "The backup time is 0. No backups to MongoDB will be performed." + Style.RESET_ALL)
        return

    client = initialize_mongodb_client(db_config)  # Conexión a MongoDB
    if not client:
        config['backup_time'] = 0  # Disable backups if MongoDB is unavailable
        print(Fore.RED + "MongoDB Server is unavailable, backups are disabled." + Style.RESET_ALL)
        return

    raw_collection = client[raw_db]['accelerations']
    max_timestamps_per_batch = 20000  # Procesar por número de timestamps
    delete_in_progress = False

    while not stop_event.is_set() or delete_in_progress:
        start_time = time.time()  # Registrar el tiempo inicial para cada respaldo

        if config["debug"]:
            print(Fore.GREEN + "----------------------------------------------Starting backup process..." + Style.RESET_ALL)

        try:
            # Conectar a la base de datos SQLite3 (buffer)
            conn = connect(sqlite_db_path)
            cursor = conn.cursor()

            # Activar WAL
            cursor.execute("PRAGMA journal_mode=WAL;")

            # Obtener todos los timestamps únicos ordenados
            cursor.execute("""
                SELECT DISTINCT t.id, t.timestamp 
                FROM timestamps t 
                JOIN accelerations a ON t.id = a.timestamp_id 
                ORDER BY t.timestamp ASC
            """)
            all_timestamps = cursor.fetchall()

            if all_timestamps:
                total_timestamps = len(all_timestamps)
                if config["debug"]:
                    print(Fore.YELLOW + f"Found {total_timestamps} timestamps in SQLite3. Processing in batches of up to {max_timestamps_per_batch} timestamps." + Style.RESET_ALL)

                total_backed_up = 0
                delete_in_progress = True  # Marcar que la eliminación está en progreso

                # Procesar todos los registros en lotes
                for i in range(0, total_timestamps, max_timestamps_per_batch):
                    timestamp_batch = all_timestamps[i:i + max_timestamps_per_batch]

                    bulk_insert = []

                    for timestamp_row in timestamp_batch:
                        timestamp_id, timestamp = timestamp_row

                        # Obtener todas las aceleraciones asociadas al timestamp actual
                        cursor.execute("""
                            SELECT a.sensor_id, a.acceleration_value
                            FROM accelerations a
                            WHERE a.timestamp_id = ?
                        """, (timestamp_id,))
                        acceleration_data = cursor.fetchall()

                        sensor_data = [
                            {"sensor_id": str(sensor_id), "acceleration": acceleration_value}
                            for sensor_id, acceleration_value in acceleration_data
                        ]

                        # Verificar si el timestamp ya existe en MongoDB
                        existing_doc = raw_collection.find_one({"timestamp": timestamp})
                        if existing_doc:
                            # Fusionar datos si ya existe
                            updated_sensor_data = existing_doc["sensor_data"] + sensor_data
                            raw_collection.update_one(
                                {"_id": existing_doc["_id"]},
                                {"$set": {"sensor_data": updated_sensor_data}}
                            )
                        else:
                            # Insertar un nuevo documento
                            bulk_insert.append({
                                "timestamp": timestamp,
                                "sensor_data": sensor_data
                            })

                    # Insertar todos los nuevos documentos en MongoDB
                    if bulk_insert:
                        raw_collection.insert_many(bulk_insert, ordered=False)

                    # Eliminar los datos procesados del buffer SQLite
                    timestamp_ids = [(row[0],) for row in timestamp_batch]
                    cursor.executemany("DELETE FROM timestamps WHERE id = ?", timestamp_ids)
                    cursor.execute("""
                        DELETE FROM accelerations
                        WHERE timestamp_id NOT IN (
                            SELECT id FROM timestamps
                        )
                    """)
                    conn.commit()

                    total_backed_up += len(timestamp_batch)

                    if config["debug"]:
                        print(Fore.CYAN + f"Batch backup completed ({len(timestamp_batch)} timestamps processed)." + Style.RESET_ALL)

                delete_in_progress = False  # Marcar que la eliminación ha sido completada

                if config["debug"]:
                    print(Fore.YELLOW + f"Backup completed. {total_backed_up} timestamps transferred in {time.time() - start_time:.5f} seconds." + Style.RESET_ALL)

            else:
                if config["debug"]:
                    print(Fore.GREEN + "No new data in the buffer database to back up." + Style.RESET_ALL)

            # Calcular el tiempo restante y ajustarlo para asegurar que el ciclo toma el tiempo exacto.
            process_duration = time.time() - start_time
            remaining_time = max(0, backup_time - process_duration)  # Asegurar que no sea negativo
            time.sleep(remaining_time)

        except Exception as e:
            print(Fore.RED + f"Error during data backup: {e}" + Style.RESET_ALL)

        finally:
            conn.close()  # Cerrar la conexión a SQLite3

    # Si se ha activado el evento de parada, asegurarse de que el proceso de respaldo finalice correctamente
    if stop_event.is_set() and delete_in_progress:
        print(Fore.YELLOW + "Stop requested, completing ongoing backup..." + Style.RESET_ALL)
        try:
            conn = connect(sqlite_db_path)
            cursor = conn.cursor()

            # Activar WAL
            cursor.execute("PRAGMA journal_mode=WAL;")

            # Procesar cualquier dato restante
            cursor.execute("""
                SELECT DISTINCT t.id, t.timestamp 
                FROM timestamps t 
                JOIN accelerations a ON t.id = a.timestamp_id 
                ORDER BY t.timestamp ASC
            """)
            timestamp_batch = cursor.fetchall()

            while timestamp_batch:
                bulk_insert = []

                for timestamp_row in timestamp_batch:
                    timestamp_id, timestamp = timestamp_row

                    # Obtener todas las aceleraciones asociadas al timestamp actual
                    cursor.execute("""
                        SELECT a.sensor_id, a.acceleration_value
                        FROM accelerations a
                        WHERE a.timestamp_id = ?
                    """, (timestamp_id,))
                    acceleration_data = cursor.fetchall()

                    sensor_data = [
                        {"sensor_id": str(sensor_id), "acceleration": acceleration_value}
                        for sensor_id, acceleration_value in acceleration_data
                    ]

                    # Verificar si el timestamp ya existe en MongoDB
                    existing_doc = raw_collection.find_one({"timestamp": timestamp})
                    if existing_doc:
                        # Fusionar datos si ya existe
                        updated_sensor_data = existing_doc["sensor_data"] + sensor_data
                        raw_collection.update_one(
                            {"_id": existing_doc["_id"]},
                            {"$set": {"sensor_data": updated_sensor_data}}
                        )
                    else:
                        # Insertar un nuevo documento
                        bulk_insert.append({
                            "timestamp": timestamp,
                            "sensor_data": sensor_data
                        })

                # Insertar todos los nuevos documentos en MongoDB
                if bulk_insert:
                    raw_collection.insert_many(bulk_insert, ordered=False)

                # Eliminar los datos procesados del buffer SQLite
                timestamp_ids = [(row[0],) for row in timestamp_batch]
                cursor.executemany("DELETE FROM timestamps WHERE id = ?", timestamp_ids)
                cursor.execute("""
                    DELETE FROM accelerations
                    WHERE timestamp_id NOT IN (
                        SELECT id FROM timestamps
                    )
                """)
                conn.commit()

                cursor.execute("""
                    SELECT DISTINCT t.id, t.timestamp 
                    FROM timestamps t 
                    JOIN accelerations a ON t.id = a.timestamp_id 
                    ORDER BY t.timestamp ASC
                """)
                timestamp_batch = cursor.fetchall()

            print(Fore.GREEN + "Final backup completed. Buffer completely cleared." + Style.RESET_ALL)

        except Exception as e:
            print(Fore.RED + f"Error during data backup: {e}" + Style.RESET_ALL)

        finally:
            conn.close()

    close_mongodb_client()
    print(Fore.RED + "**The backup process has been stopped successfully.**" + Style.RESET_ALL)



    if persistent_buffer:  # Respaldar cualquier dato restante en el buffer
        buffer_to_db(persistent_buffer, sqlite_db_path, config)  # Usar SQLite3 como buffer

    if total_capture_time == 0:
        print(Fore.GREEN + "Continuous capture. Press ENTER to stop."+ Style.RESET_ALL)
    else:
        print(Fore.RED + "DATA CAPTURE COMPLETED. Press ENTER to finnish."+ Style.RESET_ALL)

    stop_event.set()
