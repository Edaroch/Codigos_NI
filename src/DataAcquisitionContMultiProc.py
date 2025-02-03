""" 
Code to capture data from N acceleration sensors using an NI cDAQ9185 device with NI 9230 modules.
The code captures acceleration data from N sensors over a specified time interval and stores it in a user-defined buffer according to the DAQ's capacity.
It then transfers the data to a MongoDB database along with its corresponding UNIX timestamp.
The code also allows manual data capture stopping by pressing ENTER.
It uses multiprocessing for parallel data capture and processing.
Data processing not only decimates the data but also rounds it to 5 decimal places and adds the UNIX timestamp.
Python 3.10.9
"""
from nidaqmx import Task
from nidaqmx.constants import AcquisitionType, AccelUnits, AccelSensitivityUnits
from pandas import DataFrame
from numpy import array, concatenate
from pymongo import MongoClient, errors
from sqlite3 import connect
from scipy.signal import decimate  # Importar la función de decimación de SciPy
import time
from os import stat, mkdir
from multiprocessing import Process, Queue, Event
import queue
from colorama import Fore, Style
from datetime import datetime

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
    """Closes the MongoDB client if it is open."""
    global mongo_client
    if mongo_client is not None:
        mongo_client.close()
        mongo_client = None  # Resetear para asegurarnos de que se puede reinicializar más adelante

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



def backup_data(db_config, sqlite_db_path, raw_db, config, sensor_numbers, stop_event, backup_time):
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


def process_data(data_queue, stop_event, total_capture_time, original_rate, decimation_factor, sensor_numbers, sqlite_db_path, config, buffer_size):
    """
    Processes captured data and sends it to the SQLite database as a buffer.
    """
    persistent_buffer = []
    packet_count = 0
    queue_time = 0
    decimated_rate = original_rate // decimation_factor
    interval = 1 / decimated_rate
    last_timestamp = None

    # Verificar que config sea un diccionario
    if not isinstance(config, dict):
        raise ValueError("The argue 'config' must be a dictionary.")

    while not stop_event.is_set():
        if total_capture_time > 0 and packet_count >= total_capture_time:
            break

        try:
            while not data_queue.empty():
                packet_start_time = time.time()
                if config["debug"]:
                    print(Fore.GREEN + f"------------------NEW PACKAGE--------------------"+ Style.RESET_ALL)
                    print(f"1) Initial real-time {packet_start_time}.")
                try:
                    raw_data = data_queue.get_nowait()
                except queue.Empty:
                    break
                packet_count += 1
                data = array([decimate(channel, decimation_factor, zero_phase=True) for channel in raw_data])

                if config["debug"]:
                    print(f"2) Shape {data.shape} processed. - {time.time()}")
                    if data_queue.qsize() > 0:
                        print(Fore.RED + f"3) Current size of data_queue {data_queue.qsize()}"+ Style.RESET_ALL)
                    else:
                        print(Fore.GREEN + f"3) Current size of data_queue {data_queue.qsize()}"+ Style.RESET_ALL)

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
                    print(f"4) Packet number {packet_count} processed.")
                    print(f"5) Timestamps for packet {packet_count}: from {timestamps[0]} to {timestamps[-1]}")

                persistent_buffer.extend(df.to_dict(orient='records'))

                # Agrupar los datos antes de enviarlos a SQLite3 para evitar múltiples inserciones pequeñas
                if len(persistent_buffer) >= buffer_size/decimation_factor:
                    buffer_to_db(persistent_buffer, sqlite_db_path, config)  # Usar SQLite3 como buffer
                    persistent_buffer = []

                real_time_now = time.time()
                if config["debug"]:
                    print(f"6) Final real-time {real_time_now} and real-time duration {(real_time_now - packet_start_time)}.")

                # Calcular el tiempo de espera necesario
                waiting_time = (last_timestamp - timestamps[0] + interval - (real_time_now - packet_start_time)) #
                if config["debug"]:
                    print(f"7) Required waiting time: {waiting_time:.5f} seconds.")
                    print(f"8) Processing time so far: {real_time_now - packet_start_time} seconds.")
                    print(f"9) Total time between packets: {waiting_time + (real_time_now - packet_start_time)} seconds.")

                # Dormir solo si el tiempo de espera es positivo
                if waiting_time > 0 :
                    if data_queue.qsize() > 0:
                        time.sleep(0.01)
                        queue_time += abs(real_time_now - packet_start_time)
                    else:
                        time.sleep(abs(waiting_time) + abs(queue_time))
                        queue_time = 0    
                        
                real_time_now = time.time()
                time_difference = (real_time_now - last_timestamp - interval) # Diferencia de tiempo real
                if config["debug"]:
                    print(f"10) Real-time difference: {time_difference:.5f} seconds. DELAY (+), ADVANCE (-).")

            time.sleep(0.01)    
                
        except queue.Empty:
            continue

    if persistent_buffer:  # Respaldar cualquier dato restante en el buffer
        buffer_to_db(persistent_buffer, sqlite_db_path, config)  # Usar SQLite3 como buffer

    if total_capture_time == 0:
        print(Fore.GREEN + "Continuous capture. Press ENTER to stop."+ Style.RESET_ALL)
    else:
        print(Fore.RED + "DATA CAPTURE COMPLETED. Press ENTER to finnish."+ Style.RESET_ALL)

    stop_event.set()


def capture_data(data_queue, stop_event, deviceName, total_capture_time, original_rate, min_val,
                 max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, config):
    """
    Captures data from the DAQ and places it in the processing queue, adjusting the data
    to match the acquisition frequency and buffer size.
    """

    start_time = time.time()
    number_of_sensors = len(all_sensor_numbers)
    preserve_row = [i in sensor_numbers for i in all_sensor_numbers]
    persistent_buffer_capture = []  # Buffer para datos excedentes

    # Calcular datos esperados por segundo
    total_expected_samples = int(original_rate * 1)  # Muestras esperadas en 1 segundo

    with Task() as task:
        for i in range(number_of_sensors):
            mod = 1 + i // 3
            ai = i % 3
            channel_str = f"{deviceName}Mod{mod}/ai{ai}"
            task.ai_channels.add_ai_accel_chan(
                channel_str, 
                min_val=min_val, 
                max_val=max_val, 
                units=AccelUnits.METERS_PER_SECOND_SQUARED, 
                sensitivity=sensitivity, 
                sensitivity_units=AccelSensitivityUnits.VOLTS_PER_G
            )
        
        task.timing.cfg_samp_clk_timing(
            original_rate, 
            sample_mode=AcquisitionType.CONTINUOUS, 
            samps_per_chan=buffer_size
        )

        last_time = start_time

        while not stop_event.is_set():
            current_time = time.time()

            # Verificar tiempo de captura total
            if total_capture_time > 0 and (current_time - start_time >= total_capture_time):
                stop_event.set()
                break

            try:
                # Leer datos del DAQ
                data = array(task.read(number_of_samples_per_channel=buffer_size))
                data = data[preserve_row, :]  # Filtrar sensores seleccionados
                
                # Combinar datos persistentes con nuevos datos
                if persistent_buffer_capture:
                    data = concatenate([persistent_buffer_capture, data], axis=1)

                # Verificar si tenemos suficientes datos para un paquete completo
                if data.shape[1] >= total_expected_samples:
                    # Extraer un paquete completo
                    full_data = data[:, :total_expected_samples]
                    
                    # Guardar datos restantes en el buffer persistente
                    persistent_buffer_capture = data[:, total_expected_samples:]
                    
                    # Enviar paquete a la cola
                    data_queue.put(full_data)

                    if config["debug"]:
                        print(f"Complete packet sent: {full_data.shape}, Remaining data: {persistent_buffer_capture.shape}, Packet time: {current_time - last_time}")
                    desfase = current_time - last_time    
                    last_time = current_time  # Actualizar tiempo del último paquete
                else:
                    # Si no hay suficientes datos para un paquete, guardar todo en el buffer persistente
                    persistent_buffer_capture = data

                    if config["debug"]:
                        print(f"Remaining data in the buffer: {persistent_buffer_capture.shape}")

                time.sleep(min(0, abs(5 * (1 - desfase))))  # Pausa para evitar uso excesivo de CPU
                print(f"Waiting time: {1 - desfase}")

            except Exception as e:
                print(f"[ERROR] Error capturing data: {e}")    



def run_data_acquisition(deviceName, total_capture_time, original_rate, decimation_factor, 
                         min_val, max_val, sensitivity, buffer_size, sensor_numbers, 
                         sensor_numbers_all, sqlite_db_path, db_config, config, 
                         backup_time, restart_time_in_seconds, stop_event):
    """
    Main function to start data acquisition with the configured settings.
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
        print(f"Waiting {restart_time_in_seconds} seconds to restart data acquisition or press ENTER to stop.")
        stop_event.wait(timeout=restart_time_in_seconds)  # Detener tras el tiempo de reinicio o por ENTER
    else:
        input("Press ENTER to stop.")  # Si el restart_time es 0, esperar manualmente por ENTER

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
    print(f"All processes have finished. {end_time}, total time {end_time - start_time}.")


if __name__ == "__main__":
    pass  # Este archivo no está destinado a ejecutarse directamente