""" 
Codigo para obtener los ultimos minutos de registro de la base de datos de MongoDB
"""
from sys import path
from pymongo import MongoClient
from json import dump
path.append('src')
from LoadSetupData import load_config

minutos = 1  #AQUI PON LOS MINUTOS

config = load_config()

# Configuración
host = config['db_host']
port = int(config['db_port'])
db_name = config['db_backup_name']
collection_name = "accelerations"

# Conexión a MongoDB
client = MongoClient(host, port)
db = client[db_name]
collection = db[collection_name]

# Obtener el timestamp más reciente en la base de datos
most_recent_doc = collection.find_one(sort=[("timestamp", -1)])
if not most_recent_doc:
    print("No se encontraron datos en la colección.")
    exit()

max_timestamp = most_recent_doc["timestamp"]
thirty_minutes_ago = max_timestamp - (minutos * 60)  # 30 minutos hacia atrás desde el timestamp más reciente

# Filtrar datos de los últimos 30 minutos desde el timestamp más reciente
query = {"timestamp": {"$gte": thirty_minutes_ago}}
results = list(collection.find(query))

# Convertir ObjectId a string para que sea serializable a JSON
for result in results:
    result["_id"] = str(result["_id"])

# Exportar datos a un archivo JSON
output_file = "last_30_minutes.json"
with open(output_file, "w") as file:
    dump(results, file, indent=4)

print(f"Datos exportados a '{output_file}'")
