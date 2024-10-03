""" 
Codigo para capturar datos de N sensores de aceleración utilizando un dispositivo NI cDAQ9185 con módulos NI 9230.

El código captura datos de aceleración de N sensores en un intervalo de tiempo especificado y los guarda en un buffer definido por el usuario de acuerdo a la capacidad del DAQ 
y lo vuelca en una base de datos con SQLlite y su respectivo timestamp UNIX. 
El código también permite detener la captura de datos manualmente presionando ENTER.
Utiliza multiprocessing para captura y procesamiento de datos en paralelo. 
El procesamiento de los datos no solo decima los datos sino que también los redondea a 5 decimales y agrega el timestamp UNIX.
Python 3.10.9

"""
import nidaqmx
from nidaqmx.constants import AcquisitionType, AccelUnits, AccelSensitivityUnits
import pandas as pd
import numpy as np
import sqlite3
import time
from os import stat, mkdir
from multiprocessing import Process, Queue, Event
import queue


try:  # Crear directorio si no existe
    stat("Accelerations/")
except FileNotFoundError:
    mkdir("Accelerations/")



def buffer_to_sqlite(persistent_buffer, db_path, config, max_retries=5, initial_delay=0.5):
    attempt = 0
    delay = initial_delay

    while attempt < max_retries:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()

            df = pd.DataFrame(persistent_buffer)

            if config["debug"]:
                print(f"Datos pasando por la base de datos: {len(df)} registros.")

            timestamps = df['time'].unique()
            cursor.executemany("INSERT INTO timestamps (timestamp) VALUES (?)", [(ts,) for ts in timestamps])
            conn.commit()

            timestamp_ids = {ts: cursor.execute("SELECT id FROM timestamps WHERE timestamp = ?", (ts,)).fetchone()[0] for ts in timestamps}
            sensor_ids = {number: cursor.execute("SELECT id FROM sensors WHERE sensor_number = ?", (number,)).fetchone()[0] for number in df.columns if number != 'time'}

            sensor_data = []
            for index, row in df.iterrows():
                timestamp = row['time']
                timestamp_id = timestamp_ids[timestamp]
                for col in df.columns:
                    if col != 'time':
                        sensor_number = col
                        sensor_id = sensor_ids[sensor_number]
                        sensor_data.append((timestamp_id, sensor_id, row[col]))

            cursor.executemany("INSERT INTO accelerations (timestamp_id, sensor_id, acceleration_value) VALUES (?, ?, ?)", sensor_data)
            conn.commit()
            conn.close()
            persistent_buffer.clear()

            if config["debug"]:
                print(f"Buffer a SQLite exitoso. {len(sensor_data)} datos insertados.")
            break
        
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e):
                print(f"Intento {attempt + 1} fallido, la base de datos está bloqueada. Reintentando en {delay} segundos...")
                time.sleep(delay)
                delay *= 2
                attempt += 1
            else:
                raise
        except Exception as e:
            print(f"An error occurred: {e}")
            attempt += 1
            if attempt < max_retries:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2
            else:
                print("Max retries reached. Data cannot be saved.")
                break
        finally:
            if conn:
                conn.close()

def capture_data(data_queue, stop_event, deviceName, total_capture_time, original_rate, min_val,
                 max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, config):
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

            # if config["debug"]:
            #     print(f"Datos capturados del DAQ: {data.shape} antes de decimación.")

def process_data(data_queue, stop_event, total_capture_time, original_rate, decimation_factor, sensor_numbers, db_path, buffer_size, config):
    persistent_buffer = []

    # Condición para mostrar el mensaje en modo debug o no
    if config["debug"]:
        print('''
        ------------CAPTURANDO DATOS DEL DAQ------------
         Presiona ENTER para detener la captura de datos.
                        DEBUG MODE ON
        '''
        )
    else:
        print('''
        ------------CAPTURANDO DATOS DEL DAQ------------
         Presiona ENTER para detener la captura de datos.
        '''
        )

    packet_count = 0  # Contador de paquetes procesados
    decimated_rate = original_rate // decimation_factor  # Frecuencia de muestreo después de la decimación
    interval = 1 / decimated_rate  # Intervalo de tiempo entre cada muestra en segundos

    # Usar tiempo real para el control de sincronización
    last_time = pd.Timestamp.now().timestamp()
    last_timestamp = None  # Guardar el último timestamp del paquete anterior

    first_timestamp = None  # Guardar el primer timestamp del primer paquete
    final_timestamp = None  # Guardar el último timestamp del último paquete

    while not stop_event.is_set():
        if total_capture_time > 0 and packet_count >= total_capture_time:
            break  # Romper el ciclo si se ha alcanzado el tiempo límite

        try:
            current_time = pd.Timestamp.now().timestamp()  # Tiempo actual
            elapsed_time = current_time - last_time  # Tiempo transcurrido desde la última captura

            # Si no ha pasado suficiente tiempo, esperar
            if elapsed_time < 1:
                time.sleep(1 - elapsed_time)
                current_time = pd.Timestamp.now().timestamp()

            last_time = current_time  # Actualizar el tiempo para el siguiente ciclo

            # Capturar los datos del DAQ
            raw_data = data_queue.get(True, 2)  # Esperar datos con un timeout de 2 segundos
            packet_count += 1  # Contar los paquetes procesados

            # Decimación de los datos
            data = raw_data[:, ::decimation_factor]

            # Generar timestamps para el paquete basado en el tiempo real y el intervalo de muestreo
            timestamps = [last_time + i * interval for i in range(len(data[0]))]

            # Guardar el primer timestamp del primer paquete
            if first_timestamp is None:
                first_timestamp = timestamps[0]

            # Guardar el último timestamp del paquete actual
            final_timestamp = timestamps[-1]

            df = pd.DataFrame(data.transpose(), index=timestamps, columns=[f'{i}' for i in sensor_numbers])
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'time'}, inplace=True)

            # Conteo de Paquetes
            if config["debug"]:
                print(f"Paquete número {packet_count} procesado.")

            # Agregar los datos nuevos al buffer persistente
            persistent_buffer.extend(df.to_dict(orient='records'))
            buffer_to_sqlite(persistent_buffer, db_path, config)

            # Comparar timestamps si el modo debug está activado
            if config["debug"]:
                if last_timestamp is not None:
                    now_difference = pd.Timestamp.now().timestamp() - (last_timestamp + 1 / decimated_rate)
                    print(f"Diferencia ajustada entre el último timestamp del paquete anterior y el tiempo actual: {now_difference} segundos.")
                    print(f"--------------------------------------------")

                print(f"Timestamps para el paquete {packet_count}: desde {timestamps[0]} hasta {timestamps[-1]}")

            # Guardar el último timestamp del paquete actual para la próxima iteración
            last_timestamp = timestamps[-1]

        except queue.Empty:
            continue

    if total_capture_time == 0:
        print("Captura continua. Presiona ENTER para terminar.")
    else:
        print("Captura de datos completada.")

    # Calcular el tiempo total de captura basado en los timestamps
    if config["debug"] and first_timestamp is not None and final_timestamp is not None:
        capture_time = final_timestamp - first_timestamp
        print(f"Tiempo total real de captura de datos: {capture_time:.5f} segundos.")

    stop_event.set()  # Asegurarse de que la captura se detenga


def main(deviceName, total_capture_time, original_rate, decimation_factor, min_val, max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, db_path, config):
    data_queue = Queue()
    stop_event = Event()

    # Pasar buffer_size a process_data
    capture_process = Process(target=capture_data, args=(
        data_queue, stop_event, deviceName, total_capture_time, original_rate, 
        min_val, max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, config))
    
    # Aquí añadimos el buffer_size como argumento
    processing_process = Process(target=process_data, args=(
        data_queue, stop_event, total_capture_time, original_rate, decimation_factor, 
        sensor_numbers, db_path, buffer_size, config))

    capture_process.start()
    processing_process.start()

    input(" \n")
    stop_event.set()

    capture_process.join(timeout=1)
    processing_process.join(timeout=1)

    if capture_process.is_alive() or processing_process.is_alive():
        capture_process.terminate()
        processing_process.terminate()

    print("Todos los procesos han finalizado.")

if __name__ == "__main__":
    main()
