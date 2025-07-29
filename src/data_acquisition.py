""" 
Code to capture data from N acceleration sensors using an NI cDAQ9185 device with NI 9230 modules.
The code captures acceleration data from N sensors over a specified time interval and stores it in a user-defined buffer according to the DAQ's capacity.
It then transfers the data to a MongoDB database along with its corresponding UNIX timestamp.
The code also allows manual data capture stopping by pressing ENTER.
It uses multiprocessing for parallel data capture and processing.
Data processing not only decimates the data but also rounds it to 5 decimal places and adds the UNIX timestamp.
Python 3.10.9
"""

import time
from multiprocessing import Process, Queue
from capture_data import capture_data
from process_data import process_data
from data_handling import backup_data  # Importar la función para manejar el buffer y la base de datos
from setup_database import close_mongodb_client

def run_data_acquisition(deviceName, total_capture_time, original_rate, decimation_factor, 
                         min_val, max_val, sensitivity, buffer_size, sensor_numbers, 
                         sensor_numbers_all, sqlite_db_path, db_config, config, 
                         backup_time, restart_time_in_seconds, stop_event):
    """
    Main function to start data acquisition with the configured settings.
    """
    start_time = time.time()
    data_queue = Queue()
    persistent_buffer = []  # Buffer persistente para datos excedentes

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
        config["backup_time"],   # Tiempo de respaldo (en segundos)
        persistent_buffer,  # Buffer persistente para datos excedentes
        total_capture_time  # Tiempo total de captura
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