""" 
Codigo para capturar datos de 6 sensores de aceleración utilizando un dispositivo NI cDAQ9185 con 2 módulos NI 9230 de 3 canales cada uno.

El código captura datos de aceleración de 6 sensores en un intervalo de tiempo especificado y los guarda en un buffer de la capacidad del DAQ 
esto es 6400 muestras en un segundo y lo vuelca en una base de datos con SQLlite y su respectivo timestamp UNIX. 
El código también permite detener la captura de datos manualmente.
Utiliza multiprocessing para captura y procesamiento de datos en paralelo.
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



def buffer_to_sqlite(persistent_buffer, db_path, max_retries=5, initial_delay=0.5):
    """Guardar buffer en SQLite con reintentos en caso de bloqueo de la base de datos, usando un buffer persistente."""
    attempt = 0
    delay = initial_delay

    while attempt < max_retries:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL;")  # Asegurarse de que WAL está activado en cada conexión
            cursor = conn.cursor()

            df = pd.DataFrame(persistent_buffer)

            # Save timestamp
            timestamps = df['time'].unique()
            cursor.executemany("INSERT INTO timestamps (timestamp) VALUES (?)", [(ts,) for ts in timestamps])
            conn.commit()

            # Fetch the IDs for the timestamps
            timestamp_ids = {ts: cursor.execute("SELECT id FROM timestamps WHERE timestamp = ?", (ts,)).fetchone()[0] for ts in timestamps}

            # Fetch the sensor IDs from the sensors table
            sensor_ids = {number: cursor.execute("SELECT id FROM sensors WHERE sensor_number = ?", (number,)).fetchone()[0] for number in df.columns if number != 'time'}

            # Prepare sensor data for insertion
            sensor_data = []
            for index, row in df.iterrows():
                timestamp = row['time']
                timestamp_id = timestamp_ids[timestamp]
                for col in df.columns:
                    if col != 'time':
                        sensor_number = col
                        sensor_id = sensor_ids[sensor_number]
                        sensor_data.append((timestamp_id, sensor_id, row[col]))

            # Insert sensor data
            cursor.executemany("INSERT INTO accelerations (timestamp_id, sensor_id, acceleration_value) VALUES (?, ?, ?)", sensor_data)
            conn.commit()
            conn.close()
            persistent_buffer.clear()  # Limpiar el buffer solo después de una escritura exitosa
            break  # Salir del bucle si la inserción fue exitosa
        
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e):
                print(f"Intento {attempt + 1} fallido, la base de datos está bloqueada. Reintentando en {delay} segundos...")
                time.sleep(delay)
                delay *= 2  # Aumentar el tiempo de espera para el próximo intento
                attempt += 1
            else:
                raise  # Levantar otras excepciones de SQLite que no sean 'database is locked'
        except Exception as e:
            print(f"An error occurred: {e}")
            attempt += 1
            if attempt < max_retries:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                print("Max retries reached. Data not saved.")
                break
        finally:
            if conn:
                conn.close()  # Asegurar que la conexión se cierre correctamente
    else:
        print("No se pudo guardar los datos después de varios intentos. Los datos permanecen en el buffer para un próximo intento.")

def capture_data(data_queue, stop_event, deviceName, total_capture_time, original_rate, min_val,
                 max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers):
    """
    Function Duties:
        All data is captured from the DAQ
        Only channels that are set to be recorded are preserved
    """
    # print("Inicio de captura de datos. Presiona ENTER para cerrar la aplicación.")
    start_time = time.time()
    number_of_sensors = len(all_sensor_numbers)
    preserve_row = [i in sensor_numbers for i in all_sensor_numbers]
    with nidaqmx.Task() as task:
        for i in range(number_of_sensors):  # firstly data is retrieved for all channels
            mod = 1 + i // 3
            ai = i % 3
            channel_str = f"{deviceName}Mod{mod}/ai{ai}"
            task.ai_channels.add_ai_accel_chan(channel_str, min_val=min_val, max_val=max_val, units=AccelUnits.METERS_PER_SECOND_SQUARED, sensitivity=sensitivity, sensitivity_units=AccelSensitivityUnits.VOLTS_PER_G)
        task.timing.cfg_samp_clk_timing(original_rate, sample_mode=AcquisitionType.CONTINUOUS, samps_per_chan=buffer_size)

        while not stop_event.is_set():
            if total_capture_time > 0 and (time.time() - start_time >= total_capture_time):
                # print("Tiempo de captura completado.")
                stop_event.set()
            data = np.array(task.read(number_of_samples_per_channel=buffer_size)) * sensitivity
            data = data[preserve_row, :]  # unused data (daq channels without sensor pluged in) is removed
            data_queue.put(data)

def process_data(data_queue, stop_event, total_capture_time, original_rate, decimation_factor, sensor_numbers, db_path):
    persistent_buffer = []  # Buffer persistente que acumula datos hasta que se pueden guardar
    print('''
            ------------CAPTURANDO DATOS DEL DAQ------------
             Presiona ENTER para detener la captura de datos.
          '''
          )
    while not stop_event.is_set() or not data_queue.empty():
        try:
            raw_data = data_queue.get(True, 2)  # Short timeout to check stop_event regularly
            data = raw_data[:, ::decimation_factor]
            timestamps = pd.date_range(start=pd.Timestamp.now(), periods=len(data[0]), freq=pd.DateOffset(milliseconds=1000/(original_rate/decimation_factor)))
            # df = pd.DataFrame(data.transpose(), index=timestamps, columns=[f'sensor{i+1}' for i in range(number_of_sensors)])
            df = pd.DataFrame(data.transpose(), index=timestamps, columns=[f'{i}' for i in sensor_numbers])
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'time'}, inplace=True)
            df['time'] = df['time'].apply(lambda x: x.timestamp())
            # Redondear solo las columnas de sensores a X decimales
            sensor_columns = [col for col in df.columns if 'sensor' in col]
            # df[sensor_columns] = df[sensor_columns].round(10)
            # Añadir los datos nuevos al buffer persistente
            persistent_buffer.extend(df.to_dict(orient='records'))
            # Intentar guardar el buffer persistente en la base de datos
            buffer_to_sqlite(persistent_buffer, db_path)
        except queue.Empty:
            continue
    if total_capture_time == 0:
        print("Captura de datos completado.")
    else:
        print("Captura de datos completado. Presiona ENTER para terminar")
    stop_event.set()  # Ensure to signal stop to all processes



def main(deviceName, total_capture_time, original_rate, decimation_factor, min_val, max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, db_path):
    data_queue = Queue()
    stop_event = Event()

    capture_process = Process(target=capture_data, args=(data_queue, stop_event, deviceName, total_capture_time, original_rate, min_val, max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers))
    processing_process = Process(target=process_data, args=(data_queue, stop_event, total_capture_time, original_rate, decimation_factor, sensor_numbers, db_path))

    capture_process.start()
    processing_process.start()

    input(" \n")
    stop_event.set()

    capture_process.join(timeout=1)
    processing_process.join(timeout=1)

    if capture_process.is_alive() or processing_process.is_alive():
        # print("Forzando la terminación de procesos pendientes...")
        capture_process.terminate()
        processing_process.terminate()

    print("Todos los procesos han finalizado.")
    pass

if __name__ == "__main__":
    main()
