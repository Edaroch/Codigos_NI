from nidaqmx import Task
from nidaqmx.constants import AcquisitionType, AccelUnits, AccelSensitivityUnits
import time
from numpy import array, concatenate


def capture_data(data_queue, stop_event, device_name, total_capture_time, frequency_rate, min_val,
                 max_val, sensitivity, buffer_size, sensor_numbers, all_sensor_numbers, config):
    """
    Captures data from the DAQ and places it in the processing queue, adjusting the data
    to match the acquisition frequency and buffer size.
    """

    start_time = time.time()
    number_of_sensors = len(all_sensor_numbers)
    preserve_row = [i in sensor_numbers for i in all_sensor_numbers]
    persistent_buffer_capture = []  # Buffer for leftover samples

    # Samples per packet: about one second, rounded down to a multiple of the decimation factor
    # so each packet decimates to a whole number of samples and the timestamps do not drift.
    decimation_factor = int(config["decimation_factor"])
    total_expected_samples = int(frequency_rate) // decimation_factor * decimation_factor

    with Task() as task:
        for i in range(number_of_sensors):
            mod = 1 + i // 3
            ai = i % 3
            channel_str = f"{device_name}Mod{mod}/ai{ai}"
            task.ai_channels.add_ai_accel_chan(
                channel_str, 
                min_val=min_val, 
                max_val=max_val, 
                units=AccelUnits.METERS_PER_SECOND_SQUARED, 
                sensitivity=sensitivity, 
                sensitivity_units=AccelSensitivityUnits.VOLTS_PER_G
            )
        
        task.timing.cfg_samp_clk_timing(
            frequency_rate,
            sample_mode=AcquisitionType.CONTINUOUS,
            samps_per_chan=buffer_size
        )
        actual_rate = task.timing.samp_clk_rate  # DAQmx may coerce the requested rate
        if abs(actual_rate - frequency_rate) > 0.01:
            print(f"[WARNING] The DAQ samples at {actual_rate:.2f} Hz, not at the configured "
                  f"{frequency_rate:.2f} Hz. Timestamps will drift.")

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
                if len(persistent_buffer_capture):
                    data = concatenate([persistent_buffer_capture, data], axis=1)

                # Send every full packet (a read longer than one packet holds several)
                while data.shape[1] >= total_expected_samples:
                    full_data = data[:, :total_expected_samples]
                    data = data[:, total_expected_samples:]
                    data_queue.put(full_data)

                    if config["debug"]:
                        print(f"Complete packet sent: {full_data.shape}, Remaining data: {data.shape}, Packet time: {current_time - last_time}")
                    last_time = current_time  # Update the time of the last packet

                # Keep the samples that do not fill a packet for the next read
                persistent_buffer_capture = data
                if config["debug"]:
                    print(f"Remaining data in the buffer: {persistent_buffer_capture.shape}")

            except Exception as e:
                print(f"[ERROR] Error capturing data: {e}")    