"""Smoke test: run `python test_smoke.py` from the repository root.

Checks that every module under src/ imports, that SETUP.txt parses (including the
deprecated keys of older files), and that the SQLite schema can be created.
Does not touch the DAQ or MongoDB.
"""
import os
import sys
import tempfile
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import capture_data, data_acquisition, data_handling, process_data  # noqa: F401
from load_setup_data import NI9230_RATES, load_config, parse_restart_time
from setup_database import (create_sqlite_path_if_not_exists, get_sensor_numbers,
                            setup_database)

# NI-9230 datasheet, Table 1: 45 data rates from 12.8 kS/s down to 0.98 kS/s
assert len(NI9230_RATES) == 45 and NI9230_RATES[0] == 12800 and round(NI9230_RATES[-1], 2) == 984.62
assert 1600 in NI9230_RATES

config = load_config()
assert config["sqlite_db_path"].endswith(".db"), config["sqlite_db_path"]
assert isinstance(config["debug"], bool)
assert config["frequency_rate"] in NI9230_RATES
assert config["buffer_size"] == round(config["buffer_time"] * config["frequency_rate"])
assert "device_name" in config


def parse(text):
    """Loads a SETUP.txt variant written to a temporary file."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(text)
    try:
        return load_config(f.name)
    finally:
        os.remove(f.name)


base = "debug: false\nfrequency_rate: 8533.33\nbuffer_time: 0.5\ndb_path: x\\\nsqlite_name: y\n"

# Rates are matched to the exact NI-9230 value, so 8533.33 means 13.1072 MHz / 1536
assert parse(base)["frequency_rate"] == 13.1072e6 / 1536
assert parse(base)["buffer_size"] == 4267

# An older SETUP.txt still loads, with a FutureWarning per renamed key
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    legacy = parse("deviceName: cDAQ1\noriginal_rate: 1600\nbuffer_size: 3200\ndebug: true\n")
assert len(caught) == 3 and all(w.category is FutureWarning for w in caught)
assert legacy["device_name"] == "cDAQ1" and legacy["frequency_rate"] == 1600
assert legacy["buffer_time"] == 2 and legacy["buffer_size"] == 3200

# Invalid values are rejected with a clear message
for bad in (base.replace("debug: false", "debug: yes"), base.replace("8533.33", "1000")):
    try:
        parse(bad)
    except ValueError as e:
        print(f"  rejected as expected: {e}")
    else:
        raise AssertionError(f"accepted an invalid SETUP.txt:\n{bad}")

assert parse_restart_time("10s") == 10
assert parse_restart_time("6h") == 21600
assert parse_restart_time("1d") == 86400
assert parse_restart_time("1w") == 604800

sensors, sensors_all = get_sensor_numbers(config)
expected = int(config["daq_num_modules"]) * int(config["daq_ch_per_module"])
assert len(sensors_all) == expected, (sensors_all, expected)
assert set(sensors) <= set(sensors_all)

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    db = os.path.join(tmp, "sub", "accelerations.db")
    create_sqlite_path_if_not_exists(db)
    config = dict(config, backup_time=0)  # skip the MongoDB half
    setup_database(db, config, sensors)

    from sqlite3 import connect
    conn = connect(db)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"timestamps", "sensors", "accelerations"} <= tables, tables
        stored = [r[0] for r in conn.execute("SELECT sensor_number FROM sensors")]
        assert stored == sensors, (stored, sensors)
    finally:
        conn.close()

print("OK: smoke test passed")
