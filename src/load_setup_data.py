def load_config():
    config = {}
    with open('SETUP.txt', 'r') as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('#')
                key_value_part = parts[0].strip()
                key, value = key_value_part.split(': ')
                if key == 'debug':
                    config[key] = value.lower() == 'true'
                else:
                    config[key] = value

    # Combine sqlite_db_path and sqlite_name
    if 'db_path' in config and 'sqlite_name' in config:
        config['sqlite_db_path'] = f"{config['db_path']}{config['sqlite_name']}.db"

    # Convert numeric values to appropriate types
    numeric_keys = ["total_capture_time", "original_rate", "buffer_size", "decimation_factor", 
                    "min_val", "max_val", "sensitivity", "db_port", "backup_time"]
    for key in numeric_keys:
        if key in config:
            config[key] = float(config[key]) if key in ["min_val", "max_val", "sensitivity"] else int(config[key])

    # adjust restart_time if total_capture_time > 0
    if config.get("total_capture_time", 0) > 0:
        config["restart_time"] = "0s"  # Restart disabled

    return config

def parse_restart_time(restart_time_str):
    """
    Convierte la cadena de reinicio en segundos.
    Ejemplos:
    - "10s" -> 10 segundos
    - "1h"  -> 1 hora en segundos
    - "1d"  -> 1 día en segundos
    - "1w"  -> 1 semana en segundos
    """
    unit = restart_time_str[-1]
    time_value = float(restart_time_str[:-1])

    if unit == "s":
        return time_value  # En segundos
    elif unit == "h":
        return time_value * 3600  # Horas a segundos
    elif unit == "d":
        return time_value * 86400  # Días a segundos
    elif unit == "w":
        return time_value * 86400 * 7  # Semanas a segundos
    else:
        raise ValueError(f"Format not supported: {restart_time_str}")

if __name__ == "__main__":
    pass  # Este archivo no está destinado a ejecutarse directamente