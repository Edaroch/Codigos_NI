import time
from datetime import datetime
import sqlite3
import os
from threading import Thread, Event

def generate_backup_filename(data_path):
    if not os.path.exists(data_path):
        os.makedirs(data_path)
    return f"{data_path}/{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"

def get_sampling_frequency(cursor):
    # Asegúrate de seleccionar solo la columna necesaria
    cursor.execute("SELECT time FROM acceleration_data ORDER BY time DESC LIMIT 2")
    times = cursor.fetchall()
    if len(times) == 2:
        time_diff = times[0][0] - times[1][0]
        if time_diff > 0:
            frequency = 1 / time_diff
            return frequency
    return 0  # In case there are not enough records or no time difference

def backup_last_generated_data(stop_event, db_path, data_path, cada, cuanto):
    cada *= 60  # Convert minutes to seconds for scheduling
    cuanto *= 60  # Convert minutes to seconds for the amount of data to backup
    time.sleep(5)
    while not stop_event.is_set():
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:  # Utilizar with para manejo automático de recursos
            conn.execute("PRAGMA journal_mode=WAL;")  # Activar WAL
            cursor = conn.cursor()

            frequency = get_sampling_frequency(cursor)
            if frequency > 0:
                num_records = int(frequency * cuanto)
                # Especificar columnas en la consulta para mejorar la eficiencia
                query = "SELECT time, sensor1, sensor2, sensor3 FROM acceleration_data ORDER BY time DESC LIMIT ?"
                cursor.execute(query, (num_records,))
                data_to_backup = cursor.fetchall()

                if data_to_backup:
                    filename = generate_backup_filename(data_path)
                    with open(filename, 'w') as f:
                        for record in data_to_backup:
                            f.write(f"{record}\n")
                    print(f"Respaldo creado: {filename}")
                else:
                    print("No hay datos para respaldar.")
        # Check the stop event periodically during the sleep period
        if stop_event.wait(cada):  # Wait returns True if the event is set, which breaks the loop
            break

def main(cada, cuanto, db_path, data_path):
    stop_event = Event()
    
    backup_thread = Thread(target=backup_last_generated_data, args=(stop_event, db_path, data_path, cada, cuanto))
    backup_thread.start()
    try:
        input('''
              
            ---------INICIANDO PROCESO DE RESPALDO----------
        
          ''')

    finally:
        print("Cerrando proceso de respaldo en txt.")
        stop_event.set()
        backup_thread.join()
        print("Proceso de respaldo terminado. Presiona ENTER nuevamente para terminar captura de datos")

if __name__ == "__main__":
    main()

    # cada = 300  # Every 300 minutes (5 hours)
    # cuanto = 30  # Last 30 minutes of data
    # db_path = r'C:/xampp/htdocs/APIRest/sqldb/aceleraciones.db'
    # data_path = r'C:/xampp/htdocs/APIRest/data'
    # main(cada, cuanto, db_path, data_path)
