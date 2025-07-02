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
from load_setup_data import load_config  # Importar load_config desde LoadSetupData.py


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


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event):
        # Crear la ventana emergente para el tooltip
        x, y, _, _ = self.widget.bbox("insert")  # Obtener la posición del widget
        x += self.widget.winfo_rootx() + 20  # Desplazar el tooltip ligeramente a la derecha
        y += self.widget.winfo_rooty() + 20  # Desplazar el tooltip ligeramente hacia abajo

        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)  # Sin bordes
        self.tooltip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tooltip, text=self.text, background="White", relief="solid", borderwidth=1)
        label.pack()

    def hide_tooltip(self, event):
        # Cerrar la ventana del tooltip
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None



class AcquisitionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Data Acquisition Control Panel")
        self.root.geometry('1200x800')  # Ajustar tamaño de la ventana
        self.auto_update = False  # Flag para autoactualización
        self.main_process = None  # Almacena el proceso main.py




        # Realizar copia de seguridad del archivo SETUP.txt
        self.backup_setup_file()

        # Cargar la configuración actual de SETUP.txt
        self.config = load_config()



        # Variables para organizar las secciones del archivo
        self.sections = {
            "CAPTURE SETUP": ["total_capture_time", "backup_time", "restart_time", "debug"],
            "DAQ SETUP": [
                "deviceName", "original_rate", "buffer_size", "decimation_factor",
                "daq_num_modules", "daq_ch_per_module", "unused_ch"
            ],
            "SENSOR SETUP": ["min_val", "max_val", "sensitivity"],
            "DATABASES SETUP": ["db_path","sqlite_name", "db_host", "db_port", "db_backup_name"]
        }

        # Explicaciones de las variables
        self.explanations = {
            "deviceName": "Name of the data acquisition device. Check in NI-MAX for the name, e.g., cDAQ9185-21DAXXX",
            "total_capture_time": "Total capture time in seconds (0 for continuous capture).",
            "original_rate": "Original sampling frequency in Hz. Use values above 1000 for NI DAQ and apply decimation.",
            "buffer_size": "Buffer size for data capture. This information is sent to the DAQ. If you take data at 200Hz and your buffer is 400Hz, the DAQ will send data every 2 seconds.",
            "decimation_factor": "Factor to reduce the sampling frequency.",
            "min_val": "Minimum expected value in measurements (sensor). Check the sensor's technical datasheet.",
            "max_val": "Maximum expected value in measurements (sensor). Check the sensor's technical datasheet.",
            "sensitivity": "Sensor sensitivity. Check the sensor's technical datasheet.",
            "daq_num_modules": "Number of modules connected to the DAQ. The modules must be connected to the DAQ in ascending order.",
            "daq_ch_per_module": "Number of channels per module.",
            "unused_ch": "Unused channels. Use NaN for all sensors. Two-digit numbers separated by commas (e.g., 20, 22), where ij: i -> module number; j -> channel number.",
            "debug": "Enable debug mode (True/False).",
            "db_host": "MongoDB host.",
            "db_port": "MongoDB port.",
            "db_path": "SQLite database path.",
            "sqlite_name": "SQLite database name. Change the name if you want to save it in a new database. Use 'accelerations' by default.",
            "db_backup_name": "Name of the database for historical storage.",
            "backup_time": "Time in seconds to back up the buffer to the raw database.",
            "restart_time": "Example: '10s' every ten seconds, '1h' for an hour, '1d' for a day."
        }

        # Variables de entrada de los parámetros
        self.entries = {}

        # Variable para rastrear si los datos fueron actualizados
        self.is_updated = False

        # Diccionario para almacenar los checkboxes dinámicos de sensores
        self.sensor_selection = {}  


        # Crear el panel principal con scrollbar
        self.create_scrollable_panel()

        # Consola de salida
        self.console_output = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, width=200, height=15)
        self.console_output.pack(pady=10)
        self.update_console(
'''INSTRUCTIONS:
- Modify the default values if necessary and press 'Update Data' to save the configuration.
- Then, press the 'Run' button to start the capture process.
- To stop the capture, access the console, press ENTER, and manually close the console.
- For non-continuous captures, use a backup time of 0. Before restarting the capture, change the database name if you want to save it in a new one.
- Restart Time is the time in seconds to automatically restart the capture. If set to 0s, it will not restart and will accumulate a processing delay. This parameter is useful for clearing the buffer and will depend on the computer's capacity. It is recommended to set it once per day.
- Remember to save your last configuration before closing the program if desired.
'''
        )

        # Gráfico bajo la consola de salida
        self.create_plot_panel()

        # Botones de control
        self.create_control_buttons()

        # Manejar evento de cierre de ventana
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Verificar si existe la base de datos
        db_path = self.config.get("sqlite_db_path", "")
        if not db_path or not os.path.exists(db_path):
            self.update_console("Database not found at the specified path. Some functions will be disabled.")


        
    def backup_setup_file(self):
        """Creates a backup of the SETUP.txt file"""
        try:
            shutil.copyfile('SETUP.txt', 'setupbak.txt')
            # print("Copia de seguridad de SETUP.txt creada.")
        except Exception as e:
            print(f"Error creating the backup: {e}")

    def restore_setup_file(self):
        """Restores the SETUP.txt file from the backup"""
        try:
            shutil.copyfile('setupbak.txt', 'SETUP.txt')
            print("SETUP.txt restored from backup.")
            self.update_console("SETUP.txt file restored to its original state.")
        except Exception as e:
            print(f"Error restoring SETUP.txt: {e}")
            self.update_console(f"Error restoring SETUP.txt: {e}")

    def delete_backup_file(self):
        """Deletes the backup of the SETUP.txt file"""
        try:
            os.remove('setupbak.txt')
            # print("Copia de seguridad eliminada.")
        except Exception as e:
            print(f"Error deleting the backup: {e}")

    def create_scrollable_panel(self):
        """Creates a scrollable panel for configurations with a fixed width"""
        # Establecer el ancho fijo que deseas para el canvas
        fixed_width = 350  # Por ejemplo, un ancho fijo de 300 píxeles

        canvas = tk.Canvas(self.root, width=fixed_width)  # Fijar el ancho del canvas
        scroll_y = tk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll_y.set)

        # Ajustar el canvas y el scrollbar
        canvas.pack(side="left", fill=tk.Y)  # Aquí solo usamos fill=tk.Y para que el ancho sea fijo
        scroll_y.pack(side="right", fill=tk.Y)

        self.create_setup_panel(scrollable_frame)

    def create_setup_panel(self, parent):
        """Creates the configuration panel content with proper alignment."""
        for section, keys in self.sections.items():
            # Etiqueta del título de la sección (centrado)
            section_label = tk.Label(parent, text=section, font=("Helvetica", 12, "bold"))
            section_label.pack(pady=5)

            # Marco para las filas dentro de la sección
            section_frame = tk.Frame(parent)
            section_frame.pack(pady=5, fill=tk.X)  # Expandir para ocupar todo el ancho

            for row, key in enumerate(keys):
                value = self.config.get(key, "")
                
                # Nombre de la variable (columna 0)
                variable_label = tk.Label(section_frame, text=key, anchor="w", width=20)
                variable_label.grid(row=row, column=0, padx=10, pady=5, sticky="w")
                
                # Cuadro de texto para editar el valor (columna 1)
                entry = tk.Entry(section_frame, width=20)
                entry.insert(0, str(value))
                entry.grid(row=row, column=1, padx=10, pady=5, sticky="w")
                self.entries[key] = entry
                
                # Descripción del tooltip (se asocia al Label de la variable)
                description_text = self.explanations.get(key, "No description available")
                
                # Crear el tooltip para el label de la variable
                ToolTip(variable_label, description_text)
            

    def create_plot_panel(self):
        """Creates a panel to display the plot and dynamic checkboxes."""
        plot_frame = tk.Frame(self.root)
        plot_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # Crear sub-marco para botones y actualización automática
        button_frame = tk.Frame(plot_frame)
        button_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        # Checkbox para autoactualización
        self.auto_update_var = tk.IntVar()
        tk.Checkbutton(
            button_frame, text="Auto-update", variable=self.auto_update_var, command=self.toggle_auto_update
        ).pack(side=tk.LEFT, padx=5)

        # Botón para actualizar el gráfico manualmente
        tk.Button(button_frame, text="Plot Once", command=self.update_plot).pack(side=tk.LEFT, padx=5)

        # Botón para consultar nuevamente la base de datos
        tk.Button(button_frame, text="Find Sensors", command=self.update_sensor_checkboxes).pack(side=tk.LEFT, padx=5)

        # Cuadro para mostrar el desfase de tiempo
        self.time_lag_label = tk.Label(button_frame, text="Time Lag: 0.00s", width=20, anchor="w", relief=tk.SUNKEN)
        self.time_lag_label.pack(side=tk.LEFT, padx=5)

        # Crear el gráfico inicial
        self.figure = plt.Figure(figsize=(10, 2), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title('Last 20 seconds of recorded data')
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel('Acceleration (m/s²)')
        self.ax.grid(True)

        # Contenedor para el gráfico
        graph_frame = tk.Frame(plot_frame)
        graph_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = FigureCanvasTkAgg(self.figure, master=graph_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=(0, 0))

        # Panel para checkboxes dinámicos de sensores
        self.checkbox_frame = tk.Frame(plot_frame)
        self.checkbox_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        # Crear checkboxes dinámicos basados en los sensores detectados
        self.update_sensor_checkboxes()






    def update_sensor_checkboxes(self):
        """Updates the checkboxes to reflect the sensors detected in the database."""
        # Guardar estados previos de los sensores
        previous_states = {sensor: var.get() for sensor, var in self.sensor_selection.items()}

        # Detectar ruta de la base de datos desde la configuración
        db_path = self.config.get("sqlite_db_path", "")
        if not db_path or not os.path.exists(db_path):
            self.update_console("Error: Database not found at the specified path.")
            self.disable_checkboxes()
            return

        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")

                # Comprobar si existen las tablas necesarias
                query_tables = "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sensors', 'accelerations', 'timestamps')"
                existing_tables = [row[0] for row in conn.execute(query_tables).fetchall()]
                required_tables = {'sensors', 'accelerations', 'timestamps'}

                if not required_tables.issubset(set(existing_tables)):
                    self.update_console("Error: The database does not contain the necessary tables.")
                    self.disable_checkboxes()
                    return

                # Obtener sensores de los últimos 20 segundos
                query = """
                    SELECT DISTINCT s.sensor_number
                    FROM sensors s
                    JOIN accelerations a ON s.id = a.sensor_id
                    JOIN timestamps t ON t.id = a.timestamp_id
                    WHERE t.timestamp > (SELECT MAX(timestamp) - 20 FROM timestamps)
                """
                sensor_numbers = sorted([row[0] for row in conn.execute(query).fetchall()])

            if not sensor_numbers:
                self.update_console("No sensors detected in the last 20 seconds.")
                self.disable_checkboxes()
                return

            # Verificar si la cantidad de sensores ha cambiado
            if len(sensor_numbers) == len(self.sensor_selection) and all(sensor in self.sensor_selection for sensor in sensor_numbers):
                # Si no hay cambios en la cantidad de sensores, no hacer el refresh
                return

            # Limpiar el diccionario y eliminar widgets si hay cambios
            self.sensor_selection.clear()
            for widget in self.checkbox_frame.winfo_children():
                widget.destroy()

            # Crear checkboxes dinámicos organizados por columna y fila
            for sensor in sensor_numbers:
                # Calcular columna y fila según el esquema
                col = int(str(sensor)[0])  # Primer dígito para columna
                row = int(str(sensor)[1])  # Segundo dígito para fila

                # Restaurar estado previo si existe, sino por defecto True
                state = previous_states.get(sensor, True)
                var = tk.BooleanVar(value=state)
                chk = tk.Checkbutton(self.checkbox_frame, text=f"Sensor {sensor}", variable=var)
                chk.grid(row=row, column=col, padx=5, pady=5, sticky="w")
                self.sensor_selection[sensor] = var

        except Exception as e:
            self.update_console(f"Error loading data from the database: {e}")
            self.disable_checkboxes()

    def disable_checkboxes(self):
        """Desactiva los checkboxes y muestra un mensaje en la interfaz."""
        self.sensor_selection.clear()
        for widget in self.checkbox_frame.winfo_children():
            widget.destroy()
        tk.Label(self.checkbox_frame, text="No Sensors currently available").grid(row=0, column=0)



    def load_last_20_seconds(self):
        """
        Carga los datos de los últimos 20 segundos registrados desde SQLite.
        Solo carga los datos de los sensores seleccionados.
        """
        db_path = self.config.get("sqlite_db_path", "")
        if not db_path or not os.path.exists(db_path):
            self.update_console("No database found at the specified path. Plot not updated.")
            return pd.DataFrame()

        # Obtener sensores seleccionados
        selected_sensors = [sensor for sensor, var in self.sensor_selection.items() if var.get()]

        try:
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
                    WHERE t.timestamp BETWEEN ? AND ? AND s.sensor_number IN ({','.join(['?'] * len(selected_sensors))})
                    ORDER BY t.timestamp ASC
                """
                df = pd.read_sql_query(query, conn, params=(start_timestamp, end_timestamp, *selected_sensors))
        except Exception as e:
            self.update_console(f"Error al cargar datos desde la base de datos: {e}")
            return pd.DataFrame()

        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df


    def update_plot(self):
        """
        Updates the plot with the last 20 seconds of recorded data.
        """
        # Verificar si hay una base de datos antes de actualizar el gráfico
        db_path = self.config.get("sqlite_db_path", "")
        if not db_path or not os.path.exists(db_path):
            self.update_console("No database found at the specified path. Plot not updated.")
            self.auto_update_var.set(0)  # Desactivar la actualización automática
            return

        df = self.load_last_20_seconds()
        self.ax.clear()
        self.ax.set_title('Last 20 seconds of recorded data')
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel('Acceleration (m/s²)')
        self.ax.grid(True)

        if not df.empty:
            for sensor in df['sensor_number'].unique():
                sensor_data = df[df['sensor_number'] == sensor]
                self.ax.plot(sensor_data['timestamp'], sensor_data['acceleration_value'], label=f"Sensor {sensor}")

            self.ax.legend(loc='upper right')

            # Calcular desfase entre el último timestamp y el tiempo actual
            last_timestamp = df['timestamp'].max()
            current_time = pd.Timestamp.now()
            time_lag = (current_time - (last_timestamp)).total_seconds()

            # Actualizar el cuadro de desfase
            self.time_lag_label.config(text=f"Time Lag: {time_lag:.2f}s")

        else:
            # Si no hay datos, establecer desfase a 0
            self.time_lag_label.config(text="Time Lag: 0.00s")

        self.canvas.draw()



    def toggle_auto_update(self):
        """Enables or disables auto-updating of the plot."""
        if self.auto_update_var.get():
            self.auto_update = True
            self.auto_update_plot()
        else:
            self.auto_update = False

    def auto_update_plot(self):
        """Automatically updates the plot every 2 seconds if enabled."""
        if self.auto_update:
            self.update_plot()
            self.root.after(1000, self.auto_update_plot)

    def execute_main(self):
        # Guardar la configuración actualizada
        self.update_config()

        # Ejecutar main.py en un nuevo cmd
        self.update_console("Running main.py in a new console window...")
        if os.name == 'nt':  # Windows
            subprocess.Popen(['start', 'cmd', '/k', 'python', 'main.py'], shell=True)
        else:  # Linux, macOS
            subprocess.Popen(['x-terminal-emulator', '-e', 'python main.py'])

        self.update_console("Process running. Press ENTER in the console to stop and then manually close the console.")



    def update_console(self, message):
        self.console_output.config(state=tk.NORMAL)  # Habilitar escritura
        self.console_output.insert(tk.END, message + "\n")
        self.console_output.see(tk.END)  # Desplazar al final automáticamente
        self.console_output.config(state=tk.DISABLED)  # Deshabilitar escritura

    def on_closing(self):
        if self.is_updated:
            if messagebox.askyesno("Save changes", "Do you want to save changes before exiting?"):
                self.update_config()
            else:
                self.restore_setup_file()
                self.update_console("Changes discarded. SETUP.txt restored.")
        else:
            self.update_console("No changes were made.")
        self.delete_backup_file()
        self.root.destroy()

    def update_config(self):
        """Updates the configuration with values entered in the text fields."""
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
        self.update_console("Configuration data updated in SETUP.txt.")

    def create_control_buttons(self):
        """Creates the control buttons."""
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        execute_button = tk.Button(button_frame, text="Run", command=self.execute_main)
        execute_button.grid(row=0, column=0, padx=10)

        update_button = tk.Button(button_frame, text="Update Data", command=self.update_config)
        update_button.grid(row=0, column=2, padx=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = AcquisitionGUI(root)
    root.mainloop()
