from sqlite3 import connect
from os import makedirs, path
from pymongo import MongoClient, ASCENDING, errors
from colorama import Fore, Style

# Persistent MongoDB client
mongo_client = None

def create_sqlite_path_if_not_exists(sqlite_db_path):
    """
    Creates the SQLite folder and file if they do not exist.
    """
    directory = path.dirname(sqlite_db_path)

    # Create the directory if it does not exist
    if not path.exists(directory):
        makedirs(directory)
        print(f"Directory created: {directory}")

    # Create the SQLite database file if it does not exist
    if not path.exists(sqlite_db_path):
        open(sqlite_db_path, 'a').close()
        print(f"SQLite database created: {sqlite_db_path}")

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
    for mod in [j + 1 for j in range(daq_num_modules)]:
        for ai in [i for i in range(daq_ch_per_module)]:
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
    # print(sensor_numbers)
    # print(sensor_numbers_all)
    return sensor_numbers, sensor_numbers_all

def isNaN(float_number):
    """
    Checks whether a number is NaN.
    """
    return float_number != float_number

def setup_database(sqlite_db_path, config, sensor_numbers):
    """
    Sets up the SQLite and MongoDB databases.

    - SQLite is used as the buffer database.
    - MongoDB is set up for historical backups.

    Args:
        sqlite_db_path (str): Path to the SQLite database.
        config (dict): Configuration loaded from SETUP.txt.
        sensor_numbers (list): List of sensor numbers.
    """
    # SQLite configuration
    conn = connect(sqlite_db_path)
    cursor = conn.cursor()

    # Enable WAL
    cursor.execute("PRAGMA journal_mode=WAL;")

    # Create the SQLite tables
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

    # Insert the sensors into SQLite
    existing_sensors = set(row[0] for row in cursor.execute("SELECT sensor_number FROM sensors").fetchall())
    new_sensors = [sn for sn in sensor_numbers if sn not in existing_sensors]

    for sensor_number in new_sensors:
        cursor.execute('INSERT INTO sensors (sensor_number) VALUES (?)', (sensor_number,))
    conn.commit()
    conn.close()
    print("Database setup complete in SQLite.")


# MongoDB configuration
    mongo_client = None
    if config['backup_time'] == 0:
        if config["debug"]:
            print(Fore.RED + "Backup_time is 0, MongoDB database will not be configured" + Style.RESET_ALL)
        return
    try:
        # Inicializar cliente MongoDB
        mongo_client = MongoClient(config['db_host'], config['db_port'], serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')  # Validate the connection

        # Set up the raw database (historical storage)
        db_raw = mongo_client[config['db_backup_name']]
        sensors_collection_raw = db_raw['sensors']
        accelerations_collection_raw = db_raw['accelerations']

        # Create the MongoDB indexes
        accelerations_collection_raw.create_index([("timestamp", ASCENDING)])
        print("Timestamp indexes created in the raw database.")

        # Check which sensors already exist in MongoDB
        existing_sensors_raw = sensors_collection_raw.find({}, {"sensor_number": 1})
        existing_sensor_numbers_raw = {sensor["sensor_number"] for sensor in existing_sensors_raw}

        # Insert the sensors into MongoDB if they are missing
        new_sensors_raw = [sensor_number for sensor_number in sensor_numbers if sensor_number not in existing_sensor_numbers_raw]
        if new_sensors_raw:
            sensor_documents_raw = [{'sensor_number': sensor_number} for sensor_number in new_sensors_raw]
            sensors_collection_raw.insert_many(sensor_documents_raw)
            print(f"Added {len(new_sensors_raw)} new sensors to the raw database.")

        print("Raw database setup complete in MongoDB.")

    except errors.ServerSelectionTimeoutError as e:
        print(f"Error connecting to MongoDB: {e}")
        print(Fore.RED + "MongoDB is not available. Backups will be disabled. Backup time will be set to 0" + Style.RESET_ALL)
        config['backup_time'] = 0
    except Exception as e:
        print(f"Error configuring MongoDB: {e}")
        config['backup_time'] = 0
    finally:
        if mongo_client:
            mongo_client.close()

def initialize_mongodb_client(db_config):
    """
    Initializes the MongoDB client if not already initialized.
    Handles connection errors and returns None if MongoDB is unavailable.
    """
    global mongo_client
    if mongo_client is None:
        try:
            # Create the MongoDB client with a 5-second timeout
            mongo_client = MongoClient(db_config['db_host'], db_config['db_port'], serverSelectionTimeoutMS=5000)
            
            # Test the connection by pinging the server
            mongo_client.admin.command('ping')
        except errors.ServerSelectionTimeoutError:
            print("Error: Cannot connect to MongoDB. Backups will be disabled.")
            mongo_client = None  # Ensure the client remains None if connection fails
    return mongo_client

def close_mongodb_client():
    """Closes the MongoDB client if it is open."""
    global mongo_client
    if mongo_client is not None:
        mongo_client.close()
        mongo_client = None  # Reset it so the client can be initialized again later

if __name__ == "__main__":
    pass  # This file is not meant to be run directly
