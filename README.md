## Project Description

This project enables real-time data acquisition from multiple seismic sensors using a National Instruments (NI) DAQ system (e.g., cDAQ9185 with NI 9230 modules). The system supports high-speed data capture, efficient buffering with SQLite, and scalable long-term storage in MongoDB. Configuration is handled via a flexible `SETUP.txt` file, and interaction is provided through two GUIs for acquisition and data checking/analysis (PSD and SVD).

---

## Architecture

### Database Structure

1. **SQLite (Buffer)**:
   - Temporary local storage for high-speed sensor data.
   - Fast access for real-time operations.
   - Schema:
     - `timestamps`: UNIX timestamps of each acquisition.
     - `sensors`: Metadata (sensor numbers).
     - `accelerations`: Acceleration values linked to timestamps and sensors.

2. **MongoDB (Historical Storage)**:
   - Long-term archival of data backed up from SQLite.
   - Schema:
     - `sensors`: Metadata (like SQLite).
     - `accelerations`: Documents grouped by timestamp.

---

## Installation and Setup

1. Clone the repository.
2. Install **NI-DAQmx** (tested with version `ni-daqmx_24.3`). Enable hardware recognition.
3. Run `INSTALL.bat` to:
   - Create a Python 3.10 virtual environment.
   - Install all Python dependencies via `requirements.txt`.
4. Configure acquisition settings via `SETUP.txt`.

---

## Workflow

1. **Capture**:
   - `main.py` coordinates parallel processes: DAQ capture, signal decimation, and data backup.

2. **Buffering**:
   - Data is stored in SQLite with WAL mode enabled.
   - Reduces disk access while keeping quick access to recent data.

3. **Backup**:
   - Automatic periodic backup to MongoDB every `backup_time` seconds.
   - Old SQLite records are removed post-backup to preserve space.

4. **Visualization & Control**:
   - `GUI.py`: Main GUI for editing config and launching acquisition.
   - `GUI_check.py`: GUI for post-analysis using PSD and SVD computed from JSON.

---

## Folder Structure

```
<root>/
├── main.py
├── SETUP.txt
├── INSTALL.bat / RUNGUI.bat / RUNMAIN.bat
├── requirements.txt
├── README.md
├── src/
│   ├── capture_data.py
│   ├── data_acquisition.py
│   ├── data_handling.py
│   ├── process_data.py
│   ├── setup_database.py
│   ├── load_setup_data.py
│   ├── utils.py
│   ├── GUI.py
│   └── GUI_check.py
```

---

## Key Configuration Parameters (`SETUP.txt`)

- **DAQ Settings**:
  - `deviceName`: NI DAQ name from NI-MAX.
  - `original_rate`: Raw sampling rate (Hz).
  - `buffer_size`: DAQ buffer (samples).
  - `decimation_factor`: Downsampling factor.
  - `daq_num_modules`: Number of NI-9230 modules.
  - `daq_ch_per_module`: Channels per module (typically 3).
  - `unused_ch`: e.g., `nan` or `21, 22`.

- **Sensor Specs**:
  - `min_val`, `max_val`: Expected signal range.
  - `sensitivity`: Sensor sensitivity (e.g., 0.5 V/g).

- **Database**:
  - `db_path`, `sqlite_name`: Local SQLite buffer.
  - `db_host`, `db_port`, `db_backup_name`: MongoDB settings.
  - `backup_time`: Seconds between SQLite → MongoDB backups.

- **Capture Logic**:
  - `total_capture_time`: Duration (0 = infinite).
  - `restart_time`: Restart interval (e.g., `10s`, `1h`, `0s`).
  - `debug`: Enables verbose console output.

---

## Features

- ✅ **Real-Time DAQ Integration**
- ✅ **Configurable with GUI** (`GUI.py`)
- ✅ **Modular Multiprocessing**
- ✅ **Live SQLite Buffer + MongoDB Archive**
- ✅ **Automated Backup Engine**
- ✅ **PSD & SVD Analysis via `GUI_check.py`**
- ✅ **Cross-platform (Windows/Linux, with Python 3.10)**

---

## Usage

### 🖥️ GUI
- Run `RUNGUI.bat` to launch config interface (`GUI.py`).
- Press `Run Acquisition` to launch `main.py` in a new console.

### 🛠️ Command-line
- Run `RUNMAIN.bat` to start the acquisition process directly.

### ⏹️ Stopping
- Press ENTER in the acquisition console, then close it manually or press  `Stop Acquisition` in GUI.

---

## Dependencies

- NI DAQmx (tested with `ni-daqmx_24.3`)
- MongoDB (optional but recommended)
- Python 3.10
- Required packages:
  ```bash
  pip install -r requirements.txt
  ```

---

## Notes

- If MongoDB is unavailable, data remains in SQLite.
- The `GUI_check.py` uses `psd_results.json` created by `utils.py` to visualize Power Spectral Densities and Singular Value Decompositions.
- Designed for extensibility: supports additional analysis modules, REST API endpoints, and future web integration.

---

## Authors

- Developed by Emilio Daroch (University of Granada, 2024–2025) for the **Hospital Real Seismic Monitoring System** as part of a cognitive SHM platform in the BUILDCHAIN project.