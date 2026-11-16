from warnings import warn

# Data rates of the NI-9230 with its internal master timebase (datasheet 374829A-02):
# fs = fM / (2*m*n), fM = 13.1072 MHz, m = 64 (n = 9..25), 128 (n = 5..25), 256 (n = 2..26).
# 45 rates from 12800 Hz down to 984.62 Hz. Single source for the parser and the GUI.
NI9230_RATES = sorted({13.1072e6 / (2 * m * n)
                       for m, n_min, n_max in ((64, 9, 25), (128, 5, 25), (256, 2, 26))
                       for n in range(n_min, n_max + 1)}, reverse=True)

# Keys renamed in SETUP.txt. The old names are still read, with a warning.
LEGACY_KEYS = {"deviceName": "device_name",
               "original_rate": "frequency_rate",
               "buffer_size": "buffer_time"}  # samples -> seconds, converted below


def load_config(path='SETUP.txt'):
    config = {}
    with open(path, 'r') as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('#')
                key_value_part = parts[0].strip()
                key, value = key_value_part.split(': ')
                if key in LEGACY_KEYS:
                    warn(f"SETUP.txt: '{key}' is deprecated, use '{LEGACY_KEYS[key]}' instead.",
                         FutureWarning, stacklevel=2)
                    if key != "buffer_size":  # buffer_size needs a unit conversion, done below
                        key = LEGACY_KEYS[key]
                if key == 'debug':
                    if value.lower() not in ('true', 'false'):
                        raise ValueError(f"SETUP.txt: debug must be true or false, not '{value}'.")
                    config[key] = value.lower() == 'true'
                else:
                    config[key] = value

    # Combine sqlite_db_path and sqlite_name
    if 'db_path' in config and 'sqlite_name' in config:
        config['sqlite_db_path'] = f"{config['db_path']}{config['sqlite_name']}.db"

    # Convert numeric values to appropriate types
    float_keys = ["min_val", "max_val", "sensitivity", "buffer_time"]
    numeric_keys = ["total_capture_time", "decimation_factor", "db_port", "backup_time"] + float_keys
    for key in numeric_keys:
        if key in config:
            config[key] = float(config[key]) if key in float_keys else int(config[key])

    # The DAQ sampling rate must be one the NI-9230 supports, or DAQmx would silently change it
    rate = float(config["frequency_rate"])
    matches = [r for r in NI9230_RATES if abs(r - rate) < 0.01]
    if not matches:
        nearest = min(NI9230_RATES, key=lambda r: abs(r - rate))
        raise ValueError(f"SETUP.txt: frequency_rate {rate:g} Hz is not an NI-9230 data rate "
                         f"(nearest: {nearest:.2f} Hz). Pick one from the GUI drop-down list.")
    config["frequency_rate"] = matches[0]

    # Samples per DAQ read. Old SETUP.txt files give buffer_size (samples) instead of buffer_time
    if "buffer_time" not in config:
        config["buffer_time"] = int(config["buffer_size"]) / config["frequency_rate"]
    config["buffer_size"] = max(1, round(config["buffer_time"] * config["frequency_rate"]))

    # adjust restart_time if total_capture_time > 0
    if config.get("total_capture_time", 0) > 0:
        config["restart_time"] = "0s"  # Restart disabled

    return config

def parse_restart_time(restart_time_str):
    """
    Converts the restart string into seconds.
    Examples:
    - "10s" -> 10 seconds
    - "1h"  -> one hour, in seconds
    - "1d"  -> one day, in seconds
    - "1w"  -> one week, in seconds
    """
    unit = restart_time_str[-1]
    time_value = float(restart_time_str[:-1])

    if unit == "s":
        return time_value  # Already in seconds
    elif unit == "h":
        return time_value * 3600  # Hours to seconds
    elif unit == "d":
        return time_value * 86400  # Days to seconds
    elif unit == "w":
        return time_value * 86400 * 7  # Weeks to seconds
    else:
        raise ValueError(f"Format not supported: {restart_time_str}")

if __name__ == "__main__":
    pass  # This file is not meant to be run directly
