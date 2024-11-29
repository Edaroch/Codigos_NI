## Project Description

This project enables data acquisition from seismic sensors through a National Instruments (NI) DAQ system. Data is initially stored in an SQLite database as a buffer and then periodically transferred to a MongoDB database for long-term storage. This architecture provides robust and efficient data handling, supporting both real-time monitoring and historical data analysis. The configuration is managed via a flexible `SETUP.txt` file, allowing users to define acquisition parameters, buffer sizes, and backup intervals.

---

## Architecture

### Database Structure

1. **SQLite (Buffer)**:
   - Acts as a temporary storage for sensor data.
   - Provides fast, local access for real-time data handling.
   - Data is stored in three tables:
     - `timestamps`: Records the timestamp of each data point.
     - `sensors`: Contains metadata about sensors (e.g., sensor number).
     - `accelerations`: Stores acceleration values linked to timestamps and sensors.

2. **MongoDB (Backup and Historical Storage)**:
   - Stores processed data transferred from SQLite.
   - Two collections:
     - `sensors`: Metadata about sensors, similar to the SQLite `sensors` table.
     - `accelerations`: Historical acceleration data with timestamps, optimized for long-term querying.
   - Ensures scalability and allows integration with advanced analytical tools.

---

## Installation and Setup

1. Clone the repository to your local machine.
2. Ensure the **NI-DAQmx** software (version `ni-daqmx_24.3`) is installed. During setup, select the option for hardware recognition.
   - **Note**: If NI-DAQmx is not installed, install it before proceeding. You will be prompted during the setup process to confirm its installation.
3. Navigate to the project directory and run `INSTALL.bat` to:
   - Create a Python 3.10 virtual environment (`.venv`).
   - Install required Python packages from `requirements.txt`.
4. Verify and edit the configurations in `SETUP.txt` as needed.

---

## Workflow

1. **Data Acquisition**:
   - Sensor data is captured via the NI DAQ system.
   - The data is initially stored in SQLite as a buffer to ensure high-speed local operations.

2. **Buffer Management**:
   - SQLite acts as a first-in, first-out (FIFO) buffer.
   - Data in SQLite is periodically processed and transferred to MongoDB for long-term storage.

3. **Backup to MongoDB**:
   - A backup process transfers data from SQLite to MongoDB in manageable batches (e.g., 20,000 timestamps per batch).
   - Once backed up, the corresponding data is deleted from SQLite to free up buffer space.

4. **Configuration**:
   - Users can customize acquisition intervals, buffer sizes, and backup intervals in `SETUP.txt`.

---

## Folder Structure

- **src/**: Contains the core Python modules for the project.
- **MongoDB/**: Stores MongoDB configuration files and scripts.

---

## Files

- **.gitattributes**: Ensures consistent line endings across operating systems.
- **main.py**: Main script for data acquisition, buffer management, and backups.
- **SETUP.txt**: Central configuration file for acquisition and database settings.
- **interface.py**: Graphical User Interface (GUI) for managing configurations and running the system.
- **INSTALL.bat**: Script for setting up the environment and dependencies.
- **RUNGUI.bat**: Script to launch the GUI (`interface.py`).
- **RUNMAIN.bat**: Script to run the main acquisition process (`main.py`).

---

## Classes and Scripts

- **DataAcquisitionContMultiProc.py**: Manages sensor data acquisition and real-time storage in SQLite.
- **ChkPaths.py**: Ensures that required directories and database configurations exist as defined in `SETUP.txt`.
- **LoadSetupData.py**: Loads and parses configuration settings from `SETUP.txt`.
- **SetupDatabase.py**: Configures SQLite tables and MongoDB collections for efficient data handling.

---

## Configuration

The `SETUP.txt` file defines the project's behavior. Key parameters include:

- **DAQ Settings**:
  - `deviceName`: Name of the NI DAQ device.
  - `original_rate`: Initial sampling rate from sensors (in Hz).
  - `buffer_size`: Buffer size for each acquisition session.
  - `decimation_factor`: Decimation factor to reduce the sampling rate.
  - `daq_num_modules`: Number of nodules connecter to the DAQ, please use the bay in order, do not skip bays.
  - `daq_ch_per_module`: Number of channels for module DAQ.
  - `unused_ch`: 2 options: nan (all channels used) / two digits seppared by a comma (eg: 21, 22) where ij: i-> module number; j-> channel number starting by 0.
- **Database Settings**:
  - `db_host`: MongoDB host address.
  - `db_port`: MongoDB port.
  - `sqlite_db_path`: Path to the SQLite buffer database including the name of the database.
  - `db_backup_name`: MongoDB database for long-term storage.
  - `backup_time`: Interval (in seconds) for transferring data from SQLite to MongoDB, use 0 to disable the backup and store data only in SQLite3 database.
- **Timing**:
  - `total_capture_time`: Total duration for data capture (0 for continuous capture).
  - `restart_time`: Interval for restarting the acquisition process (e.g., 0 for continuous, 10s for ten seconds, 1d for one day).
- **Sensor Limits**:
  - `min_val`: Minimum expected sensor reading.
  - `max_val`: Maximum expected sensor reading.
  - `sensitivity`: Sensibility if the seismic sensor.

---

## Features

1. **Real-Time Data Acquisition**:
   - Captures data from seismic sensors via NI DAQ and stores it in SQLite for fast local access.
2. **Efficient Backup Process**:
   - Transfers buffered data from SQLite to MongoDB in batches, ensuring scalability for long-term storage.
3. **Customizable Configuration**:
   - Easily adjust acquisition intervals, buffer sizes, and backup frequencies through `SETUP.txt`.
4. **Interactive GUI**:
   - The `interface.py` script provides an easy-to-use interface for managing configurations and starting/stopping the system.
5. **Robust Error Handling**:
   - Automatically handles database connection issues and retries failed operations.
6. **Modular Architecture**:
   - Supports future scalability and integration with advanced analytics tools.

---

## Usage

1. **Graphical Interface**:
   - Run `RUNGUI.bat` to launch the GUI and manage configurations or start the acquisition process.
2. **Command Line**:
   - Execute `RUNMAIN.bat` to start the main acquisition process.
3. **Stopping the Acquisition**:
   - Press ENTER in the console running the acquisition process, then close the console manually.

---

## Notes

- If MongoDB is not installed or cannot connect, the system will skip the backup process and continue capturing data in SQLite.
- Use `SETUP.txt` to configure the acquisition system before starting.
- Ensure proper NI DAQ and MongoDB setups for optimal performance.

---

## Dependencies

- **NI-MAX**: Required for configuring the NI hardware and ensuring proper DAQ operation.
- **MongoDB**: Used for long-term data storage and historical analysis.
- **SQLite**: Serves as a local buffer database for real-time data.
- **Python Packages**:
  - Install all dependencies using:
    ```bash
    pip install -r requirements.txt
    ```
