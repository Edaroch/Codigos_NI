from numpy import array
from pandas import DataFrame
from colorama import Fore, Style
import queue
import time
from data_handling import buffer_to_db
from scipy.signal import decimate



def process_data(data_queue, stop_event, total_capture_time, original_rate, decimation_factor, sensor_numbers, sqlite_db_path, config, buffer_size):
    """
    Processes captured data and sends it to the SQLite database as a buffer.
    """
    persistent_buffer = []
    packet_count = 0
    queue_time = 0
    decimated_rate = original_rate // decimation_factor
    interval = 1 / decimated_rate
    last_timestamp = None

    # Check that config is a dictionary
    if not isinstance(config, dict):
        raise ValueError("The argue 'config' must be a dictionary.")

    while not stop_event.is_set():
        if total_capture_time > 0 and packet_count >= total_capture_time:
            break

        try:
            while not data_queue.empty():
                packet_start_time = time.time()
                if config["debug"]:
                    print(Fore.GREEN + f"------------------NEW PACKAGE--------------------"+ Style.RESET_ALL)
                    print(f"1) Initial real-time {packet_start_time}.")
                try:
                    raw_data = data_queue.get_nowait()
                except queue.Empty:
                    break
                packet_count += 1
                data = array([decimate(channel, decimation_factor, zero_phase=True) for channel in raw_data])

                if config["debug"]:
                    print(f"2) Shape {data.shape} processed. - {time.time()}")
                    if data_queue.qsize() > 0:
                        print(Fore.RED + f"3) Current size of data_queue {data_queue.qsize()}"+ Style.RESET_ALL)
                    else:
                        print(Fore.GREEN + f"3) Current size of data_queue {data_queue.qsize()}"+ Style.RESET_ALL)

                if last_timestamp is None:
                    timestamps = [packet_start_time + i * interval for i in range(len(data[0]))]
                else:
                    expected_first_timestamp = last_timestamp + interval
                    timestamps = [expected_first_timestamp + i * interval for i in range(len(data[0]))]

                last_timestamp = timestamps[-1]

                df = DataFrame(data.transpose(), index=timestamps, columns=[f'{i}' for i in sensor_numbers])
                df.reset_index(inplace=True)
                df.rename(columns={'index': 'time'}, inplace=True)

                if config["debug"]:
                    print(f"4) Packet number {packet_count} processed.")
                    print(f"5) Timestamps for packet {packet_count}: from {timestamps[0]} to {timestamps[-1]}")

                persistent_buffer.extend(df.to_dict(orient='records'))

                # Group the data before sending it to SQLite3, to avoid many small inserts
                if len(persistent_buffer) >= buffer_size/decimation_factor:
                    buffer_to_db(persistent_buffer, sqlite_db_path, config)  # Use SQLite3 as the buffer
                    persistent_buffer = []

                real_time_now = time.time()
                if config["debug"]:
                    print(f"6) Final real-time {real_time_now} and real-time duration {(real_time_now - packet_start_time)}.")

                # Work out how long to wait
                waiting_time = (last_timestamp - timestamps[0] + interval - (real_time_now - packet_start_time)) #
                if config["debug"]:
                    print(f"7) Required waiting time: {waiting_time:.5f} seconds.")
                    print(f"8) Processing time so far: {real_time_now - packet_start_time} seconds.")
                    print(f"9) Total time between packets: {waiting_time + (real_time_now - packet_start_time)} seconds.")

                # Sleep only if the waiting time is positive
                if waiting_time > 0 :
                    if data_queue.qsize() > 0:
                        time.sleep(0.01)
                        queue_time += abs(real_time_now - packet_start_time)
                    else:
                        time.sleep(abs(waiting_time) + abs(queue_time))
                        queue_time = 0    
                        
                real_time_now = time.time()
                time_difference = (real_time_now - last_timestamp - interval) # Difference against the real elapsed time
                if config["debug"]:
                    print(f"10) Real-time difference: {time_difference:.5f} seconds. DELAY (+), ADVANCE (-).")

            time.sleep(0.01)    
                
        except queue.Empty:
            continue