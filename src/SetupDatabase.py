import sqlite3
import sys

def setup_database(db_path, number_of_sensors):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Activar WAL
    cursor.execute("PRAGMA journal_mode=WAL;")

    # Verificar si la tabla ya existe y comparar el número de columnas
    cursor.execute("PRAGMA table_info(acceleration_data);")
    columns = cursor.fetchall()
    
    # Si la tabla existe y el número de columnas es diferente al número de sensores esperado + 1 (incluyendo la columna de tiempo)
    if columns and len(columns) != number_of_sensors + 1:
        print(f"La tabla actual tiene {len(columns) - 1} sensores, pero se esperan {number_of_sensors}.")
        response = input("¿Deseas borrar la base de datos existente y crear una nueva? (s/n): ")
        
        if response.lower() == 's':
            print("Escribe BORRAR para confirmar la eliminación de la base de datos.")
            double_check = input()
            if double_check == "BORRAR":
                cursor.execute("DROP TABLE IF EXISTS acceleration_data;")
                print("La tabla ha sido eliminada.")
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

    # Crear la tabla si no existe o después de haber borrado la antigua
    sensor_columns = ', '.join([f'sensor{i + 1} REAL' for i in range(number_of_sensors)])
    sql_query = f'''
        CREATE TABLE IF NOT EXISTS acceleration_data (
            time REAL,
            {sensor_columns}
        );
    '''
    cursor.execute(sql_query)
    
    # Crear un índice en la columna 'time' para mejorar las consultas de búsqueda y ordenamiento
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_time ON acceleration_data(time);")
    
    conn.commit()
    conn.close()
    print("Configuración de la base de datos completa.")

