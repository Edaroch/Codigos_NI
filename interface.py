import sys
sys.path.append('src')  # Añadir la carpeta 'src' al path
import shutil
import os
import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import timedelta
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
        self.root.geometry('1200x750')  # Ajustar tamaño de la ventana
        self.auto_update = False  # Flag para autoactualización
        self.main_process = None  # Almacena el proceso main.py

        # Realizar copia de seguridad del archivo SETUP.txt
        self.backup_setup_file()

        # Cargar la configuración actual de SETUP.txt
        self.config = load_config()

        # Variables para organizar las secciones del archivo
        self.sections = {
            "CONFIGURACION DE CAPTURA": ["total_capture_time", "backup_time", "restart_time", "debug"],
            "CONFIGURACION DEL DAQ": [
                "deviceName", "original_rate", "buffer_size", "decimation_factor",
                "daq_num_modules", "daq_ch_per_module", "unused_ch"
            ],
            "CONFIGURACION DE LOS SENSORES": ["min_val", "max_val", "sensitivity"],
            "CONFIGURACION BASES DE DATOS": ["sqlite_db_path", "db_host", "db_port", "db_backup_name"]
        }

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
            "sqlite_db_path": "Ruta y nombre de la base de datos SQLite.",
            "db_backup_name": "Nombre de la base de datos para almacenamiento histórico.",
            "backup_time": "Tiempo en segundos para respaldo del buffer a la base de datos raw.",
            "restart_time": "Ejemplo: '10s' cada diez segundos, '1h' para cada hora, '1d' para cada día."
        }

        # Variables de entrada de los parámetros
        self.entries = {}

        # Variable para rastrear si los datos fueron actualizados
        self.is_updated = False

        # Crear el panel principal con scrollbar
        self.create_scrollable_panel()

        # Consola de salida
        self.console_output = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, width=60, height=20)
        self.console_output.pack(pady=10)
        self.update_console(
'''INSTRUCCIONES: 
- Modifica los valores por defecto si fuese necesario y presiona 'Actualizar Datos' para guardar la configuración. 
- Luego presiona el botón 'Ejecutar' para iniciar el proceso de captura. 
- Para detener la captura, accede a la consola, presiona ENTER y cierra manualmente la consola. 
- Para capturas que no sean continuas, utiliza un tiempo de backup 0. Antes de reiniciar la captura, cambia el nombre de la base de datos para guardar en una nueva si asi lo deseas. 
- Restart Time es el tiempo en segundos para reiniciar automáticamente la captura. Si se establece en 0s, no se reiniciará e irá acumulando un retraso de procesado de los datos. Este parámetro es útil para limpiar el buffer y dependerá de la capacidad del ordenador. 
'''
        )

        # Gráfico bajo la consola de salida
        self.create_plot_panel()

        # Botones de control
        self.create_control_buttons()

        # Manejar evento de cierre de ventana
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def backup_setup_file(self):
        """Crea una copia de seguridad del archivo SETUP.txt"""
        try:
            shutil.copyfile('SETUP.txt', 'setupbak.txt')
            # print("Copia de seguridad de SETUP.txt creada.")
        except Exception as e:
            print(f"Error al crear la copia de seguridad: {e}")

    def restore_setup_file(self):
        """Restaura el archivo SETUP.txt desde la copia de seguridad"""
        try:
            shutil.copyfile('setupbak.txt', 'SETUP.txt')
            print("SETUP.txt restaurado desde la copia de seguridad.")
            self.update_console("Archivo SETUP.txt restaurado a su estado original.")
        except Exception as e:
            print(f"Error al restaurar SETUP.txt: {e}")
            self.update_console(f"Error al restaurar SETUP.txt: {e}")

    def delete_backup_file(self):
        """Elimina la copia de seguridad del archivo SETUP.txt"""
        try:
            os.remove('setupbak.txt')
            # print("Copia de seguridad eliminada.")
        except Exception as e:
            print(f"Error al eliminar la copia de seguridad: {e}")

    def create_scrollable_panel(self):
        """Crea un panel desplazable para las configuraciones"""
        canvas = tk.Canvas(self.root)
        scroll_y = tk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll_y.set)

        canvas.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        self.create_setup_panel(scrollable_frame)

    def create_setup_panel(self, parent):
        """Crea el contenido del panel de configuración"""
        for section, keys in self.sections.items():
            tk.Label(parent, text=section, font=("Helvetica", 12, "bold")).pack(pady=5)
            section_frame = tk.Frame(parent)
            section_frame.pack(pady=5)

            for key in keys:
                value = self.config.get(key, "")
                tk.Label(section_frame, text=key).grid(row=keys.index(key), column=0, padx=10, pady=5)
                entry = tk.Entry(section_frame)
                entry.insert(0, str(value))
                entry.grid(row=keys.index(key), column=1, padx=10, pady=5)
                self.entries[key] = entry
                tk.Label(section_frame, text=self.explanations.get(key, "No description available")).grid(
                    row=keys.index(key), column=2, padx=10, pady=5
                )
            

    def create_plot_panel(self):
        """Crea un panel para mostrar el gráfico."""
        plot_frame = tk.Frame(self.root)
        plot_frame.pack(pady=20, fill=tk.BOTH, expand=True)

        # Crear el gráfico inicial vacío
        self.figure = plt.Figure(figsize=(5, 2), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title('Últimos 20 segundos de datos registrados')
        self.ax.set_xlabel('Tiempo')
        self.ax.set_ylabel('Aceleración (m/s^2)')
        self.ax.grid(True)

        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Checkbox para autoactualización
        self.auto_update_var = tk.IntVar()
        tk.Checkbutton(
            plot_frame, text="Actualización automática", variable=self.auto_update_var, command=self.toggle_auto_update
        ).pack(side=tk.LEFT, padx=5)

        # Botón para actualizar el gráfico manualmente
        tk.Button(plot_frame, text="Actualizar Gráfico", command=self.update_plot).pack(side=tk.LEFT, padx=5)

    def load_last_20_seconds(self):
        """
        Carga los datos de los últimos 20 segundos registrados desde SQLite.
        """
        db_path = self.config.get("sqlite_db_path", "")
        if not db_path:
            return pd.DataFrame()

        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            # Obtener el último timestamp registrado
            query_max = "SELECT MAX(timestamp) as max_time FROM timestamps"
            max_time = pd.read_sql_query(query_max, conn)['max_time'].iloc[0]
            if max_time is None:
                return pd.DataFrame()  # Si no hay datos, retornar vacío
            end_timestamp = max_time
            start_timestamp = end_timestamp - 20  # Últimos 20 segundos

            query = f"""
                SELECT t.timestamp, s.sensor_number, a.acceleration_value
                FROM accelerations a
                JOIN timestamps t ON a.timestamp_id = t.id
                JOIN sensors s ON a.sensor_id = s.id
                WHERE t.timestamp BETWEEN ? AND ?
                ORDER BY t.timestamp ASC
            """
            df = pd.read_sql_query(query, conn, params=(start_timestamp, end_timestamp))

        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df

    def update_plot(self):
        """
        Actualiza el gráfico con los últimos 20 segundos de datos registrados.
        """
        df = self.load_last_20_seconds()
        self.ax.clear()
        self.ax.set_title('Últimos 20 segundos de datos registrados')
        self.ax.set_xlabel('Tiempo')
        self.ax.set_ylabel('Aceleración (m/s^2)')
        self.ax.grid(True)

        if not df.empty:
            for sensor in df['sensor_number'].unique():
                sensor_data = df[df['sensor_number'] == sensor]
                self.ax.plot(sensor_data['timestamp'], sensor_data['acceleration_value'], label=f"Sensor {sensor}")

            self.ax.legend(loc='upper right')

        self.canvas.draw()

    def toggle_auto_update(self):
        """Activa o desactiva la autoactualización del gráfico."""
        if self.auto_update_var.get():
            self.auto_update = True
            self.auto_update_plot()
        else:
            self.auto_update = False

    def auto_update_plot(self):
        """Actualiza el gráfico automáticamente cada 2 segundos si está activado."""
        if self.auto_update:
            self.update_plot()
            self.root.after(2000, self.auto_update_plot)

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



    def update_console(self, message):
        self.console_output.insert(tk.END, message + "\n")
        self.console_output.see(tk.END)  # Auto scroll to the end

    def on_closing(self):
        if self.is_updated:
            if messagebox.askyesno("Guardar cambios", "¿Deseas guardar los cambios antes de salir?"):
                self.update_config()
            else:
                self.restore_setup_file()
                self.update_console("Cambios descartados. SETUP.txt restaurado.")
        else:
            self.update_console("No se realizaron cambios.")
        self.delete_backup_file()
        self.root.destroy()

    def update_config(self):
        """Actualiza la configuración con los valores ingresados en los campos de texto."""
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

    def create_control_buttons(self):
        """Crea los botones de control"""
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        execute_button = tk.Button(button_frame, text="Ejecutar", command=self.execute_main)
        execute_button.grid(row=0, column=0, padx=10)

        update_button = tk.Button(button_frame, text="Actualizar Datos", command=self.update_config)
        update_button.grid(row=0, column=2, padx=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = AcquisitionGUI(root)
    root.mainloop()
