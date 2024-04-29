import sqlite3



# Define la ruta a tu base de datos
# db_path = 'Accelerations/acchr.db'
db_path =  'Accelerations/aceleraciones.db'

# Conectar a la base de datos
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Consulta SQL para seleccionar los últimos 10 registros ordenados por timestamp
query_last_n = '''
SELECT * FROM acceleration_data
ORDER BY time DESC
LIMIT 3
'''

# Consulta SQL para obtener el total de registros en la base de datos
query_total_records = '''
SELECT COUNT(*) FROM acceleration_data
'''

# Ejecutar consulta para obtener los últimos 10 registros ordenados por timestamp
c.execute(query_last_n)
last_n_records = c.fetchall()

# Ejecutar consulta para obtener el total de registros en la base de datos
c.execute(query_total_records)
total_records = c.fetchone()[0]

# Consulta SQL para obtener la cantidad de segundos de muestra
query_sample_seconds = '''
SELECT MAX(time) - MIN(time) FROM acceleration_data
'''

# Ejecutar consulta para obtener la cantidad de segundos de muestra
c.execute(query_sample_seconds)
sample_seconds = c.fetchone()[0]

# Cerrar la conexión a la base de datos
conn.close()

# Imprimir los últimos n registros ordenados por timestamp
print("Últimos n registros ordenados por timestamp:")
for record in last_n_records:
    print(record)

# Imprimir el total de registros en la base de datos
print("Total de registros en la base de datos:", total_records)

# Imprimir la cantidad de segundos de muestra
print("Cantidad de segundos de muestra:", sample_seconds)

# Conectar a la base de datos
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Consulta SQL para seleccionar los últimos 2 registros ordenados por timestamp
query_last_2 = '''
SELECT * FROM acceleration_data
ORDER BY time DESC
LIMIT 2
'''
# Ejecutar consulta para obtener los últimos 2 registros ordenados por timestamp
c.execute(query_last_2)
last_2_records = c.fetchall()

# Cerrar la conexión a la base de datos
conn.close()

# Calcular y imprimir la diferencia de tiempo entre el último y el penúltimo registro
if len(last_2_records) == 2:
    time_difference = last_2_records[0][0] - last_2_records[1][0]
    print("Diferencia de tiempo entre el último y penúltimo registro:", time_difference, "segundos")

print("Frecuencia de muestreo real:", 1/time_difference,  "Hz")

