import sqlite3
import sys

# def setup_database(db_path, number_of_sensors):
#     conn = sqlite3.connect(db_path)
#     cursor = conn.cursor()
    
#     # Activar WAL
#     cursor.execute("PRAGMA journal_mode=WAL;")

#     # Verificar si la tabla ya existe y comparar el número de columnas
#     # cursor.execute("PRAGMA table_info(acceleration_data);")
#     # columns = cursor.fetchall()
#     cursor.execute("SELECT COUNT(*) FROM sensors")
#     columns = cursor.fetchone()
    
#     # Si la tabla existe y el número de columnas es diferente al número de sensores esperado + 1 (incluyendo la columna de tiempo)
#     if columns and len(columns) != number_of_sensors + 1:
#         print(f"La tabla actual tiene {len(columns) - 1} sensores, pero se esperan {number_of_sensors}.")
#         response = input("¿Deseas borrar la base de datos existente y crear una nueva? (s/n): ")
        
#         if response.lower() == 's':
#             print("Escribe BORRAR para confirmar la eliminación de la base de datos.")
#             double_check = input()
#             if double_check == "BORRAR":
#                 cursor.execute("DROP TABLE IF EXISTS acceleration_data;")
#                 print("La tabla ha sido eliminada.")
#             else:
#                 print("Confirmación fallida. Abortando operación.")
#                 conn.close()
#                 sys.exit()
#         else:
#             print('''
              
#             Operación cancelada.
#             Modifica el archivo SETUP.txt y cambia el nombre 
#             de la base de datos en db_file para crear una nueva
#             y vuelve a ejecutar.      
        
#           ''')
#             conn.close()
#             sys.exit()

#     # Crear la tabla si no existe o después de haber borrado la antigua
#     sensor_columns = ', '.join([f'sensor{i + 1} REAL' for i in range(number_of_sensors)])
#     sql_query = f'''
#         CREATE TABLE IF NOT EXISTS acceleration_data (
#             time REAL,
#             {sensor_columns}
#         );
#     '''
#     cursor.execute(sql_query)
    
#     # Crear un índice en la columna 'time' para mejorar las consultas de búsqueda y ordenamiento
#     cursor.execute("CREATE INDEX IF NOT EXISTS idx_time ON acceleration_data(time);")
    
#     conn.commit()
#     conn.close()
#     print("Configuración de la base de datos completa.")


def get_sensor_numbers(config):
    """
    Function Duties:
        Get a list with the sensors identification
    Input:
        daq_num_modules: str containing the number of modules (0 not included)
        daq_ch_per_module: str containing the number of ch per module (0 not included)
        unused_ch: it can be:
            'nan': all channels are used
            'ij'; i: module id; j:channel id
            'ij, kl, mn...': same as before, but multiple elements
    Output:
        sensor_numbers: list
    """
    daq_num_modules = config['daq_num_modules']
    daq_ch_per_module = config['daq_ch_per_module']
    unused_ch = config['unused_ch']

    # Get preliminar list of sensor numbers
    sensor_numbers = list()
    daq_num_modules, daq_ch_per_module = int(daq_num_modules), int(daq_ch_per_module)
    for ai in [i for i in range(daq_ch_per_module)]:
        for mod in [j + 1 for j in range(daq_num_modules)]:
            sensor_numbers.append(10*mod+ai)

    # Readapt variable to see if there are unused channels
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

    return sensor_numbers


def isNaN(float_number):
    return float_number != float_number


def setup_database(db_path, sensor_numbers):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Activar WAL
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS timestamps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME NOT NULL
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
    
    # Insert sensor names into the sensors table if they don't already exist
    for sensor_number in sensor_numbers:
        cursor.execute('INSERT OR IGNORE INTO sensors (sensor_number) VALUES (?)', (sensor_number,))
    
    conn.commit()
    conn.close()
    print("Configuración de la base de datos completa.")