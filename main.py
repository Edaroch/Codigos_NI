from sys import path
import time
from threading import Thread, Event  # threading.Event para el manejo de hilos
from multiprocessing import Event as MPEvent  # multiprocessing.Event para procesos

path.append('src')

from data_acquisition import run_data_acquisition
from load_setup_data import load_config, parse_restart_time
from setup_database import setup_database, get_sensor_numbers, create_sqlite_path_if_not_exists

from warnings import filterwarnings
filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)


def main():
    # Cargar configuración desde el archivo SETUP.txt
    config = load_config()

    # Asegurar que el archivo SQLite y su ruta existan
    sqlite_db_path = config['sqlite_db_path']
    print(sqlite_db_path)
    create_sqlite_path_if_not_exists(sqlite_db_path)

    # Obtener números de sensores
    sensor_numbers, sensor_numbers_all = get_sensor_numbers(config)

    # Configurar la base de datos SQLite y MongoDB
    setup_database(sqlite_db_path, config, sensor_numbers)

    # Preparar db_config para pasar a las funciones
    db_config = {
        'db_host': config['db_host'],
        'db_port': int(config['db_port']),
        'db_name': config['db_backup_name'],  # Nombre de la base de datos temporal
        'db_backup_name': config['db_backup_name']  # Nombre de la base de datos para respaldo
    }

    # Leer la variable restart_time desde el archivo de configuración
    restart_time_str = config.get("restart_time", "0")
    restart_time_in_seconds = parse_restart_time(restart_time_str)

    # Crear eventos de parada para hilos y procesos
    stop_event = Event()  # threading.Event para controlar los hilos
    process_stop_event = MPEvent()  # multiprocessing.Event para controlar los procesos

    def stop_acquisition():
        """Detiene la adquisición cuando el usuario presiona ENTER."""
        input("PRESS ENTER TO STOP")
        stop_event.set()
        process_stop_event.set()

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
            sqlite_db_path,
            db_config,
            config,
            int(config["backup_time"]),
            restart_time_in_seconds,
            process_stop_event
        ))

        acquisition_thread.start()
        acquisition_thread.join()  # Espera a que termine la ejecución del hilo

        # Si la adquisición se detuvo porque el restart_time expiró o se presionó ENTER
        elapsed_time = time.time() - start_time
        if not stop_event.is_set() and restart_time_in_seconds > 0 and elapsed_time >= restart_time_in_seconds:
            print(f"Restarting the capture after {restart_time_in_seconds} seconds.")
            time.sleep(1)  # Espera un segundo antes de reiniciar
        else:
            print("All process were stopped manually.")
            break

    stop_thread.join()  # Asegurarse de que el hilo de entrada finalice correctamente


if __name__ == "__main__":
    main()
