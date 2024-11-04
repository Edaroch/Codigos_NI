## Project Description

This project handles the data acquisition from seismic sensors through a National Instruments (NI) DAQ system. Sensor data is captured and stored in a MongoDB database for real-time monitoring, with a backup system that transfers buffered data to a raw database for long-term storage. The system dynamically adjusts the decimation factor to match a user-defined target frequency, ensuring efficient data handling and storage. Additionally, users can configure acquisition times, buffer sizes, and backup intervals through a configurable `SETUP.txt` file.

## Installation and Setup

1. Clone the repository to your local machine.
2. Install the NI-DAQmx software (version ni-daqmx_24.3), ensuring you choose the option for hardware recognition during setup.
3. Set up your environment using Python 3.10.
4. Install required Python packages from `requirements.txt`.
5. Verify the configurations in `SETUP.txt`.

## Folder Structure

- **src/**: Contains the Python modules for the project.
- **MongoDB/**: Houses the MongoDB database used for persistent storage of sensor data.

## Files

- **.gitattributes**: Git configuration file that ensures consistent handling of line endings across various operating systems.
- **main.py**: Main entry point for the data acquisition system, responsible for initializing the data acquisition, processing, and backup workflows.
- **SETUP.txt**: Central configuration file for the application, controlling DAQ settings, backup intervals, and database configurations.
- **interface.py**: GUI for managing configuration settings and executing `main.py` directly from the interface.

## Classes

- **DataAcquisitionContMultiProc.py**: Manages data capture from sensors through the DAQ system, handles real-time decimation, and manages data storage into MongoDB.
- **ChkPaths.py**: Ensures that the necessary directories and MongoDB databases are available as defined in `SETUP.txt`; creates them if they are not.
- **LoadSetupData.py**: Loads configuration settings from `SETUP.txt`.
- **SetupDatabase.py**: Initializes MongoDB collections for buffering real-time data.

## Configuration

The `SETUP.txt` file contains critical configuration settings for the data acquisition system, including:
- **deviceName**: The name of the NI DAQ device.
- **total_capture_time**: The total duration for data capture (in seconds, or 0 for continuous capture).
- **original_rate**: The initial sampling rate from the sensors (in Hz).
- **decimation_factor**: Factor by which to reduce the sampling rate for long-term storage.
- **buffer_size**: The size of the buffer for each acquisition session.
- **db_host**: MongoDB host address.
- **db_port**: MongoDB port.
- **db_name**: The MongoDB database for real-time data storage.
- **db_backup_name**: The MongoDB database for long-term storage (backup).
- **backup_time**: Interval (in seconds) for backing up buffered data to the long-term storage database.
- **restart_time**: Defines the interval for restarting the acquisition process (0 for continuous acquisition, 10s for every ten seconds, 1d for every day, etc.).


## Decimation

The system ensure that the data stored in the MongoDB database reflects the intended sampling rate, even if the rate of data reception varies. The buffered data is then periodically backed up to a raw database, with the ability to process data in configurable chunks to avoid overloading the database during large data captures.

- **Backup Handling**: Data from the buffer is backed up in batches (default 50000 records per batch) and subsequently deleted from the buffer to free space.
- **Error Handling**: The system retries failed database operations and provides debug information if enabled in `SETUP.txt`.

## Usage

1. Execute `main.py`.
2. You can also use `interface.py` for a graphical user interface to manage configuration and start/stop the acquisition process.
3. To terminate the acquisition process, press ENTER when prompted in the console.

## Dependencies

- **NI-MAX**: Necessary for installing drivers for the NI hardware. Ensure that the DAQ is properly configured using this software before starting; verify that the device is detectable by the software and confirm that the device name is correctly entered into the `SETUP.txt` file.
- **SQLite**: The project uses SQLite as the database for storing sensor data.
- **Python Packages**: Install required Python packages using `pip install -r requirements.txt`.

## Features
1. Real-time data acquisition from seismic sensors via NI DAQ.
2. Decimation to reduce data load while maintaining relevant data for long-term storage.
3. MongoDB integration for storing sensor data, with a backup system to transfer data from a temporary buffer to a long-term database.
4. Configurable acquisition intervals, backup times, and buffer sizes via SETUP.txt.
5. Interactive GUI (interface.py) for managing configuration settings and executing the acquisition process directly.
