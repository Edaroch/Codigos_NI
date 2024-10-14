import sys
sys.path.append('src')
import time
from threading import Thread
from DataAcquisitionContMultiProc import main as run_data_acquisition
from ChkPaths import check_and_create_paths
from LoadSetupData import load_config
from SetupDatabase import get_sensor_numbers, setup_database

def main():
    config = load_config()
    db_path = check_and_create_paths(config)
    sensor_numbers, sensor_numbers_all = get_sensor_numbers(config)

    setup_database(db_path, sensor_numbers)

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
        db_path,
        config  
    ))

    acquisition_thread.start()
    acquisition_thread.join()

if __name__ == "__main__":
    main()