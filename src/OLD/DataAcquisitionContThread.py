""" 
Codigo para capturar datos de 6 sensores de aceleración utilizando un dispositivo NI cDAQ9185 con 2 módulos NI 9230 de 3 canales cada uno.

El código captura datos de aceleración de 6 sensores en un intervalo de tiempo especificado y los guarda en un buffer de la capacidad del DAQ 
esto es 6400 muestras en un segundo y lo vuelca en una base de datos con SQLlite y su respectivo timestamp UNIX. 
El código también permite detener la captura de datos manualmente.
Utiliza threading para captura y procesamiento de datos.
Python 3.10.9

"""
import nidaqmx
from nidaqmx.constants import AcquisitionType, AccelUnits, AccelSensitivityUnits
import pandas as pd
import numpy as np
import sqlite3
import time
import threading
from os import stat, mkdir

# Configuración de la captura
deviceName = 'cDAQ9185-21DA9E1'
total_capture_time = 15*60  # Configurado a 60 segundos para captura limitada por tiempo
original_rate = 6400  # Tasa de muestreo original en Hz
decimation_factor = 16  # Factor de decimación para obtener 400 Hz
rate = original_rate / decimation_factor  # Frecuencia de muestreo efectiva en Hz después de la decimación
min_val = -0.006 # Valor mínimo en Volts
max_val = 0.006 # Valor máximo en Volts
sensitivity = 10.0  # Sensibilidad en Volts/G
batch_size = 20  # Número de registros para escribir por lote
buffer_size = 6400  # Esto define cuántas muestras se leerán en cada ciclo del bucle
number_of_sensors = 6  # Número de sensores de aceleración

db_path = "Accelerations/aceleraciones.db"

try:
    stat("Accelerations/")
except:
    mkdir("Accelerations/")

def setup_database(number_of_sensors):  # Añade el número de sensores como parámetro
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


def buffer_to_sqlite(buffer, db_path, final=False): # Escribir los datos en la base de datos
    if buffer:
        conn = sqlite3.connect(db_path)
        pd.DataFrame(buffer).to_sql('acceleration_data', conn, if_exists='append', index=False)
        conn.close()
        buffer.clear()

def capture_data(stop_event): # Función para capturar los datos
    setup_database(number_of_sensors)
    data_buffer = []
    start_time = time.time()  # Guardar el tiempo de inicio para controlar la duración de la captura

    with nidaqmx.Task() as task:
        for i in range(number_of_sensors):
            mod = 1 + i // 3
            ai = i % 3
            channel_str = f"{deviceName}Mod{mod}/ai{ai}"
            task.ai_channels.add_ai_accel_chan(channel_str, min_val=min_val, max_val=max_val, units=AccelUnits.METERS_PER_SECOND_SQUARED, sensitivity=sensitivity, sensitivity_units=AccelSensitivityUnits.VOLTS_PER_G)
        task.timing.cfg_samp_clk_timing(original_rate, sample_mode=AcquisitionType.CONTINUOUS, samps_per_chan=buffer_size)

        while not stop_event.is_set(): # Bucle principal de captura
            current_time = time.time()
            if total_capture_time > 0 and (current_time - start_time >= total_capture_time):
                break  # Detener la captura después del tiempo definido
            
            data = np.array(task.read(number_of_samples_per_channel=buffer_size)) * sensitivity
            data = data[:, ::decimation_factor]  # Decimar los datos

            timestamps = pd.date_range(start=pd.Timestamp.now(), periods=len(data[0]), freq=pd.DateOffset(milliseconds=1000/rate)) # Crear marcas de tiempo
            df = pd.DataFrame(data.transpose(), index=timestamps, columns=[f'sensor{i+1}' for i in range(6)])
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'time'}, inplace=True)
            df['time'] = df['time'].apply(lambda x: x.timestamp())
            data_buffer.extend(df.to_dict(orient='records'))

            if len(data_buffer) >= batch_size:
                buffer_to_sqlite(data_buffer, db_path) # Escribir los datos en la base de datos por lotes

    buffer_to_sqlite(data_buffer, db_path, final=True) # Escribir los datos restantes en la base de datos
    print("Data capture complete.")

def main():
    stop_event = threading.Event()
    capture_thread = threading.Thread(target=capture_data, args=(stop_event,))
    capture_thread.start()

    input("Press Enter to stop...\n")
    stop_event.set()
    capture_thread.join()

if __name__ == "__main__":
    main()
