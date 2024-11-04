""" 
Codigo para capturar datos de N sensores de aceleración utilizando un dispositivo NI cDAQ9185 con módulos NI 9230.

El código captura datos de aceleración de N sensores en un intervalo de tiempo especificado y los guarda en un buffer definido por el usuario de acuerdo a la capacidad del DAQ 
y lo vuelca en una base de datos MongoDB y su respectivo timestamp UNIX. 
El código también permite detener la captura de datos manualmente presionando ENTER.
Utiliza multiprocessing para captura y procesamiento de datos en paralelo. 
El procesamiento de los datos no solo decima los datos sino que también los redondea a 5 decimales y agrega el timestamp UNIX.
Python 3.10.9

"""
import nidaqmx
from nidaqmx.constants import AcquisitionType, AccelUnits, AccelSensitivityUnits
import pandas as pd
import numpy as np
from pymongo import MongoClient, errors
import time
from os import stat, mkdir
from multiprocessing import Process, Queue, Event
import queue
from colorama import Fore, Style

# Crear cliente persistente para MongoDB
mongo_client = None

def initialize_mongodb_client(db_config):
    """Inicializa el cliente MongoDB si no está ya inicializado."""
    global mongo_client
    if mongo_client is None:
        mongo_client = MongoClient(db_config['db_host'], db_config['db_port'])
    return mongo_client

def close_mongodb_client():
    """Cierra el cliente MongoDB si está abierto."""
    global mongo_client
    if mongo_client is not None:
        mongo_client.close()
        mongo_client = None  # Resetear para asegurarnos de que se puede reinicializar más adelante

def buffer_to_mongodb(persistent_buffer, db_config, config, max_retries=5, initial_delay=0.5):
    """Función para insertar los datos en MongoDB."""
    attempt = 0
    delay = initial_delay

    client = initialize_mongodb_client(db_config)
    db = client[db_config['db_name']]
    accelerations_collection = db['accelerations']

    while attempt < max_retries:
        try:
            df = pd.DataFrame(persistent_buffer)

            if config["debug"]:
                print(f"5) Datos pasando por la base de datos: {len(df)} registros.")

            # Insertar los datos agrupados por timestamp
            grouped_data = df.groupby('time').apply(lambda x: [
                {"sensor_id": col, "acceleration": row[col]} for _, row in x.iterrows() for col in x.columns if col != 'time'
            ]).reset_index(name='sensor_data')

            bulk_insert = [
                {"timestamp": row['time'], "sensor_data": row['sensor_data']}
                for _, row in grouped_data.iterrows()
            ]

            if bulk_insert:
                accelerations_collection.insert_many(bulk_insert, ordered=False)

            persistent_buffer.clear()

            if config["debug"]:
                print(f"6) Buffer a MongoDB exitoso. {len(bulk_insert)} timestamps insertados.")
            break

        except Exception as e:
            print(f"Error: {e}")
            attempt += 1
            if attempt < max_retries:
                print(f"Reintentando en {delay} segundos...")
                time.sleep(delay)
                delay *= 2
            else:
                close_mongodb_client()
                print("Se alcanzó el máximo de intentos. No se pudieron guardar los datos.")
            break
    close_mongodb_client()

def backup_data(db_config, buffer_db, raw_db, config, sensor_numbers, stop_event, backup_time):
    """
    Realiza el respaldo de todos los datos de la base de datos buffer a la base de datos grande (raw) en paquetes de 1000 registros.
    Este proceso se repite cada X segundos, según lo indicado por backup_time.
    """
    client = initialize_mongodb_client(db_config)
    buffer_collection = client[buffer_db]['accelerations']
    raw_collection = client[raw_db]['accelerations']
    max_batch_size = 50000  # Tamaño máximo de los paquetes para el respaldo
    delete_in_progress = False

    while not stop_event.is_set() or delete_in_progress:
        start_time = time.time()  # Registrar el tiempo inicial para cada respaldo

        if config["debug"]:
            print(Fore.GREEN + "----------------------------------------------Iniciando proceso de respaldo..." + Style.RESET_ALL)

        try:
            # Obtener el total de registros en la base de datos buffer
            total_data = buffer_collection.count_documents({})

            if total_data > 0:
                if config["debug"]:
                    print(Fore.YELLOW + f"Se encontraron {total_data} registros. Respaldo en paquetes de máximo {max_batch_size} registros." + Style.RESET_ALL)

                offset = 0
                total_backed_up = 0
                delete_in_progress = True  # Marcar que la eliminación está en progreso

                while offset < total_data:
                    # Obtener el siguiente lote de datos
                    buffer_data = list(buffer_collection.find().limit(max_batch_size))
                    if not buffer_data:
                        break  # Salir del bucle si no hay más datos

                    # Respaldar datos al raw
                    raw_collection.insert_many(buffer_data, ordered=False)

                    # Contar los registros respaldados
                    total_backed_up += len(buffer_data)
                    if config["debug"]:
                        print(Fore.CYAN + f"Respaldo de paquete {total_backed_up // max_batch_size + 1} completado ({len(buffer_data)} registros)." + Style.RESET_ALL)

                    # Eliminar los datos respaldados del buffer por ID
                    buffer_collection.delete_many({"_id": {"$in": [doc["_id"] for doc in buffer_data]}})
                    if config["debug"]:
                        print(Fore.GREEN + f"**Se han eliminado {len(buffer_data)} registros del buffer.**" + Style.RESET_ALL)

                    offset += len(buffer_data)

                delete_in_progress = False  # Marcar que la eliminación ha sido completada

                if config["debug"]:
                    print(Fore.YELLOW + f"Respaldo completado. {total_backed_up} registros transferidos en {time.time() - start_time:.5f} segundos." + Style.RESET_ALL)

            else:
                if config["debug"]:
                    print(Fore.GREEN + "No hay datos nuevos en la base de datos buffer para respaldar." + Style.RESET_ALL)

            # Calcular el tiempo restante y ajustarlo para asegurar que el ciclo toma el tiempo exacto.
            process_duration = time.time() - start_time
            remaining_time = max(0, backup_time - process_duration)  # Asegurar que no sea negativo
            time.sleep(remaining_time)

        except Exception as e:
            print(Fore.RED + f"Error durante el respaldo de datos: {e}" + Style.RESET_ALL)

    # Si se ha activado el evento de parada, asegurarse de que el proceso de respaldo finalice correctamente
    if stop_event.is_set() and delete_in_progress:
        print(Fore.YELLOW + "Detención solicitada, completando respaldo en curso..." + Style.RESET_ALL)
        try:
            # Finalizar cualquier respaldo pendiente si el evento de parada se ha activado
            buffer_data = list(buffer_collection.find().limit(max_batch_size))

            while buffer_data:
                raw_collection.insert_many(buffer_data, ordered=False)
                buffer_collection.delete_many({"_id": {"$in": [doc["_id"] for doc in buffer_data]}})
                if config["debug"]:
                    print(Fore.GREEN + f"Respaldo final de paquete completado ({len(buffer_data)} registros)." + Style.RESET_ALL)
                buffer_data = list(buffer_collection.find().limit(max_batch_size))

            print(Fore.GREEN + "Respaldo final completado. Buffer eliminado por completo." + Style.RESET_ALL)

        except Exception as e:
            print(Fore.RED + f"Error durante el respaldo final de datos: {e}" + Style.RESET_ALL)

    close_mongodb_client()
    print(Fore.RED + "**El proceso de respaldo ha sido detenido correctamente.**" + Style.RESET_ALL)



def process_data(data_queue, stop_event, total_capture_time, original_rate, decimation_factor, sensor_numbers, db_config, buffer_size, config):
    """
    Procesa los datos capturados y los envía a la base de datos MongoDB.
    """
    persistent_buffer = []
    packet_count = 0
    decimated_rate = original_rate // decimation_factor
    interval = 1 / decimated_rate
    last_timestamp = None

    while not stop_event.is_set():
        if total_capture_time > 0 and packet_count >= total_capture_time:
            break

        try:
            packet_start_time = time.time()
            if config["debug"]:
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

            df = pd.DataFrame(data.transpose(), index=timestamps, columns=[f'{i}' for i in sensor_numbers])
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'time'}, inplace=True)

            if config["debug"]:
                print(f"3) Paquete número {packet_count} procesado.")
                print(f"4) Timestamps para el paquete {packet_count}: desde {timestamps[0]} hasta {timestamps[-1]}")

            persistent_buffer.extend(df.to_dict(orient='records'))

            # Agrupar los datos antes de enviarlos a MongoDB para evitar múltiples inserciones pequeñas
            if len(persistent_buffer) >= buffer_size:
                buffer_to_mongodb(persistent_buffer, db_config, config)
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
                print(f"--------------------------------------------")

        except queue.Empty:
            continue

    if persistent_buffer:  # Respaldar cualquier dato restante en el buffer
        buffer_to_mongodb(persistent_buffer, db_config, config)

    if total_capture_time == 0:
        print("Captura continua. Presiona ENTER para terminar.")
    else:
        close_mongodb_client()  # Cerrar el cliente MongoDB
        print("Captura de datos completada.")

    stop_event.set()


def capture_data(data_queue, stop_event, deviceName, total_capture_time, original_rate, min_val,
                 max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, config):
    """
    Captura los datos del DAQ y los coloca en la cola de procesamiento.
    """
    start_time = time.time()
    number_of_sensors = len(all_sensor_numbers)
    preserve_row = [i in sensor_numbers for i in all_sensor_numbers]

    with nidaqmx.Task() as task:
        for i in range(number_of_sensors):
            mod = 1 + i // 3
            ai = i % 3
            channel_str = f"{deviceName}Mod{mod}/ai{ai}"
            task.ai_channels.add_ai_accel_chan(channel_str, min_val=min_val, max_val=max_val, units=AccelUnits.METERS_PER_SECOND_SQUARED, sensitivity=sensitivity, sensitivity_units=AccelSensitivityUnits.VOLTS_PER_G)
        
        task.timing.cfg_samp_clk_timing(original_rate, sample_mode=AcquisitionType.CONTINUOUS, samps_per_chan=buffer_size)

        while not stop_event.is_set():
            if total_capture_time > 0 and (time.time() - start_time >= total_capture_time):
                stop_event.set()

            data = np.array(task.read(number_of_samples_per_channel=buffer_size)) * sensitivity
            data = data[preserve_row, :]
            data_queue.put(data)


def run_data_acquisition(deviceName, total_capture_time, original_rate, decimation_factor, min_val, max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, db_config, config, backup_time, restart_time_in_seconds, stop_event):
    """
    Función principal para iniciar la adquisición de datos con la configuración establecida.
    """
    start_time = time.time()
    data_queue = Queue()

    # Proceso para capturar datos del DAQ
    capture_process = Process(target=capture_data, args=(
        data_queue, stop_event, deviceName, total_capture_time, original_rate, 
        min_val, max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, config))
    
    # Proceso para procesar los datos capturados
    processing_process = Process(target=process_data, args=(
        data_queue, stop_event, total_capture_time, original_rate, decimation_factor, 
        sensor_numbers, db_config, buffer_size, config))

    # Proceso de respaldo que corre en paralelo
    backup_process = Process(target=backup_data, args=(db_config, db_config['db_name'], db_config['db_backup_name'], config, sensor_numbers, stop_event, backup_time))

    capture_process.start()
    processing_process.start()
    backup_process.start()

    if restart_time_in_seconds > 0:
        print(f"Esperando {restart_time_in_seconds} segundos para detener o presionar ENTER.")
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