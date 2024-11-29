""" 
Codigo para capturar datos de N sensores de aceleración utilizando un dispositivo NI cDAQ9185 con módulos NI 9230.

El código captura datos de aceleración de N sensores en un intervalo de tiempo especificado y los guarda en un buffer definido por el usuario de acuerdo a la capacidad del DAQ 
y lo vuelca en una base de datos MongoDB y su respectivo timestamp UNIX. 
El código también permite detener la captura de datos manualmente presionando ENTER.
Utiliza multiprocessing para captura y procesamiento de datos en paralelo. 
El procesamiento de los datos no solo decima los datos sino que también los redondea a 5 decimales y agrega el timestamp UNIX.
Python 3.10.9

"""
from nidaqmx import Task
from nidaqmx.constants import AcquisitionType, AccelUnits, AccelSensitivityUnits
from pandas import DataFrame
from numpy import array
from pymongo import MongoClient, errors
from sqlite3 import connect
import time
from os import stat, mkdir
from multiprocessing import Process, Queue, Event
import queue
from colorama import Fore, Style

# Crear cliente persistente para MongoDB
mongo_client = None

def initialize_mongodb_client(db_config):
    """
    Initializes the MongoDB client if not already initialized.
    Handles connection errors and returns None if MongoDB is unavailable.
    """
    global mongo_client
    if mongo_client is None:
        try:
            # Create the MongoDB client with a 5-second timeout
            mongo_client = MongoClient(db_config['db_host'], db_config['db_port'], serverSelectionTimeoutMS=5000)
            
            # Test the connection by pinging the server
            mongo_client.admin.command('ping')
        except errors.ServerSelectionTimeoutError:
            print("Error: Cannot connect to MongoDB. Backups will be disabled.")
            mongo_client = None  # Ensure the client remains None if connection fails
    return mongo_client

def close_mongodb_client():
    """Cierra el cliente MongoDB si está abierto."""
    global mongo_client
    if mongo_client is not None:
        mongo_client.close()
        mongo_client = None  # Resetear para asegurarnos de que se puede reinicializar más adelante

def buffer_to_db(persistent_buffer, sqlite_db_path, config, max_retries=5, initial_delay=0.5):
    """
    Inserta datos en la base de datos SQLite3.
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
                print(f"5) Datos pasando por la base de datos: {len(df)} registros por sensor.")

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
                print(f"6) Buffer a SQLite3 exitoso. {len(sensor_data)} aceleraciones insertadas.")
            break

        except Exception as e:
            print(f"Error: {e}")
            attempt += 1
            if attempt < max_retries:
                print(f"Reintentando en {delay} segundos...")
                time.sleep(delay)
                delay *= 2
            else:
                print("Se alcanzó el máximo de intentos. No se pudieron guardar los datos.")
            break

        finally:
            if 'conn' in locals() and conn:
                conn.close()



def backup_data(db_config, sqlite_db_path, raw_db, config, sensor_numbers, stop_event, backup_time):
    """
    Realiza el respaldo de todos los datos de la base de datos SQLite3 (buffer) a la base de datos MongoDB (raw).
    Procesa en lotes basados en timestamps y elimina los datos correctamente.
    """

    if backup_time == 0:
        
        print(Fore.RED + "El tiempo de respaldo es 0. No se realizarán respaldos a MongoDB." + Style.RESET_ALL)
        return

    client = initialize_mongodb_client(db_config)  # Conexión a MongoDB
    if not client:
        config['backup_time'] = 0  # Disable backups if MongoDB is unavailable
        print(Fore.RED + "MongoDB Server no se encuentra, los respaldos están desactivados." + Style.RESET_ALL)
        return

    raw_collection = client[raw_db]['accelerations']
    max_timestamps_per_batch = 20000  # Procesar por número de timestamps
    delete_in_progress = False

    while not stop_event.is_set() or delete_in_progress:
        start_time = time.time()  # Registrar el tiempo inicial para cada respaldo

        if config["debug"]:
            print(Fore.GREEN + "----------------------------------------------Iniciando proceso de respaldo..." + Style.RESET_ALL)

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
                    print(Fore.YELLOW + f"Se encontraron {total_timestamps} timestamps en SQLite3. Procesando en lotes de máximo {max_timestamps_per_batch} timestamps." + Style.RESET_ALL)

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
                        print(Fore.CYAN + f"Respaldo de lote completado ({len(timestamp_batch)} timestamps procesados)." + Style.RESET_ALL)

                delete_in_progress = False  # Marcar que la eliminación ha sido completada

                if config["debug"]:
                    print(Fore.YELLOW + f"Respaldo completado. {total_backed_up} timestamps transferidos en {time.time() - start_time:.5f} segundos." + Style.RESET_ALL)

            else:
                if config["debug"]:
                    print(Fore.GREEN + "No hay datos nuevos en la base de datos buffer para respaldar." + Style.RESET_ALL)

            # Calcular el tiempo restante y ajustarlo para asegurar que el ciclo toma el tiempo exacto.
            process_duration = time.time() - start_time
            remaining_time = max(0, backup_time - process_duration)  # Asegurar que no sea negativo
            time.sleep(remaining_time)

        except Exception as e:
            print(Fore.RED + f"Error durante el respaldo de datos: {e}" + Style.RESET_ALL)

        finally:
            conn.close()  # Cerrar la conexión a SQLite3

    # Si se ha activado el evento de parada, asegurarse de que el proceso de respaldo finalice correctamente
    if stop_event.is_set() and delete_in_progress:
        print(Fore.YELLOW + "Detención solicitada, completando respaldo en curso..." + Style.RESET_ALL)
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

            print(Fore.GREEN + "Respaldo final completado. Buffer eliminado por completo." + Style.RESET_ALL)

        except Exception as e:
            print(Fore.RED + f"Error durante el respaldo final de datos: {e}" + Style.RESET_ALL)

        finally:
            conn.close()

    close_mongodb_client()
    print(Fore.RED + "**El proceso de respaldo ha sido detenido correctamente.**" + Style.RESET_ALL)





def process_data(data_queue, stop_event, total_capture_time, original_rate, decimation_factor, sensor_numbers, sqlite_db_path, config, buffer_size):
    """
    Procesa los datos capturados y los envía a la base de datos SQLite como buffer.
    """
    persistent_buffer = []
    packet_count = 0
    decimated_rate = original_rate // decimation_factor
    interval = 1 / decimated_rate
    last_timestamp = None

    # Verificar que config sea un diccionario
    if not isinstance(config, dict):
        raise ValueError("El argumento 'config' debe ser un diccionario.")

    while not stop_event.is_set():
        if total_capture_time > 0 and packet_count >= total_capture_time:
            break

        try:
            packet_start_time = time.time()
            if config["debug"]:
                print(Fore.GREEN + f"------------------NEW PACKAGE--------------------"+ Style.RESET_ALL)
                print(f"1) Tiempo real inicial {packet_start_time}.")
            raw_data = data_queue.get(True, 2)
            packet_count += 1
            data = raw_data[:, ::decimation_factor]

            if config["debug"]:
                print(f"2) Shape {data.shape} procesado.")

            if last_timestamp is None:
                timestamps = [packet_start_time + i * interval for i in range(len(data[0]))]
            else:
                expected_first_timestamp = last_timestamp + interval
                timestamps = [expected_first_timestamp + i * interval for i in range(len(data[0]))]

            last_timestamp = timestamps[-1]

            df = DataFrame(data.transpose(), index=timestamps, columns=[f'{i}' for i in sensor_numbers])
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'time'}, inplace=True)

            if config["debug"]:
                print(f"3) Paquete número {packet_count} procesado.")
                print(f"4) Timestamps para el paquete {packet_count}: desde {timestamps[0]} hasta {timestamps[-1]}")

            persistent_buffer.extend(df.to_dict(orient='records'))

            # Agrupar los datos antes de enviarlos a SQLite3 para evitar múltiples inserciones pequeñas
            if len(persistent_buffer) >= buffer_size:
                buffer_to_db(persistent_buffer, sqlite_db_path, config)  # Usar SQLite3 como buffer
                persistent_buffer = []

            real_time_now = time.time()
            if config["debug"]:
                print(f"5) Tiempo real final {real_time_now}.")

            # Calcular el tiempo de espera necesario
            waiting_time = (last_timestamp - timestamps[0] + interval - (real_time_now - packet_start_time))
            if config["debug"]:
                print(f"6) Tiempo de espera necesario: {waiting_time:.5f} segundos.")
                print(f"7) Tiempo de proceso hasta ahora: {real_time_now - packet_start_time} segundos.")
                print(f"8) Tiempo total entre paquetes: {waiting_time + (real_time_now - packet_start_time)} segundos.")

            # Dormir solo si el tiempo de espera es positivo
            if waiting_time > 0:
                time.sleep(waiting_time)

            real_time_now = time.time()
            time_difference = (real_time_now - last_timestamp) - interval
            if config["debug"]:
                print(f"9) Diferencia entre el tiempo actual menos el último timestamp, si es positivo se atrasa: {time_difference:.5f} segundos.")

        except queue.Empty:
            continue

    if persistent_buffer:  # Respaldar cualquier dato restante en el buffer
        buffer_to_db(persistent_buffer, sqlite_db_path, config)  # Usar SQLite3 como buffer

    if total_capture_time == 0:
        print(Fore.GREEN + "Captura continua. Presiona ENTER para terminar."+ Style.RESET_ALL)
    else:
        print(Fore.RED + "CAPTURA DE DATOS COMPLETADA. Presiona ENTER para terminar."+ Style.RESET_ALL)

    stop_event.set()


def capture_data(data_queue, stop_event, deviceName, total_capture_time, original_rate, min_val,
                 max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, config):
    """
    Captura los datos del DAQ y los coloca en la cola de procesamiento.
    """
    start_time = time.time()
    number_of_sensors = len(all_sensor_numbers)
    preserve_row = [i in sensor_numbers for i in all_sensor_numbers]

    with Task() as task:
        for i in range(number_of_sensors):
            mod = 1 + i // 3
            ai = i % 3
            channel_str = f"{deviceName}Mod{mod}/ai{ai}"
            task.ai_channels.add_ai_accel_chan(channel_str, min_val=min_val, max_val=max_val, units=AccelUnits.METERS_PER_SECOND_SQUARED, sensitivity=sensitivity, sensitivity_units=AccelSensitivityUnits.VOLTS_PER_G)
        
        task.timing.cfg_samp_clk_timing(original_rate, sample_mode=AcquisitionType.CONTINUOUS, samps_per_chan=buffer_size)

        while not stop_event.is_set():
            if total_capture_time > 0 and (time.time() - start_time >= total_capture_time):
                stop_event.set()

            data = array(task.read(number_of_samples_per_channel=buffer_size)) * sensitivity
            data = data[preserve_row, :]
            data_queue.put(data)


def run_data_acquisition(deviceName, total_capture_time, original_rate, decimation_factor, 
                         min_val, max_val, sensitivity, buffer_size, sensor_numbers, 
                         sensor_numbers_all, sqlite_db_path, db_config, config, 
                         backup_time, restart_time_in_seconds, stop_event):
    """
    Función principal para iniciar la adquisición de datos con la configuración establecida.
    """
    start_time = time.time()
    data_queue = Queue()

    # Proceso para capturar datos del DAQ
    capture_process = Process(target=capture_data, args=(
        data_queue, stop_event, deviceName, total_capture_time, original_rate, 
        min_val, max_val, sensitivity, buffer_size, sensor_numbers, sensor_numbers_all, config))
    
    # Proceso para procesar los datos capturados
    processing_process = Process(target=process_data, args=(
        data_queue, stop_event, total_capture_time, original_rate, decimation_factor, 
        sensor_numbers, sqlite_db_path, config, buffer_size))

    backup_process = Process(target=backup_data, args=(
        db_config,              # Configuración de MongoDB
        sqlite_db_path,         # Ruta a la base de datos SQLite (buffer)
        db_config["db_backup_name"],  # Nombre de la base de datos MongoDB raw
        config,                 # Configuración general
        sensor_numbers,         # Números de sensores
        stop_event,             # Evento de parada
        config["backup_time"]   # Tiempo de respaldo (en segundos)
    ))

    capture_process.start()
    processing_process.start()
    backup_process.start()

    if restart_time_in_seconds > 0:
        print(f"Esperando {restart_time_in_seconds} segundos para reiniciar la toma de datos o presionar ENTER para detener.")
        stop_event.wait(timeout=restart_time_in_seconds)  # Detener tras el tiempo de reinicio o por ENTER
    else:
        input("Presiona ENTER para detener.")  # Si el restart_time es 0, esperar manualmente por ENTER

    stop_event.set()  # Detener todos los procesos

    # Unir los procesos para asegurar que finalicen correctamente
    capture_process.join(timeout=1)
    processing_process.join(timeout=1)
    backup_process.join(timeout=1)
    
    close_mongodb_client()  # Cerrar el cliente MongoDB

    if capture_process.is_alive() or processing_process.is_alive() or backup_process.is_alive():
        capture_process.terminate()
        processing_process.terminate()
        backup_process.terminate()
        close_mongodb_client()  # Cerrar el cliente MongoDB
    end_time = time.time()
    print(f"Todos los procesos han finalizado. {end_time}, tiempo total {end_time - start_time}.")


if __name__ == "__main__":
    pass  # Este archivo no está destinado a ejecutarse directamente