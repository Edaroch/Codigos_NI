import sys
sys.path.append('src')  # Añadir la carpeta 'src' al path
import shutil
import os
import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
from LoadSetupData import load_config  # Importar load_config desde LoadSetupData.py


# Función para guardar la configuración sin borrar comentarios ni agregar líneas en blanco
def save_config(config):
    with open('SETUP.txt', 'r') as file:
        lines = file.readlines()

    with open('SETUP.txt', 'w') as file:
        for line in lines:
            line_stripped = line.strip()
            if line_stripped and not line_stripped.startswith('#'):  # Si no es comentario
                key = line_stripped.split(': ')[0]  # Obtiene la clave (por ejemplo, 'deviceName')
                if key in config:
                    # Escribir el valor actualizado en la línea
                    value = config[key]
                    if key == 'debug':
                        value = 'true' if value else 'false'
                    # Mantener comentario original y escribir sin agregar espacios adicionales
                    if '#' in line:
                        file.write(f"{key}: {value} {line[line.index('#'):]}")  # Mantener el comentario
                    else:
                        file.write(f"{key}: {value}\n")
                else:
                    file.write(line)  # Mantener la línea tal como está si no es clave conocida
            else:
                file.write(line)  # Escribir comentarios y líneas vacías sin modificar


class AcquisitionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Data Acquisition Control Panel")
        self.root.geometry('1000x950')  # Ajustar tamaño para mejor visualización

        # Realizar copia de seguridad del archivo SETUP.txt
        self.backup_setup_file()

        # Cargar la configuración actual de SETUP.txt
        self.config = load_config()

        # Explicaciones de las variables
        self.explanations = {
            "deviceName": "Nombre del dispositivo de adquisición de datos.",
            "total_capture_time": "Tiempo total de captura en segundos (0 para captura continua).",
            "original_rate": "Frecuencia de muestreo original en Hz.",
            "buffer_size": "Tamaño del buffer para la captura de datos.",
            "decimation_factor": "Factor para reducir la frecuencia de muestreo.",
            "min_val": "Valor mínimo esperado en las mediciones (sensor).",
            "max_val": "Valor máximo esperado en las mediciones (sensor).",
            "sensitivity": "Sensibilidad del sensor.",
            "daq_num_modules": "Número de módulos conectados al DAQ.",
            "daq_ch_per_module": "Número de canales por módulo.",
            "unused_ch": "Canales no utilizados.",
            "debug": "Activar modo de depuración (True/False).",
            "db_host": "Host de MongoDB.",
            "db_port": "Puerto de MongoDB.",
            "db_name": "Nombre de la base de datos temporal en tiempo real.",
            "db_backup_name": "Nombre de la base de datos para almacenamiento histórico.",
            "backup_time": "Tiempo en segundos para respaldo del buffer a la base de datos raw.",
            "restart_time": "0 para captura continua. Ejemplo: '10s' cada diez segundos, '1d' para un día."
        }

        # Variables de entrada de los parámetros
        self.entries = {}

        # Variable para rastrear si los datos fueron actualizados
        self.is_updated = False

        # Crear el panel para editar los valores de SETUP.txt
        self.create_setup_panel()

        # Consola de salida (más alta para mejor visibilidad)
        self.console_output = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, width=100, height=15)
        self.console_output.pack(pady=10)

        # Botones de control
        self.create_control_buttons()

        # Manejar evento de cierre de ventana
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def backup_setup_file(self):
        """Crea una copia de seguridad del archivo SETUP.txt"""
        try:
            shutil.copyfile('SETUP.txt', 'setupbak.txt')
            print("Copia de seguridad de SETUP.txt creada.")
        except Exception as e:
            print(f"Error al crear la copia de seguridad: {e}")

    def restore_setup_file(self):
        """Restaura el archivo SETUP.txt desde la copia de seguridad"""
        try:
            shutil.copyfile('setupbak.txt', 'SETUP.txt')
            print("SETUP.txt restaurado desde la copia de seguridad.")
        except Exception as e:
            print(f"Error al restaurar SETUP.txt: {e}")

    def delete_backup_file(self):
        """Elimina la copia de seguridad del archivo SETUP.txt"""
        try:
            os.remove('setupbak.txt')
            print("Copia de seguridad eliminada.")
        except Exception as e:
            print(f"Error al eliminar la copia de seguridad: {e}")

    def create_setup_panel(self):
        # Panel de configuración
        setup_frame = tk.Frame(self.root)
        setup_frame.pack(pady=10)

        # Crear entradas para cada clave en el archivo SETUP.txt
        row = 0
        for key, value in self.config.items():
            tk.Label(setup_frame, text=key).grid(row=row, column=0, padx=10, pady=5)  # Nombre de la variable
            entry = tk.Entry(setup_frame)
            entry.insert(0, str(value))
            entry.grid(row=row, column=1, padx=10, pady=5)  # Campo editable
            self.entries[key] = entry
            tk.Label(setup_frame, text=self.explanations.get(key, "No description available")).grid(row=row, column=2, padx=10, pady=5)  # Explicación
            row += 1

    def create_control_buttons(self):
        # Botones para ejecutar y actualizar
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        execute_button = tk.Button(button_frame, text="Ejecutar", command=self.execute_main)
        execute_button.grid(row=0, column=0, padx=10)

        update_button = tk.Button(button_frame, text="Actualizar Datos", command=self.update_config)
        update_button.grid(row=0, column=1, padx=10)

    def update_console(self, message):
        self.console_output.insert(tk.END, message + "\n")
        self.console_output.see(tk.END)  # Auto scroll to the end

    def update_config(self):
        # Actualizar la configuración con los nuevos valores de los campos
        for key, entry in self.entries.items():
            value = entry.get()
            # Convertir tipos numéricos si es necesario
            if key in ["total_capture_time", "original_rate", "buffer_size", "decimation_factor", "db_port", "backup_time"]:
                value = int(value)
            elif key in ["min_val", "max_val", "sensitivity"]:
                value = float(value)
            elif key == "debug":
                value = value.lower() == 'true'  # Convertir a booleano
            self.config[key] = value

        # Marcar que los datos fueron actualizados
        self.is_updated = True

        # Guardar los nuevos valores en el archivo SETUP.txt
        save_config(self.config)
        self.update_console("Datos de configuración actualizados en SETUP.txt.")

    def execute_main(self):
        # Guardar la configuración actualizada
        self.update_config()

        # Ejecutar main.py en un nuevo cmd
        self.update_console("Ejecutando main.py en una nueva ventana de consola...")
        if os.name == 'nt':  # Windows
            subprocess.Popen(['start', 'cmd', '/k', 'python', 'main.py'], shell=True)
        else:  # Linux, macOS
            subprocess.Popen(['x-terminal-emulator', '-e', 'python main.py'])

        self.update_console("Proceso ejecutándose. Presiona ENTER en la consola para detener y luego cierra manualmente.")

    def on_closing(self):
        # Verificar si hubo actualizaciones y preguntar si se deben guardar
        if self.is_updated:
            if messagebox.askyesno("Guardar cambios", "¿Deseas guardar los cambios antes de salir?"):
                self.update_config()  # Guardar si el usuario elige 'Sí'
            else:
                self.restore_setup_file()  # Restaurar el archivo original si elige 'No'
                self.update_console("Cambios descartados. SETUP.txt restaurado.")
        else:
            self.update_console("No se realizaron cambios.")

        # Eliminar el archivo de respaldo después de cerrar
        self.delete_backup_file()

        self.root.destroy()  # Cerrar la ventana


if __name__ == "__main__":
    root = tk.Tk()
    app = AcquisitionGUI(root)
    root.mainloop()