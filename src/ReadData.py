import sqlite3
import datetime

def get_db_connection(db_path):
    """Conectar a la base de datos y devolver el cursor y la conexión."""
    conn = sqlite3.connect(db_path)
    return conn, conn.cursor()

def execute_query(cursor, query):
    """Ejecutar una consulta SQL y devolver los resultados."""
    cursor.execute(query)
    return cursor.fetchall()

def close_db_connection(conn):
    """Cerrar la conexión a la base de datos."""
    conn.close()

def get_formatted_time():
    """Obtener la hora y fecha actual en formato string."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def save_report_to_file(data, filename):
    """Guardar los datos en un archivo de texto."""
    with open(filename, 'w') as file:
        file.write(data)

# def calculate_frequency(records):
#     """Calcular la frecuencia de muestreo basada en dos registros temporales."""
#     if len(records) == 2:
#         time_difference = abs(records[0][0] - records[1][0])
#         if time_difference > 0:  # Evitar división por cero
#             return 1.0 / time_difference
#     return 0  # En caso de que no haya suficientes registros o no haya diferencia

def calculate_frequency(records):
    """Calcular la frecuencia de muestreo basada en dos registros temporales."""
    if len(records) == 2:
        time1 = datetime.datetime.fromtimestamp(records[0][0])
        time2 = datetime.datetime.fromtimestamp(records[1][0])
        
        time_difference = abs((time1 - time2).total_seconds())
        if time_difference > 0:  # Evitar división por cero
            return 1.0 / time_difference
    return 0  # En caso de que no haya suficientes registros o no haya diferencia

def main(db_path):
    
    conn, cursor = get_db_connection(db_path)

    # Consultas SQL
    # queries = {
    #     'last_n_records': 'SELECT * FROM accelerations ORDER BY time DESC LIMIT 3',
    #     'total_records': 'SELECT COUNT(*) FROM accelerations',
    #     'sample_seconds': 'SELECT MAX(time) - MIN(time) FROM accelerations',
    #     'last_2_records': 'SELECT time FROM accelerations ORDER BY time DESC LIMIT 2'
    # }

    queries = {
        'last_n_records': '''
            SELECT a.*
            FROM accelerations a
            JOIN timestamps t ON a.timestamp_id = t.id
            ORDER BY t.timestamp DESC
            LIMIT 3
        ''',
        'total_records': 'SELECT COUNT(*) FROM accelerations',
        'sample_seconds': '''
            SELECT (julianday(MAX(t.timestamp)) - julianday(MIN(t.timestamp))) * 86400.0 AS sample_seconds
            FROM accelerations a
            JOIN timestamps t ON a.timestamp_id = t.id
        ''',
        'last_2_records': '''
            SELECT t.timestamp
            FROM accelerations a
            JOIN timestamps t ON a.timestamp_id = t.id
            ORDER BY t.timestamp DESC
            LIMIT 2
        '''
    }

    # Ejecución de consultas
    last_n_records = execute_query(cursor, queries['last_n_records'])
    total_records = execute_query(cursor, queries['total_records'])[0][0]
    sample_seconds = execute_query(cursor, queries['sample_seconds'])[0][0]
    last_2_records = execute_query(cursor, queries['last_2_records'])

    # Calcular frecuencia
    frequency_hz = calculate_frequency(last_2_records)

    # Preparación de datos para el archivo
    report = []
    report.append("Últimos 3 registros ordenados por timestamp:\n")
    report.extend([str(record) + '\n' for record in last_n_records])
    report.append(f"Total de registros en la base de datos: {total_records}\n")
    report.append(f"Cantidad de segundos de muestra: {sample_seconds}\n")
    report.append(f"Frecuencia de muestreo real: {frequency_hz:.2f} Hz\n")

    close_db_connection(conn)

    # Guardar en archivo
    filename = f'reporte_{get_formatted_time()}.txt'
    save_report_to_file(''.join(report), filename)
    print(f"Reporte guardado en: {filename}")

# db_path = r"C:/xampp/htdocs/APIRest/sqldb/aceleraciones.db"

if __name__ == "__main__":
    main()