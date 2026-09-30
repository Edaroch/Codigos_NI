"""Smoke test: run `python test_smoke.py` from the repository root.

Checks that every module under src/ imports, that SETUP.txt parses, and that the
SQLite schema can be created. Does not touch the DAQ or MongoDB.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import capture_data, data_acquisition, data_handling, process_data  # noqa: F401
from load_setup_data import load_config, parse_restart_time
from setup_database import (create_sqlite_path_if_not_exists, get_sensor_numbers,
                            setup_database)

config = load_config()
assert config["sqlite_db_path"].endswith(".db"), config["sqlite_db_path"]
assert isinstance(config["debug"], bool)
assert isinstance(config["original_rate"], int)

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
