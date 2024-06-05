## Project Description

This project handles the data acquisition from seismic sensors through a National Instruments (NI) DAQ system. The sensor data is captured and stored in a SQLite database, with functionality to export selected data spans to text files as per user requirements.

## Installation and Setup

1. Clone the repository to your local machine.
2. Install the NI-DAQmx software (version ni-daqmx_24.3), ensuring you choose the option for hardware recognition during setup.
3. Set up your environment using Python 3.10.
4. Install required Python packages from `requirements.txt`.
5. Verify the configurations in `SETUP.txt`.

## Folder Structure

- **src/**: Contains the Python modules for the project.
- **data/**: Stores text files with sensor data.
- **Accelerations/**: Houses the SQLite database (`aceleraciones.db`) used for persistent storage of sensor data.

## Files

- **.gitattributes**: Git configuration file that ensures consistent handling of line endings across various operating systems.
- **main.py**: Main entry point for the data acquisition system.
- **SETUP.txt**: Centralizes all configuration parameters for the application.
- **GUIplot.py**: Provides a GUI for real-time visualization of accelerations, and facilitates data and figure export.

## Classes

- **CheckResources.py**: Monitors and reports on computer resource utilization.
- **DataAcquisitionContMultiProc.py**: Manages data capture from sensors through the DAQ system.
- **SQLtoTXT.py**: Periodically exports data from the SQLite database to a .txt file based on user-defined intervals.
- **ReadData.py**: Reads data from the database and logs the last three entries, total number of entries, and sampling frequency to a text file in the root directory.
- **ChkPaths.py**: Ensures that the SQL database and data directories are present as defined in `SETUP.txt`; creates them if they are not.
- **LoadSetupData.py**: Loads configuration settings from `SETUP.txt`.
- **SetupDatabase.py**: Setup the database with the table `acceleration_data` each row are designed `time` and `sensor1`, `sensor2`, etc... depending on the number of sensors in `SETUP.txt`

## Usage

1. Execute `main.py`.
2. To terminate the program, press ENTER multiple times as needed.

## Dependencies

- **NI-MAX**: Necessary for installing drivers for the NI hardware. Ensure that the DAQ is properly configured using this software before starting; verify that the device is detectable by the software and confirm that the device name is correctly entered into the `SETUP.txt` file.


