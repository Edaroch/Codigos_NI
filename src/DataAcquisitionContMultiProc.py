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

def setup_database(db_path, number_of_sensors):  # Añade el número de sensores como parámetro
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Generar dinámicamente las columnas de los sensores
    sensor_columns = ', '.join([f'sensor{i + 1} REAL' for i in range(number_of_sensors)])
    sql_query = f'''
        CREATE TABLE IF NOT EXISTS acceleration_data (
            time REAL,
            {sensor_columns}
        )
    '''
    
    
    conn.commit()
    conn.close()
    print("Configuración de la base de datos completa.")

def buffer_to_sqlite(buffer, db_path, final=False):
    if buffer:
        conn = sqlite3.connect(db_path)
        pd.DataFrame(buffer).to_sql('acceleration_data', conn, if_exists='append', index=False)
        conn.close()
        buffer.clear()
        # print("Datos guardados en SQLite.")

def capture_data(data_queue, stop_event, deviceName, total_capture_time, original_rate, decimation_factor, min_val, max_val, sensitivity, buffer_size, number_of_sensors, db_path):
    setup_database(db_path, number_of_sensors)
    print("Inicio de captura de datos. Presiona ENTER para cerrar la aplicación.")
    start_time = time.time()
    with nidaqmx.Task() as task:
        for i in range(number_of_sensors):
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
            data_queue.put(data)

def process_data(data_queue, stop_event, deviceName, total_capture_time, original_rate, decimation_factor, min_val, max_val, sensitivity, buffer_size, number_of_sensors, db_path):
    print("Inicio del procesamiento de datos. Presiona ENTER para cerrar la aplicación.")
    while not stop_event.is_set() or not data_queue.empty():
        try:
            raw_data = data_queue.get(True, 2)  # Short timeout to check stop_event regularly
            data = raw_data[:, ::decimation_factor]
            timestamps = pd.date_range(start=pd.Timestamp.now(), periods=len(data[0]), freq=pd.DateOffset(milliseconds=1000/(original_rate/decimation_factor)))
            df = pd.DataFrame(data.transpose(), index=timestamps, columns=[f'sensor{i+1}' for i in range(6)])
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'time'}, inplace=True)
            df['time'] = df['time'].apply(lambda x: x.timestamp())
            buffer_to_sqlite(df.to_dict(orient='records'), db_path)
        except queue.Empty:
            continue
    print("Procesamiento de datos completado. Presiona ENTER para finalizar")
    stop_event.set()  # Ensure to signal stop to all processes



def main(deviceName, total_capture_time, original_rate, decimation_factor, min_val, max_val, sensitivity, buffer_size, number_of_sensors, db_path):
    data_queue = Queue()
    stop_event = Event()

    capture_process = Process(target=capture_data, args=(data_queue, stop_event, deviceName, total_capture_time, original_rate, decimation_factor, min_val, max_val, sensitivity, buffer_size, number_of_sensors, db_path))
    processing_process = Process(target=process_data, args=(data_queue, stop_event, deviceName, total_capture_time, original_rate, decimation_factor, min_val, max_val, sensitivity, buffer_size, number_of_sensors, db_path))

    capture_process.start()
    processing_process.start()

    input("Presiona ENTER para detener la captura de datos.\n")
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
