from nidaqmx import Task
from nidaqmx.constants import AcquisitionType, AccelUnits, AccelSensitivityUnits
import time
from numpy import array, concatenate


def capture_data(data_queue, stop_event, deviceName, total_capture_time, original_rate, min_val,
                 max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, config):
    """
    Captures data from the DAQ and places it in the processing queue, adjusting the data
    to match the acquisition frequency and buffer size.
    """

    start_time = time.time()
    number_of_sensors = len(all_sensor_numbers)
    preserve_row = [i in sensor_numbers for i in all_sensor_numbers]
    persistent_buffer_capture = []  # Buffer for leftover samples

    # Samples expected per second
    total_expected_samples = int(original_rate * 1)  # Samples expected in 1 second

    with Task() as task:
        for i in range(number_of_sensors):
            mod = 1 + i // 3
            ai = i % 3
            channel_str = f"{deviceName}Mod{mod}/ai{ai}"
            task.ai_channels.add_ai_accel_chan(
                channel_str, 
                min_val=min_val, 
                max_val=max_val, 
                units=AccelUnits.METERS_PER_SECOND_SQUARED, 
                sensitivity=sensitivity, 
                sensitivity_units=AccelSensitivityUnits.VOLTS_PER_G
            )
        
        task.timing.cfg_samp_clk_timing(
            original_rate, 
            sample_mode=AcquisitionType.CONTINUOUS, 
            samps_per_chan=buffer_size
        )

        last_time = start_time

        while not stop_event.is_set():
            current_time = time.time()

            # Check the total capture time
            if total_capture_time > 0 and (current_time - start_time >= total_capture_time):
                stop_event.set()
                break

            try:
                # Read data from the DAQ
                data = array(task.read(number_of_samples_per_channel=buffer_size))
                data = data[preserve_row, :]  # Keep only the selected sensors
                
                # Combine leftover samples with the new ones
                if persistent_buffer_capture:
                    data = concatenate([persistent_buffer_capture, data], axis=1)

                # Check whether there are enough samples for a full packet
                if data.shape[1] >= total_expected_samples:
                    # Take one full packet
                    full_data = data[:, :total_expected_samples]
                    
                    # Keep the remaining samples in the persistent buffer
                    persistent_buffer_capture = data[:, total_expected_samples:]
                    
                    # Send the packet to the queue
                    data_queue.put(full_data)

                    if config["debug"]:
                        print(f"Complete packet sent: {full_data.shape}, Remaining data: {persistent_buffer_capture.shape}, Packet time: {current_time - last_time}")
                    last_time = current_time  # Update the time of the last packet
                else:
                    # Not enough samples for a packet: keep everything in the persistent buffer
                    persistent_buffer_capture = data

                    if config["debug"]:
                        print(f"Remaining data in the buffer: {persistent_buffer_capture.shape}")

            except Exception as e:
                print(f"[ERROR] Error capturing data: {e}")    