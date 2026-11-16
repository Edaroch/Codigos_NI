"""End-to-end test: run `python test_acquisition.py [seconds]` from the repository root.

Runs the real acquisition (src/main.py) for a few seconds, checks what reached SQLite,
then runs the analysis chain and drives both GUIs, saving every figure.

DAQ source:
- If the NI-DAQmx driver lists a device named like `device_name` in SETUP.txt, that device
  is used. To test without hardware, create it in NI MAX: Devices and Interfaces >
  Create New > Simulated NI-DAQmx Chassis > cDAQ-9185 (named as device_name), then add
  one NI 9230 per module in slots 1..daq_num_modules.
- Otherwise the DAQ is emulated: channel i is a 2+i Hz sine plus noise, delivered in real time.

Everything runs in a temporary folder with its own SETUP.txt (no MongoDB, no restart),
so the repository and its database are not touched.
"""
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time

import numpy as np
import nidaqmx
from nidaqmx.system import System

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

from load_setup_data import NI9230_RATES, load_config  # noqa: E402


class EmulatedTask:
    """Stands in for nidaqmx.Task when no NI-DAQmx device is available."""

    def __init__(self):
        self.channels, self.read_samples = [], 0
        self.ai_channels = self.timing = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def add_ai_accel_chan(self, name, **kwargs):
        self.channels.append(name)

    def cfg_samp_clk_timing(self, rate, **kwargs):
        self.samp_clk_rate, self.start = rate, time.time()

    def read(self, number_of_samples_per_channel):
        n = number_of_samples_per_channel
        # Block until the samples would exist, like the real DAQ
        time.sleep(max(0.0, self.start + (self.read_samples + n) / self.samp_clk_rate - time.time()))
        t = (self.read_samples + np.arange(n)) / self.samp_clk_rate
        self.read_samples += n
        noise = np.random.default_rng().standard_normal((len(self.channels), n))
        return [0.002 * np.sin(2 * np.pi * (2 + i) * t) + 1e-4 * noise[i] for i in range(len(self.channels))]


def ni_devices():
    try:
        return [device.name for device in System.local().devices]
    except Exception:  # NI-DAQmx driver not installed
        return []


# Decided at import time so the spawned capture process makes the same choice
DEVICE = load_config(os.path.join(ROOT, "SETUP.txt"))["device_name"]
EMULATED = DEVICE not in ni_devices()
if EMULATED:
    nidaqmx.Task = EmulatedTask


def pump(root, seconds=0.5):
    """Lets Tk run its pending callbacks (after(), redraws) for a while."""
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def widget_texts(widget):
    texts = set()
    for child in widget.winfo_children():
        try:
            texts.add(child.cget("text"))
        except Exception:
            pass
        texts |= widget_texts(child)
    return texts


def run_acquisition(tmp, seconds):
    overrides = {"db_path": tmp + os.sep, "backup_time": "0", "restart_time": "1h",
                 "total_capture_time": "0", "debug": "false"}
    with open(os.path.join(ROOT, "SETUP.txt")) as f:
        lines = [f"{line.split(':')[0]}: {overrides[line.split(':')[0]]}"
                 if line.split(':')[0] in overrides else line.rstrip("\n") for line in f]
    with open("SETUP.txt", "w") as f:
        f.write("\n".join(lines) + "\n")

    import main as acquisition  # src/main.py
    stopper = threading.Timer(seconds, lambda: open("STOP.txt", "w").write("stop"))  # the GUI's stop path
    stopper.start()
    acquisition.main()
    stop_time = time.time()

    config = load_config()
    rate = config["frequency_rate"] / config["decimation_factor"]
    from setup_database import get_sensor_numbers
    n_sensors = len(get_sensor_numbers(config)[0])
    with sqlite3.connect(config["sqlite_db_path"]) as conn:
        ts = np.array([r[0] for r in conn.execute("SELECT timestamp FROM timestamps ORDER BY timestamp")])
        stored = conn.execute("SELECT COUNT(DISTINCT sensor_id), COUNT(*) FROM accelerations").fetchone()
    print(f"SQLite: {len(ts)} timestamps x {stored[0]} sensors = {stored[1]} values "
          f"({len(ts) / rate:.1f} s at {rate:g} Hz), last sample {stop_time - ts[-1]:.2f} s before the stop")
    assert stored[0] == n_sensors and stored[1] == len(ts) * n_sensors, stored
    assert len(ts) / rate >= seconds / 2, "less data than expected in SQLite"  # process start-up eats a few s
    assert np.allclose(np.diff(ts), 1 / rate, atol=1e-6), "timestamps are not evenly spaced at the stored rate"
    return config


def run_analysis():
    from utils import get_PSD_SVD_from_file, get_last_seconds_from_sqlite
    assert get_last_seconds_from_sqlite(seconds=30), "no records exported from SQLite"
    get_PSD_SVD_from_file()
    with open("psd_results.json") as f:
        results = json.load(f)
    freqs = np.array(results["frequencies"])
    peaks = [freqs[np.argmax(values)] for values in results["psd"].values()]
    print("PSD peaks (Hz):", [round(p, 2) for p in peaks])
    if EMULATED:  # channel i carries a 2+i Hz sine
        assert all(abs(p - (2 + i)) < 0.5 for i, p in enumerate(peaks)), peaks
    assert len(results["singular_values"]) == len(results["psd"])


def run_analysis_gui(tmp):
    import tkinter as tk
    import GUI_analysis
    from utils import save_figure

    saved = []
    GUI_analysis.save_figure = lambda fig, name: saved.append(  # skip the file dialog
        save_figure(fig, name, os.path.join(tmp, f"{name}.png")))

    root = tk.Tk()
    root.withdraw()
    app = GUI_analysis.AnalysisGUI(root)
    assert root.title() == "Analysis GUI"
    assert "Save figure" in widget_texts(root)

    app.check_data()  # "Plot Once"
    pump(root)
    assert app.active_view == "overlay" and app.ax.lines, "PSD Overlay not drawn"
    app.save_current_figure()

    app.plot_psd_mosaic()
    pump(root)
    assert app.active_view == "mosaic" and app.mosaic_ready, "PSD Mosaic not drawn"
    app.save_current_figure()

    for log in (False, True):
        app.log_scale_var.set(log)
        app.plot_singular_values()
        pump(root)
        assert app.active_view == "svd" and app.ax.get_ylabel() == "Singular Value [(m/s²)²/Hz]", app.ax.get_ylabel()
    app.save_current_figure()
    save_figure(app.fig, "svd", os.path.join(tmp, "svd.pdf"))

    app.on_closing()
    names = [os.path.basename(p) for p in saved]
    assert names == ["psd_overlay.png", "psd_mosaic.png", "svd.png"], names
    assert all(os.path.getsize(p) > 10_000 for p in saved + [os.path.join(tmp, "svd.pdf")])


def run_main_gui(tmp):
    import tkinter as tk
    from tkinter import ttk
    import warnings
    import GUI
    from utils import save_figure

    # Start from an old-style SETUP.txt to check that it loads and is migrated on save
    with open("SETUP.txt") as f:
        text = f.read()
    with open("SETUP.txt", "w") as f:
        f.write(text.replace("device_name:", "deviceName:").replace("frequency_rate:", "original_rate:")
                .replace("buffer_time: 1 ", "buffer_size: 1600 "))

    saved = []
    GUI.save_figure = lambda fig, name: saved.append(  # skip the file dialog
        save_figure(fig, name, os.path.join(tmp, f"{name}.png")))
    root = tk.Tk()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app = GUI.AcquisitionGUI(root)
    assert sum(w.category is FutureWarning for w in caught) == 3, [str(w.message) for w in caught]

    entries = app.entries
    assert {"original_rate", "buffer_size", "deviceName"}.isdisjoint(entries)
    assert isinstance(entries["frequency_rate"], ttk.Combobox)
    assert list(entries["frequency_rate"]["values"]) == [GUI.format_rate(r) for r in NI9230_RATES]
    assert entries["frequency_rate"].get() == "1600" and entries["buffer_time"].get() == "1.0"
    assert isinstance(entries["debug"], ttk.Combobox) and list(entries["debug"]["values"]) == ["True", "False"]
    assert app.output_rate_label.cget("text") == "Stored rate: 200 Hz"
    assert {"Spectral Analysis", "Save figure"} <= widget_texts(root)

    app.update_plot()
    pump(root)
    app.save_plot()
    assert os.path.getsize(saved[0]) > 10_000

    app.update_config()  # "Save Changes"
    root.destroy()
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # no deprecated key may remain
        config = load_config()
    with open("SETUP.txt") as f:
        text = f.read()
    assert "device_name: cDAQ1 #" in text and "frequency_rate: 1600 #" in text and "buffer_time: 1.0 #" in text
    assert config["buffer_size"] == 1600 and config["debug"] is False


if __name__ == "__main__":
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 15
    print(f"DAQ: {'emulated (no NI-DAQmx device ' + DEVICE + ')' if EMULATED else 'NI-DAQmx device ' + DEVICE}")
    with tempfile.TemporaryDirectory(prefix="shmdaq_test_", ignore_cleanup_errors=True) as tmp:
        os.chdir(tmp)
        run_acquisition(tmp, seconds)
        run_analysis()
        run_analysis_gui(tmp)
        run_main_gui(tmp)
        os.chdir(ROOT)
    print("OK: acquisition, SQLite storage, analysis and both GUIs passed")
