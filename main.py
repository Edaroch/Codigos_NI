from sys import path
import time
from threading import Thread, Event  # threading.Event para el manejo de hilos
from multiprocessing import Event as MPEvent  # multiprocessing.Event para procesos
import os
path.append('src')

from data_acquisition import run_data_acquisition
from load_setup_data import load_config, parse_restart_time
from setup_database import setup_database, get_sensor_numbers, create_sqlite_path_if_not_exists

import platform
from warnings import filterwarnings
filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)


def main():
    # Load configuration from SETUP.txt
    config = load_config()

    # Ensure SQLite file and its path exist
    sqlite_db_path = config['sqlite_db_path']
    print(sqlite_db_path)
    create_sqlite_path_if_not_exists(sqlite_db_path)

    # Get sensor numbers
    sensor_numbers, sensor_numbers_all = get_sensor_numbers(config)

    # Setup SQLite and MongoDB databases
    setup_database(sqlite_db_path, config, sensor_numbers)

    # Prepare db_config for passing to functions
    db_config = {
        'db_host': config['db_host'],
        'db_port': int(config['db_port']),
        'db_name': config['db_backup_name'],  # Temporary database name
        'db_backup_name': config['db_backup_name']  # Backup database name
    }

    # Read the restart_time variable from the configuration file
    restart_time_str = config.get("restart_time", "0")
    restart_time_in_seconds = parse_restart_time(restart_time_str)

    # Create stop events for threads and processes
    stop_event = Event()  # threading.Event to control threads
    process_stop_event = MPEvent()  # multiprocessing.Event to control processes

    def stop_acquisition():
        print("PRESS ENTER TO STOP (or wait for STOP.txt)")

        if platform.system() == "Windows":
            from msvcrt import kbhit, getch
            while not stop_event.is_set():
                if kbhit() and getch() == b'\r':  # ENTER key
                    stop_event.set()
                    process_stop_event.set()
                    break
                time.sleep(0.1)
        else:
            from sys import stdin
            from select import select
            while not stop_event.is_set():
                if stdin in select([stdin], [], [], 1)[0]:
                    _ = stdin.readline()
                    stop_event.set()
                    process_stop_event.set()
                    break

    def check_stop_file():
        """Verifies if STOP.txt exists to stop the acquisition."""
        while not stop_event.is_set():
            if os.path.exists("STOP.txt"):
                print("🛑 STOP.txt detected. Stopping acquisition.")
                stop_event.set()
                process_stop_event.set()
                try:
                    os.remove("STOP.txt")
                except Exception as e:
                    print(f"Warning: could not delete STOP.txt -> {e}")
                break
            time.sleep(1)

    # Start a thread to wait for the user to press ENTER
    stop_thread = Thread(target=stop_acquisition)
    stop_thread.start()

    file_stop_thread = Thread(target=check_stop_file)
    file_stop_thread.start()

    while not stop_event.is_set():  # Loop to restart acquisition if necessary
        start_time = time.time()

        # Reset the stop event for each cycle
        process_stop_event.clear()

        # Start the data acquisition, processing, and backup process
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
        acquisition_thread.join()  # Wait for the thread to finish

        # If acquisition stopped because restart_time expired or ENTER was pressed
        elapsed_time = time.time() - start_time
        if not stop_event.is_set() and restart_time_in_seconds > 0 and elapsed_time >= restart_time_in_seconds:
            print(f"Restarting the capture after {restart_time_in_seconds} seconds.")
            time.sleep(1)  # Wait a second before restarting
        else:
            print("All process were stopped manually.")
            break

    stop_thread.join()  # Ensure the stop thread finishes
    file_stop_thread.join()  # Ensure the file check thread finishes

if __name__ == "__main__":
    main()
