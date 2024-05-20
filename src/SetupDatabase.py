import sqlite3
import sys

def setup_database(db_path, number_of_sensors):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Activar WAL
    cursor.execute("PRAGMA journal_mode=WAL;")

    # Verificar si las tablas ya existen y comparar el número de columnas con los sensores esperados
    cursor.execute("PRAGMA table_info(sensor_data);")
    sensor_columns = cursor.fetchall()
    cursor.execute("PRAGMA table_info(timestamps);")
    timestamp_columns = cursor.fetchall()

    if sensor_columns and len(sensor_columns) - 1 != number_of_sensors:  # Excluding timestamp_id
        print(f"La tabla actual tiene {len(sensor_columns) - 1} sensores, pero se esperan {number_of_sensors}.")
        response = input("¿Deseas borrar la base de datos existente y crear una nueva? (s/n): ")
        if response.lower() == 's':
            print("Escribe BORRAR para confirmar la eliminación de la base de datos.")
            double_check = input()
            if double_check == "BORRAR":
                cursor.execute("DROP TABLE IF EXISTS sensor_data;")
                cursor.execute("DROP TABLE IF EXISTS timestamps;")
                print("Las tablas han sido eliminadas.")
            else:
                print("Confirmación fallida. Abortando operación.")
                conn.close()
                sys.exit()
        else:
            print('''
              
            Operación cancelada.
            Modifica el archivo SETUP.txt y cambia el nombre 
            de la base de datos en db_file para crear una nueva
            y vuelve a ejecutar.      
        
          ''')
            conn.close()
            sys.exit()

    # Crear tabla para timestamps si no existe
    if not timestamp_columns:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timestamps (
                timestamp_id INTEGER PRIMARY KEY AUTOINCREMENT,
                time REAL UNIQUE
            );
        ''')

    # Crear tabla para datos de sensores si no existe o después de haber borrado la antigua
    if not sensor_columns:
        sensor_fields = ', '.join([f'sensor{i + 1} REAL' for i in range(number_of_sensors)])
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS sensor_data (
                data_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_id INTEGER,
                {sensor_fields},
                FOREIGN KEY(timestamp_id) REFERENCES timestamps(timestamp_id)
            );
        ''')

    # Crear índices para mejorar las consultas
    if not timestamp_columns:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_time ON timestamps(time);")
    if not sensor_columns:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp_id ON sensor_data(timestamp_id);")
    
    conn.commit()
    conn.close()
    print("Configuración de la base de datos completa.")
