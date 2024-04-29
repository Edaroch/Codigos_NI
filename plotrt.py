

import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from tkinter import Tk, Label, Button, Entry, Frame, Checkbutton, IntVar, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime
import matplotlib.dates as mdates

db_path = "Accelerations/aceleraciones.db"

def load_data_from_database(db_path, end_timestamp, seconds_back):
    conn = sqlite3.connect(db_path)
    query = "SELECT max(time) as max_time FROM acceleration_data"
    times = pd.read_sql_query(query, conn)
    max_time = times['max_time'].iat[0]
    
    if end_timestamp == 0:
        end_timestamp = max_time
    start_timestamp = end_timestamp - seconds_back

    query = "SELECT * FROM acceleration_data WHERE time BETWEEN ? AND ? ORDER BY time"
    df = pd.read_sql_query(query, conn, params=(start_timestamp, end_timestamp))
    conn.close()
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def initialize_plot(frame):
    figure = plt.Figure(figsize=(10, 6), dpi=100)
    ax = figure.add_subplot(111)
    ax.set_title('Acceleration Data Over Time')
    ax.set_xlabel('Time')
    ax.set_ylabel('Acceleration (m/s^2)')
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=20))
    canvas = FigureCanvasTkAgg(figure, master=frame)
    canvas.draw()
    canvas.get_tk_widget().pack(side='top', fill='both', expand=1)
    return ax, canvas

def update_plot(df, ax, canvas, sensor_checks):
    ax.clear()
    if df.empty:
        ax.text(0.5, 0.5, 'No data available in the specified range', horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
    else:
        for i, sensor in enumerate(['sensor1', 'sensor2', 'sensor3', 'sensor4', 'sensor5', 'sensor6'], start=1):
            if sensor_checks[i-1].get():
                ax.plot(df['time'], df[sensor], label=f'Sensor {i}')
        ax.legend(loc='upper right')
        for label in ax.get_xticklabels():
            label.set_rotation(45)
    ax.grid(True)
    canvas.draw()

def plot_button_clicked(frame, ax, canvas, sensor_checks):
    end_ts = get_timestamp_from_entry(end_entry)
    seconds_back = int(seconds_back_entry.get() if seconds_back_entry.get() else 0)
    df = load_data_from_database(db_path, end_ts, seconds_back)
    update_plot(df, ax, canvas, sensor_checks)

def auto_refresh_toggle(frame, ax, canvas, sensor_checks):
    if auto_refresh_var.get():
        plot_button_clicked(frame, ax, canvas, sensor_checks)
        root.after(int(refresh_rate_entry.get() if refresh_rate_entry.get() else 1000), lambda: auto_refresh_toggle(frame, ax, canvas, sensor_checks))

def get_timestamp_from_entry(entry):
    try:
        return int(datetime.strptime(entry.get(), "%Y-%m-%d %H:%M:%S").timestamp())
    except ValueError:
        return 0

def on_closing():
    if messagebox.askokcancel("Quit", "Do you want to close the application?"):
        root.destroy()

root = Tk()
root.title("Data Visualization")
controls_frame = Frame(root)
controls_frame.pack(side='top', fill='x')

Label(controls_frame, text="End datetime (YYYY-MM-DD HH:MM:SS) or 0 for the most recent data").pack(side='left')
end_entry = Entry(controls_frame)
end_entry.pack(side='left')
end_entry.insert(0, "0")

Label(controls_frame, text="Seconds back from end time").pack(side='left')
seconds_back_entry = Entry(controls_frame)
seconds_back_entry.pack(side='left')
seconds_back_entry.insert(0, "30")

sensor_checks = [IntVar(value=1) for _ in range(6)]
for i in range(6):
    Checkbutton(controls_frame, text=f'Sensor {i+1}', variable=sensor_checks[i]).pack(side='left')

auto_refresh_var = IntVar()
Checkbutton(controls_frame, text="Auto-refresh", variable=auto_refresh_var, command=lambda: auto_refresh_toggle(plot_frame, ax, canvas, sensor_checks)).pack(side='left')

Label(controls_frame, text="Refresh rate (ms):").pack(side='left')
refresh_rate_entry = Entry(controls_frame)
refresh_rate_entry.pack(side='left')
refresh_rate_entry.insert(0, "1000")

Button(controls_frame, text="Plot Data", command=lambda: plot_button_clicked(plot_frame, ax, canvas, sensor_checks)).pack(side='left')

plot_frame = Frame(root)
plot_frame.pack(fill='both', expand=True)

ax, canvas = initialize_plot(plot_frame)

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()

