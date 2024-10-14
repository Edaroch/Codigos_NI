## Project Description

This project handles the data acquisition from seismic sensors through a National Instruments (NI) DAQ system. The sensor data is captured and stored in a SQLite database, with functionality to export selected data spans to text files as per user requirements. Additionally, the system dynamically adjusts the decimation factor to match a user-defined target frequency, ensuring efficient data handling and storage.

## Installation and Setup

1. Clone the repository to your local machine.
2. Install the NI-DAQmx software (version ni-daqmx_24.3), ensuring you choose the option for hardware recognition during setup.
3. Set up your environment using Python 3.10.
4. Install required Python packages from `requirements.txt`.
5. Verify the configurations in `SETUP.txt`.

## Folder Structure

- **src/**: Contains the Python modules for the project.
- **data/**: Stores text files with sensor data.
- **Accelerations/**: Houses the SQLite database (`acelerations.db`) used for persistent storage of sensor data.

## Files

- **.gitattributes**: Git configuration file that ensures consistent handling of line endings across various operating systems.
- **main.py**: Main entry point for the data acquisition system.
- **SETUP.txt**: Centralizes all configuration parameters for the application.
- **GUIplot.py**: Provides a GUI for real-time visualization of accelerations, and facilitates data and figure export.

## Classes

- **CheckResources.py**: Monitors and reports on computer resource utilization.
- **DataAcquisitionContMultiProc.py**: Manages data capture from sensors through the DAQ system, with support for dynamic decimation based on the target frequency defined in `SETUP.txt`.
- **ChkPaths.py**: Ensures that the SQL database and data directories are present as defined in `SETUP.txt`; creates them if they are not.
- **LoadSetupData.py**: Loads configuration settings from `SETUP.txt`.
- **SetupDatabase.py**: Setup the database with the table `acceleration_data` each row are designed `time` and `sensor1`, `sensor2`, etc... depending on the number of sensors in `SETUP.txt`

## Configuration

The `SETUP.txt` file contains critical configuration settings for the data acquisition system, including:
- **deviceName**: The name of the NI DAQ device.
- **total_capture_time**: Thetotal duration for data capture (in seconds)
- **original_rate**: The initial sampling rate from the sensors.
- **decimation_frec**: The target frequency after dynamic decimation (e.g., 20 Hz).
- **buffer_size**: The size of the data buffer for acquisition.
- **db_fold**: Path to store the SQLite database.
- **buffer_flush_interval**: Interval (in seconds) to flush the data buffer to the SQLite database.

## Dynamic Decimation

The system dynamically adjusts the decimation factor to maintain the target frequency (decimation_frec) as defined in `SETUP.txt`. This ensures that the frequency of data stored in the database is consistent, even if the rate of data reception varies.

## Usage

1. Execute `main.py`.
2. To terminate the program, press ENTER multiple times as needed.

## Dependencies

- **NI-MAX**: Necessary for installing drivers for the NI hardware. Ensure that the DAQ is properly configured using this software before starting; verify that the device is detectable by the software and confirm that the device name is correctly entered into the `SETUP.txt` file.
- **SQLite**: The project uses SQLite as the database for storing sensor data.
- **Python Packages**: Install required Python packages using `pip install -r requirements.txt`.


