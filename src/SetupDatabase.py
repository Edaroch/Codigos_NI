from pymongo import MongoClient, ASCENDING

def get_sensor_numbers(config):
    """
    Función para obtener los números de sensores.
    """
    daq_num_modules = config['daq_num_modules']
    daq_ch_per_module = config['daq_ch_per_module']
    unused_ch = config['unused_ch']

    sensor_numbers = []
    daq_num_modules, daq_ch_per_module = int(daq_num_modules), int(daq_ch_per_module)
    for ai in range(daq_ch_per_module):
        for mod in range(1, daq_num_modules + 1):
            sensor_numbers.append(10 * mod + ai)
    
    sensor_numbers_all = sensor_numbers.copy()

    # Manejar canales no usados
    if isinstance(unused_ch, list):
        sensor_numbers = [i for i in sensor_numbers if i not in unused_ch]
    elif isinstance(unused_ch, int):
        sensor_numbers = [i for i in sensor_numbers if i != unused_ch]

    return sensor_numbers, sensor_numbers_all


def setup_database(config, sensor_numbers):
    """
    Función para configurar la base de datos en MongoDB.
    Crea colecciones para timestamps, sensores y aceleraciones, si no existen,
    tanto en la base de datos buffer (temporal) como en la base de datos raw (almacenamiento histórico).
    """
    try:
        # Conectar a MongoDB
        client = MongoClient(config['db_host'], config['db_port'])

        # Configurar la base de datos buffer (en tiempo real)
        db_buffer = client[config['db_name']]
        sensors_collection_buffer = db_buffer['sensors']
        accelerations_collection_buffer = db_buffer['accelerations']

        # Configurar la base de datos raw (almacenamiento histórico)
        db_raw = client[config['db_backup_name']]
        sensors_collection_raw = db_raw['sensors']
        accelerations_collection_raw = db_raw['accelerations']

        # Crear índices en el campo timestamp
        accelerations_collection_buffer.create_index([("timestamp", ASCENDING)])
        accelerations_collection_raw.create_index([("timestamp", ASCENDING)])
        print("Índices de timestamp creados en las bases de datos buffer y raw.")

        # Verificar si los sensores ya existen en la base de datos buffer
        existing_sensors_buffer = sensors_collection_buffer.find({}, {"sensor_number": 1})
        existing_sensor_numbers_buffer = {sensor["sensor_number"] for sensor in existing_sensors_buffer}

        # Filtrar sensores que no existan en la base de datos buffer
        new_sensors_buffer = [sensor_number for sensor_number in sensor_numbers if sensor_number not in existing_sensor_numbers_buffer]

        if new_sensors_buffer:
            # Insertar solo los sensores que no estén en la base de datos buffer
            sensor_documents_buffer = [{'sensor_number': sensor_number} for sensor_number in new_sensors_buffer]
            sensors_collection_buffer.insert_many(sensor_documents_buffer)
            print(f"Se han añadido {len(new_sensors_buffer)} sensores nuevos en la base de datos buffer.")

        print("Configuración de la base de datos buffer completa en MongoDB.")

        # Verificar si los sensores ya existen en la base de datos raw
        existing_sensors_raw = sensors_collection_raw.find({}, {"sensor_number": 1})
        existing_sensor_numbers_raw = {sensor["sensor_number"] for sensor in existing_sensors_raw}

        # Filtrar sensores que no existan en la base de datos raw
        new_sensors_raw = [sensor_number for sensor_number in sensor_numbers if sensor_number not in existing_sensor_numbers_raw]

        if new_sensors_raw:
            # Insertar solo los sensores que no estén en la base de datos raw
            sensor_documents_raw = [{'sensor_number': sensor_number} for sensor_number in new_sensors_raw]
            sensors_collection_raw.insert_many(sensor_documents_raw)
            print(f"Se han añadido {len(new_sensors_raw)} sensores nuevos en la base de datos raw.")

        print("Configuración de la base de datos raw completa en MongoDB.")

    except Exception as e:
        print(f"Error al configurar la base de datos en MongoDB: {e}")
    
    finally:
        # Cerrar la conexión a MongoClient para liberar recursos
        client.close()
        
if __name__ == "__main__":
    pass  # Este archivo no está destinado a ejecutarse directamente