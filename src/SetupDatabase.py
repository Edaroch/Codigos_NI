from sqlite3 import connect  # Solo se importa la función connect de sqlite3
from os import makedirs, path  # Solo se importan makedirs y path
from pymongo import MongoClient, ASCENDING, errors  # Importar MongoClient y ASCENDING de pymongo
from colorama import Fore, Style

def create_sqlite_path_if_not_exists(sqlite_db_path):
    """
    Crea la carpeta y archivo SQLite si no existen.
    """
    directory = path.dirname(sqlite_db_path)

    # Crear el directorio si no existe
    if not path.exists(directory):
        makedirs(directory)
        print(f"Directorio creado: {directory}")

    # Crear el archivo de base de datos SQLite si no existe
    if not path.exists(sqlite_db_path):
        open(sqlite_db_path, 'a').close()
        print(f"Base de datos SQLite creada: {sqlite_db_path}")


def get_sensor_numbers(config):
    """
    Function Duties:
        Get a list with the sensors identification.
    Input:
        daq_num_modules: str containing the number of modules (0 not included).
        daq_ch_per_module: str containing the number of ch per module (0 not included).
        unused_ch: it can be:
            'nan': all channels are used
            'ij'; i: module id; j:channel id.
            'ij, kl, mn...': same as before, but multiple elements.
    Output:
        sensor_numbers: list with sensor numbers.
        sensor_numbers_all: list with all sensor numbers (all channels that will be
            recorded by the DAQ, although some of them should be discarded).
    """
    daq_num_modules = config['daq_num_modules']
    daq_ch_per_module = config['daq_ch_per_module']
    unused_ch = config['unused_ch']

    # Get preliminar list of sensor numbers
    sensor_numbers = list()
    daq_num_modules, daq_ch_per_module = int(daq_num_modules), int(daq_ch_per_module)
    for ai in [i for i in range(daq_ch_per_module)]:
        for mod in [j + 1 for j in range(daq_num_modules)]:
            sensor_numbers.append(10 * mod + ai)
    sensor_numbers_all = [i for i in sensor_numbers]

    # Handle unused channels
    exist_unused_ch = True
    if ',' in unused_ch:
        unused_ch = unused_ch.split(',')
        unused_ch = [int(i) for i in unused_ch]
    else:
        unused_ch = float(unused_ch)
        if isNaN(unused_ch):
            exist_unused_ch = False
        else:
            unused_ch = int(unused_ch)
        unused_ch = [unused_ch]

    # Remove unused channels
    if exist_unused_ch:
        for i in unused_ch:
            sensor_numbers.remove(i)

    return sensor_numbers, sensor_numbers_all


def isNaN(float_number):
    """
    Verifica si un número es NaN.
    """
    return float_number != float_number


def setup_database(sqlite_db_path, config, sensor_numbers):
    """
    Configura la base de datos SQLite y MongoDB.

    - SQLite se utiliza como base de datos buffer.
    - MongoDB se configura para respaldos históricos.

    Parámetros:
        sqlite_db_path (str): Ruta a la base de datos SQLite.
        config (dict): Configuración cargada desde SETUP.txt.
        sensor_numbers (list): Lista de números de sensores.
    """
    # Configuración de SQLite
    conn = connect(sqlite_db_path)
    cursor = conn.cursor()

    # Activar WAL
    cursor.execute("PRAGMA journal_mode=WAL;")

    # Crear tablas en SQLite
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS timestamps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL NOT NULL
    );
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sensors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sensor_number INTEGER UNIQUE
    );
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS accelerations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp_id INTEGER NOT NULL,
        sensor_id INTEGER NOT NULL,
        acceleration_value REAL NOT NULL,
        FOREIGN KEY (timestamp_id) REFERENCES timestamps(id),
        FOREIGN KEY (sensor_id) REFERENCES sensors(id)
    );
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON timestamps(timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sensor_number ON sensors(sensor_number);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp_id ON accelerations(timestamp_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sensor_id ON accelerations(sensor_id);")

    conn.commit()

    # Insertar sensores en SQLite
    existing_sensors = set(row[0] for row in cursor.execute("SELECT sensor_number FROM sensors").fetchall())
    new_sensors = [sn for sn in sensor_numbers if sn not in existing_sensors]

    for sensor_number in new_sensors:
        cursor.execute('INSERT INTO sensors (sensor_number) VALUES (?)', (sensor_number,))
    conn.commit()
    conn.close()
    print("Configuración de la base de datos SQLite completa.")


# Configuración de MongoDB
    mongo_client = None
    if config['backup_time'] == 0:
        if config["debug"]:
            print(Fore.RED + "Backup_time es 0, no se configura base de datos en MongoDB" + Style.RESET_ALL)
        return
    try:
        # Inicializar cliente MongoDB
        mongo_client = MongoClient(config['db_host'], config['db_port'], serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')  # Validar conexión

        # Configurar la base de datos raw (almacenamiento histórico)
        db_raw = mongo_client[config['db_backup_name']]
        sensors_collection_raw = db_raw['sensors']
        accelerations_collection_raw = db_raw['accelerations']

        # Crear índices en MongoDB
        accelerations_collection_raw.create_index([("timestamp", ASCENDING)])
        print("Índices de timestamp creados en la base de datos raw.")

        # Verificar sensores existentes en MongoDB
        existing_sensors_raw = sensors_collection_raw.find({}, {"sensor_number": 1})
        existing_sensor_numbers_raw = {sensor["sensor_number"] for sensor in existing_sensors_raw}

        # Insertar sensores en MongoDB si no existen
        new_sensors_raw = [sensor_number for sensor_number in sensor_numbers if sensor_number not in existing_sensor_numbers_raw]
        if new_sensors_raw:
            sensor_documents_raw = [{'sensor_number': sensor_number} for sensor_number in new_sensors_raw]
            sensors_collection_raw.insert_many(sensor_documents_raw)
            print(f"Se han añadido {len(new_sensors_raw)} sensores nuevos en la base de datos raw.")

        print("Configuración de la base de datos raw completa en MongoDB.")

    except errors.ServerSelectionTimeoutError as e:
        print(f"Error al conectar con MongoDB: {e}")
        print(Fore.RED + "MongoDB no está disponible. Se desactivarán los respaldos. Tiempo de respaldo se modificará a 0"+ Style.RESET_ALL)
        config['backup_time'] = 0
    except Exception as e:
        print(f"Error al configurar MongoDB: {e}")
        config['backup_time'] = 0
    finally:
        if mongo_client:
            mongo_client.close()


if __name__ == "__main__":
    pass  # Este archivo no está destinado a ejecutarse directamente
