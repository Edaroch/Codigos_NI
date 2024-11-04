import sys
sys.path.append('src')
import time
from threading import Thread, Event  # threading.Event para el manejo de hilos
from DataAcquisitionContMultiProc import run_data_acquisition
from LoadSetupData import load_config, parse_restart_time
from SetupDatabase import get_sensor_numbers, setup_database
from multiprocessing import Event as MPEvent  # multiprocessing.Event para procesos

import warnings
warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)

def main():
    # Cargar configuración desde el archivo SETUP.txt
    config = load_config()
    # Obtener números de sensores
    sensor_numbers, sensor_numbers_all = get_sensor_numbers(config)

    # Configurar la base de datos en MongoDB
    setup_database(config, sensor_numbers)

    # Preparar db_config para pasar a las funciones
    db_config = {
        'db_host': config['db_host'],
        'db_port': int(config['db_port']),
        'db_name': config['db_name'],
        'db_backup_name': config['db_backup_name']  # Nombre de la base de datos de respaldo
    }

    # Leer la variable restart_time desde el archivo de configuración
    restart_time_str = config.get("restart_time", "0")  # Obtener el valor de restart_time desde la configuración
    restart_time_in_seconds = parse_restart_time(restart_time_str)

    # Crear el evento de parada con threading para hilos y con multiprocessing para procesos
    stop_event = Event()  # threading.Event para controlar los hilos
    process_stop_event = MPEvent()  # multiprocessing.Event para controlar los procesos

    def stop_acquisition():
        """Detiene la adquisición cuando el usuario presiona ENTER."""
        input("Presiona ENTER para detener.")
        stop_event.set()
        process_stop_event.set()  # Asegurar que los procesos también se detengan

    # Iniciar un hilo para esperar a que el usuario presione ENTER
    stop_thread = Thread(target=stop_acquisition)
    stop_thread.start()

    while not stop_event.is_set():  # Bucle para reiniciar la adquisición si es necesario
        start_time = time.time()

        # Reiniciar el evento de parada para cada ciclo
        process_stop_event.clear()

        # Iniciar el proceso de adquisición de datos, procesamiento y respaldo
        acquisition_thread = Thread(target=run_data_acquisition, args=(
            config["deviceName"],
            int(config["total_capture_time"]),
            int(config["original_rate"]),
            int(config["decimation_factor"]),
            float(config["min_val"]),
            float(config["max_val"]),
            float(config["sensitivity"]),
            int(config["buffer_size"]),
            sensor_numbers,
            sensor_numbers_all,
            db_config,
            config,
            int(config["backup_time"]),
            restart_time_in_seconds,  # Pasar el restart_time a run_data_acquisition
            process_stop_event  # Pasar el evento de parada para procesos
        ))

        acquisition_thread.start()
        acquisition_thread.join()  # Espera a que termine la ejecución del hilo

        # Si la adquisición se detuvo porque el restart_time expiró o se presionó ENTER
        elapsed_time = time.time() - start_time
        if not stop_event.is_set() and restart_time_in_seconds > 0 and elapsed_time >= restart_time_in_seconds:
            print(f"Reiniciando adquisición después de {restart_time_in_seconds} segundos.")
            time.sleep(1)  # Espera un segundo antes de reiniciar
        else:
            print("El proceso fue detenido manualmente. Terminando.")
            break  # Salir del bucle si se presionó ENTER

    stop_thread.join()  # Asegurarse de que el hilo de entrada finalice correctamente

if __name__ == "__main__":
    main()