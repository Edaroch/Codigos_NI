import psutil
import time

def monitor_resources(interval=1, duration=60):
    # Monitorear recursos durante un minuto cada segundo
    start_time = time.time()
    while time.time() - start_time < duration:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        print(f"CPU Usage: {cpu}%, Memory Usage: {memory}%")
        time.sleep(interval - 1)  # ajustar el tiempo de sueño si es necesario

# Llamar a la función en una nueva línea de tu script
monitor_resources()