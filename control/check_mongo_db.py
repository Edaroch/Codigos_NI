from pymongo import MongoClient
'''

Just to check if raw data in MongoDB is duplicated or orphaned.

'''    
# Configuración de la conexión a MongoDB
DB_HOST = "localhost"
DB_PORT = 27017
RAW_DB_NAME = "acquisition_db_raw"  # Nombre de la base de datos MongoDB
RAW_COLLECTION_NAME = "accelerations"  # Colección donde están los datos

def check_mongo_data():
    try:
        # Conexión al cliente de MongoDB
        client = MongoClient(DB_HOST, DB_PORT)
        db = client[RAW_DB_NAME]
        collection = db[RAW_COLLECTION_NAME]

        print("Conexión a la base de datos establecida.")

        # Verificar timestamps duplicados
        duplicate_timestamps = collection.aggregate([
            {
                "$group": {
                    "_id": "$timestamp",
                    "count": {"$sum": 1},
                    "documents": {"$push": "$$ROOT"}
                }
            },
            {
                "$match": {
                    "count": {"$gt": 1}
                }
            }
        ])

        duplicates = list(duplicate_timestamps)
        if duplicates:
            print(f"Se encontraron {len(duplicates)} timestamps duplicados:")
            for dup in duplicates[:10]:
                print(f"\n- Timestamp: {dup['_id']} | Repeticiones: {dup['count']}")
                for doc in dup["documents"]:
                    print(f"  - ID: {doc['_id']}")
                    for sensor_data in doc["sensor_data"]:
                        print(f"    Sensor ID: {sensor_data['sensor_id']} | Aceleración: {sensor_data['acceleration']}")
        else:
            print("No se encontraron timestamps duplicados.")

        # Verificar aceleraciones huérfanas (sin datos de sensor)
        orphaned_accelerations = collection.find({
            "$or": [
                {"sensor_data": {"$exists": False}},
                {"sensor_data": {"$size": 0}}
            ]
        })

        orphaned_list = list(orphaned_accelerations)
        if orphaned_list:
            print(f"\nSe encontraron {len(orphaned_list)} registros de aceleraciones huérfanos.")
            for orphan in orphaned_list[:10]:  # Mostrar los primeros 10 registros huérfanos
                print(f"  - ID: {orphan['_id']} | Timestamp: {orphan.get('timestamp', 'N/A')}")
        else:
            print("\nNo se encontraron registros de aceleraciones huérfanos.")

    except Exception as e:
        print(f"Error al verificar los datos en MongoDB: {e}")

    finally:
        client.close()
        print("Conexión a la base de datos cerrada.")

if __name__ == "__main__":
    check_mongo_data()
