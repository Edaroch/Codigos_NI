import sys
sys.path.append('src')
import time
from threading import Thread
from DataAcquisitionContMultiProc import main as run_data_acquisition
#from ReadData import main as read_data
from SQLtoTXT import main as data_packs
from ChkPaths import check_and_create_paths
from LoadSetupData import load_config
from SetupDatabase import setup_database
# from src.GUIplot import start_gui


def main():
    config = load_config()
    db_path, data_path = check_and_create_paths(config)

    setup_database(db_path, int(config["number_of_sensors"]))
    print("Configuración de la base de datos completa.")

    # Crear hilos para la adquisición de datos y la lectura de datos
    acquisition_thread = Thread(target=run_data_acquisition, args=(config["deviceName"], int(config["total_capture_time"]), int(config["original_rate"]), int(config["decimation_factor"]), float(config["min_val"]), float(config["max_val"]), float(config["sensitivity"]), int(config["buffer_size"]), int(config["number_of_sensors"]), db_path))
    #data_packs_thread = Thread(target=data_packs, args=(int(config["cada"]), int(config["cuanto"]), db_path, data_path))
    # gui_thread = Thread(target=start_gui)

    # Iniciar los hilos
    acquisition_thread.start()
    #data_packs_thread.start()
    # gui_thread.start()

    # Esperar a que los hilos de adquisición y empaque terminen
    acquisition_thread.join()
    #data_packs_thread.join()
    # gui_thread.join()

    read_data(db_path)  # Ejecuta la función main del script de lectura de datos

if __name__ == "__main__":
    main()

