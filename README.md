# Hospital Real Seismic Monitoring System

Real-time acquisition of acceleration data from multiple seismic sensors using a
National Instruments DAQ (cDAQ9185 / cDAQ9189 with NI 9230 modules). Data is
captured at high rate, decimated, buffered in SQLite and archived in MongoDB.
Configuration lives in `SETUP.txt`; two Tkinter GUIs cover acquisition control
and frequency-domain checking (PSD / SVD).

> **Branches** — `production` is the deployed code; `main` is development.
> Deploy from `production` only.

---

## Architecture

### Database structure

1. **SQLite (buffer)** — temporary local storage for high-speed sensor data,
   WAL mode enabled.
   - `timestamps`: UNIX timestamp of each sample.
   - `sensors`: sensor numbers (`10*module + channel`).
   - `accelerations`: values linked to a timestamp and a sensor.

2. **MongoDB (historical storage)** — long-term archive of data backed up from
   SQLite, then purged from SQLite to keep the buffer small.
   - `sensors`: same metadata as SQLite.
   - `accelerations`: one document per timestamp with a `sensor_data` array.

---

## Installation

1. Install **NI-DAQmx** (tested with `ni-daqmx_24.3`) and confirm the device is
   visible in NI MAX.
2. Install **Python 3.10** and, optionally, **MongoDB**.
3. Clone the repository and switch to the deployed branch:
   ```bat
   git clone <repo-url>
   cd Codigos_NI
   git checkout production
   ```
4. Create the virtual environment and install the dependencies:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   deactivate
   ```
5. Adjust the acquisition settings in `SETUP.txt` (or from the GUI).

---

## Usage

All commands are run **from the repository root** — every path in the code is
relative to it.

| Action | Command |
| --- | --- |
| Control panel GUI | `RUNGUI.bat` (or `python src\GUI.py`) |
| Acquisition without GUI | `RUNMAIN.bat` (or `python src\main.py`) |
| Check GUI (PSD / SVD) | `python src\GUI_check.py`, or the *Check Data* button |
| Verify the installation | `python test_smoke.py` |
| Inspect MongoDB for duplicates | `python control\check_mongo_db.py` |

### Stopping an acquisition

- Press **ENTER** in the acquisition console, **or**
- Press **Stop Acquisition** in the GUI (writes a `STOP.txt` the acquisition
  polls once per second and then deletes).

---

## Workflow

1. **Capture** — `src/main.py` loads `SETUP.txt`, prepares the databases and
   starts `run_data_acquisition`, which spawns three processes: DAQ capture,
   decimation/timestamping, and backup.
2. **Buffering** — processed packets are written to SQLite in batches.
3. **Backup** — every `backup_time` seconds the SQLite rows are moved to
   MongoDB and deleted locally. `backup_time: 0` disables backups and keeps all
   data in SQLite.
4. **Restart** — if `restart_time` is non-zero the whole acquisition cycle is
   restarted at that interval, which bounds any accumulated drift.
5. **Analysis** — `GUI_check.py` calls `utils.py` to export the last 30 s from
   SQLite to `last_seconds.json`, computes PSD and SVD into `psd_results.json`
   and plots them.

---

## Folder structure

```
<root>/
├── src/
│   ├── main.py            # entry point, orchestration and stop handling
│   ├── data_acquisition.py# spawns capture / process / backup processes
│   ├── capture_data.py    # reads the NI DAQ
│   ├── process_data.py    # decimation, timestamping, batching
│   ├── data_handling.py   # SQLite writes and SQLite -> MongoDB backup
│   ├── setup_database.py  # schema creation, sensor list, Mongo client
│   ├── load_setup_data.py # SETUP.txt parser
│   ├── utils.py           # data export, PSD and SVD
│   ├── GUI.py             # acquisition control panel
│   └── GUI_check.py       # PSD / SVD viewer
├── control/
│   └── check_mongo_db.py  # duplicate / orphan check on MongoDB
├── doc/                   # user manual (DOCX and PDF)
├── SETUP.txt              # configuration
├── requirements.txt
├── test_smoke.py          # installation check
├── RUNGUI.bat / RUNMAIN.bat
└── README.md
```

---

## Key configuration parameters (`SETUP.txt`)

**Capture**
- `total_capture_time`: duration in seconds (`0` = continuous).
- `backup_time`: seconds between SQLite → MongoDB backups (`0` = no backup).
- `restart_time`: restart interval — `0`, `10s`, `1h`, `1d`, `1w`.
- `debug`: verbose console output.

**DAQ**
- `deviceName`: device name as shown in NI MAX.
- `original_rate`: raw sampling rate in Hz (2–24000).
- `buffer_size`: DAQ buffer in samples; the DAQ delivers data when it fills.
- `decimation_factor`: downsampling factor; effective rate is
  `original_rate / decimation_factor`.
- `daq_num_modules`, `daq_ch_per_module`: hardware layout.
- `unused_ch`: `nan`, or two-digit ids separated by commas (`21, 22`) where the
  first digit is the module and the second the channel.

**Sensors**
- `min_val`, `max_val`: expected signal range (m/s²).
- `sensitivity`: sensor sensitivity (V/g).

**Databases**
- `db_path`, `sqlite_name`: location and name of the SQLite buffer.
- `db_host`, `db_port`, `db_backup_name`: MongoDB connection and database.

---

## Notes

- If MongoDB is unreachable, backups are disabled automatically and data stays
  in SQLite — the acquisition does not stop.
- `last_seconds.json` and `psd_results.json` are regenerated on every check;
  they are working files, not results to keep.
- The full user manual, with step-by-step procedures and troubleshooting, is in
  [doc/](doc/) as `Manual_Usuario.docx` and `Manual_Usuario.pdf`.

---

## Authors

Developed by Emilio Daroch (University of Granada, 2024–2025) for the
**Hospital Real Seismic Monitoring System**, part of a cognitive SHM platform in
the BUILDCHAIN project.
