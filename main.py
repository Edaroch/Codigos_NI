import sys
# Asegurarte de que Python pueda encontrar los scripts en la subcarpeta src
sys.path.append('src')

from DataAcquisitionContMultiProc import main as run_data_acquisition
from ReadData import main as read_data

def main():

    # Configuración de la captura
    deviceName = 'cDAQ9185-21DA9E1'
    total_capture_time = 0  # Configurado a 5 minutos para captura limitada por tiempo, 0 para continua
    original_rate = 6400  # Frecuencia de muestreo original en Hz
    decimation_factor = 16  # Factor de decimación para obtener 400 Hz
    min_val = -0.006
    max_val = 0.006
    sensitivity = 10.0
    buffer_size = 6400
    number_of_sensors = 6

    db_path = "Accelerations/aceleraciones.db"

    print("Iniciando la adquisición de datos. Presiona ENTER para cerrar")
    run_data_acquisition(deviceName, total_capture_time, original_rate, decimation_factor, min_val, max_val, sensitivity, buffer_size, number_of_sensors, db_path)  # Llama a la función main del script de adquisición de datos.
    read_data()  # Llama a la función main del script de lectura de datos.

if __name__ == "__main__":
    main()
    
