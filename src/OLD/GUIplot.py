import sys
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from tkinter import Tk, Label, Button, Entry, Frame, Checkbutton, IntVar, messagebox, filedialog, ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime
import matplotlib.dates as mdates
sys.path.append('src')
from LoadSetupData import load_config
from ChkPaths import check_and_create_paths

config = load_config()
db_path, data_path = check_and_create_paths(config)

def load_data_from_database(db_path, end_timestamp, seconds_back):
    # Usar 'with' para manejar automáticamente la conexión a la base de datos
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")  # Activar el modo WAL
        
        # Consulta para obtener el último timestamp registrado
        query = "SELECT max(time) as max_time FROM acceleration_data"
        times = pd.read_sql_query(query, conn)
        max_time = times['max_time'].iat[0]

        # Establecer los timestamps de inicio y fin para la carga de datos
        if end_timestamp == 0:
            end_timestamp = max_time
        start_timestamp = end_timestamp - seconds_back

        # Consulta para cargar datos entre dos timestamps, utilizando parámetros para evitar la inyección de SQL
        query = "SELECT * FROM acceleration_data WHERE time BETWEEN ? AND ? ORDER BY time"
        df = pd.read_sql_query(query, conn, params=(start_timestamp, end_timestamp))

    # Convertir la columna 'time' a formato datetime para mejor manejo en pandas
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def get_sensor_names(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(acceleration_data);")
    info = cursor.fetchall()
    conn.close()
    return [item[1] for item in info if item[1].startswith('sensor')]

def initialize_plot(frame):
    figure = plt.Figure(figsize=(10, 6), dpi=100)
    ax = figure.add_subplot(111)
    ax.set_title('Datos de aceleración a lo largo del tiempo')
    ax.set_xlabel('Tiempo')
    ax.set_ylabel('Aceleración (m/s^2)')
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=20))
    figure.subplots_adjust(left=0.1, right=0.9, top=0.8, bottom=0.3)
    canvas = FigureCanvasTkAgg(figure, master=frame)
    canvas.draw()
    canvas.get_tk_widget().pack(side='top', fill='both', expand=1)
    return ax, canvas

def update_plot(df, ax, canvas, sensor_checks, sensor_names, mark_max, max_value_label):
    ax.clear()
    ax.set_title('Datos de aceleración a lo largo del tiempo')
    ax.set_xlabel('Tiempo')
    ax.set_ylabel('Aceleración (m/s^2)')
    max_value = None
    max_time = None
    max_label = "Max: N/A"
    if not df.empty:
        for i, sensor in enumerate(sensor_names, start=1):
            if sensor_checks[i-1].get():
                data = df[sensor]
                times = df['time']
                ax.plot(times, data, label=f'Sensor {i}')
                if mark_max.get():
                    local_max = data.abs().max()
                    max_time = times[data.abs().idxmax()]
                    if max_value is None or local_max > abs(max_value):
                        max_value = data[data.abs().idxmax()]
                        max_label = f"Max: {max_value:.3f} at {max_time}"
                        ax.scatter([max_time], [max_value], color='red', zorder=5)
                        ax.annotate(f"{max_value:.3f}", xy=(max_time, max_value), textcoords="offset points", xytext=(0,10), ha='center')
    ax.legend(loc='upper right')
    ax.grid(True)
    for label in ax.get_xticklabels():
        label.set_rotation(45)
    canvas.draw()
    max_value_label.config(text=max_label if max_value else "Max: N/A")

def plot_button_clicked(frame, ax, canvas, sensor_checks, sensor_names, mark_max, max_value_label, end_entry, seconds_back_entry, db_path, root):
    end_ts = get_timestamp_from_entry(end_entry)
    seconds_back = int(seconds_back_entry.get() if seconds_back_entry.get() else 0)
    df = load_data_from_database(db_path, end_ts, seconds_back)
    update_plot(df, ax, canvas, sensor_checks, sensor_names, mark_max, max_value_label)
    root.df = df  # Storing the DataFrame in the root for global access

def auto_refresh_toggle(frame, ax, canvas, sensor_checks, sensor_names, mark_max, max_value_label, end_entry, seconds_back_entry, db_path, auto_refresh_var, refresh_rate_entry, root):
    if auto_refresh_var.get():
        plot_button_clicked(frame, ax, canvas, sensor_checks, sensor_names, mark_max, max_value_label, end_entry, seconds_back_entry, db_path, root)
        refresh_rate = max(100, int(refresh_rate_entry.get()))
        root.after(refresh_rate, lambda: auto_refresh_toggle(frame, ax, canvas, sensor_checks, sensor_names, mark_max, max_value_label, end_entry, seconds_back_entry, db_path, auto_refresh_var, refresh_rate_entry, root))

def get_timestamp_from_entry(entry):
    try:
        return int(datetime.strptime(entry.get(), "%Y-%m-%d %H:%M:%S").timestamp())
    except ValueError:
        return 0

def save_plot(figure, max_label):
    file_path = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[("PNG files", "*.png"), ("PDF files", "*.pdf"), ("All files", "*.*")])
    if file_path:
        figure.savefig(file_path)
        with open(f"{file_path}_max_value.txt", "w") as f:
            f.write(max_label)

def save_data(root):
    if hasattr(root, 'df'):  # Check if DataFrame is available
        file_path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if file_path:
            root.df.to_csv(file_path, sep='\t', index=False)

def on_closing(root):
    if messagebox.askokcancel("Cerrar", "¿Quieres cerrar la interfaz?"):
        root.destroy()

def start_gui():
    root = Tk()
    root.title("Visualización de Datos")
    root.geometry('1200x700')

    top_frame = Frame(root)
    top_frame.pack(side='top', fill='x', expand=False)

    Label(top_frame, text="Fecha Fin (AAAA-MM-DD HH:MM:SS) o 0").grid(row=0, column=0)
    end_entry = Entry(top_frame)
    end_entry.grid(row=0, column=1)
    end_entry.insert(0, "0")

    Label(top_frame, text="Segundos atrás").grid(row=0, column=2)
    seconds_back_entry = Entry(top_frame)
    seconds_back_entry.grid(row=0, column=3)
    seconds_back_entry.insert(0, "30")
    
    Label(top_frame, text="Tasa de refresco (ms):").grid(row=1, column=0)
    refresh_rate_entry = Entry(top_frame)
    refresh_rate_entry.grid(row=1, column=1)
    refresh_rate_entry.insert(0, "1000")

    auto_refresh_var = IntVar(root)
    mark_max = IntVar(root)

    Checkbutton(top_frame, text="Marcar máximo", variable=mark_max).grid(row=1, column=3)
    max_value_label = Label(top_frame, text="Max: N/A")
    max_value_label.grid(row=1, column=4)

    sensor_frame = Frame(root)
    sensor_frame.pack(side='left', fill='y')

    plot_frame = Frame(root)
    plot_frame.pack(side='left', fill='both', expand=True)

    ax, canvas = initialize_plot(plot_frame)
    sensor_names = get_sensor_names(db_path)
    sensor_checks = [IntVar(value=1) for _ in sensor_names]

    for i, sensor_name in enumerate(sensor_names):
        Checkbutton(sensor_frame, text=sensor_name, variable=sensor_checks[i]).pack()

    Button(top_frame, text="Graficar Datos", command=lambda: plot_button_clicked(plot_frame, ax, canvas, sensor_checks, sensor_names, mark_max, max_value_label, end_entry, seconds_back_entry, db_path, root)).grid(row=2, column=0)
    Button(top_frame, text="Guardar Gráfico", command=lambda: save_plot(ax.figure, max_value_label['text'])).grid(row=2, column=1)
    Button(top_frame, text="Guardar Datos", command=lambda: save_data(root)).grid(row=2, column=2)
    Checkbutton(top_frame, text="Auto-refresco", variable=auto_refresh_var, command=lambda: auto_refresh_toggle(plot_frame, ax, canvas, sensor_checks, sensor_names, mark_max, max_value_label, end_entry, seconds_back_entry, db_path, auto_refresh_var, refresh_rate_entry, root)).grid(row=1, column=2)

    root.protocol("WM_DELETE_WINDOW", lambda: on_closing(root))
    root.mainloop()

if __name__ == "__main__":
    start_gui()
