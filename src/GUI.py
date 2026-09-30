import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import shutil
import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from load_setup_data import load_config
from tkinter import ttk


# Function to save the configuration without deleting comments or adding blank lines

def save_config(config):
    with open('SETUP.txt', 'r') as file:
        lines = file.readlines()

    with open('SETUP.txt', 'w') as file:
        for line in lines:
            line_stripped = line.strip()
            if line_stripped and not line_stripped.startswith('#'):  # If not a comment
                key = line_stripped.split(': ')[0]  # Get the key (e.g., 'deviceName')
                if key in config:
                    value = config[key]
                    if key == 'debug':
                        value = 'true' if value else 'false'
                    # Keep the original comment, without adding extra spaces
                    if '#' in line:
                        file.write(f"{key}: {value} {line[line.index('#'):]}")  # Keep the comment
                    else:
                        file.write(f"{key}: {value}\n")
                else:
                    file.write(line)  # Leave the line untouched if the key is not a known one
            else:
                file.write(line)  # Write comments and blank lines unchanged


class SplashScreen:
    def __init__(self):
        self.splash = tk.Toplevel()
        self.splash.overrideredirect(True)
        self.splash.configure(bg="white")
        self.splash.geometry("400x120+500+300")
        self.splash.lift()  # Bring to the front
        self.splash.attributes("-topmost", True)  # Always on top

        label = tk.Label(self.splash, text="Loading GUI...", font=("Helvetica", 14), bg="white")
        label.pack(pady=10)

        self.progress = ttk.Progressbar(self.splash, mode='indeterminate', length=300)
        self.progress.pack(pady=10)
        self.progress.start()

        # Force an immediate render
        self.splash.update()

    def close(self):
        self.progress.stop()
        self.splash.destroy()


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event):
        # Create the tooltip window
        x, y, _, _ = self.widget.bbox("insert")  # Get the position of the widget
        x += self.widget.winfo_rootx() + 20  # Shift the tooltip slightly to the right
        y += self.widget.winfo_rooty() + 20  # Shift the tooltip slightly down

        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)  # No border
        self.tooltip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tooltip, text=self.text, background="White", relief="solid", borderwidth=1)
        label.pack()

    def hide_tooltip(self, event):
        # Close the tooltip window
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None



class AcquisitionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Data Acquisition Control Panel")
        self.root.state('zoomed')
        self.auto_update = False  # Auto-refresh flag
        self.main_process = None  # Holds the main.py process
        self.acquisition_running = False
        

        # Back up the SETUP.txt file
        self.backup_setup_file()

        # Load the current configuration from SETUP.txt
        self.config = load_config()

        # Groups used to lay out the sections of the file
        self.sections = {
            "CAPTURE SETUP": ["total_capture_time", "restart_time", "debug"],
            "DAQ SETUP": [
                "deviceName", "original_rate", "buffer_size", "decimation_factor",
                "daq_num_modules", "daq_ch_per_module", "unused_ch"
            ],
            "SENSOR SETUP": ["min_val", "max_val", "sensitivity"],
            "BUFFER DATABASE SETUP (SQL)": ["db_path","sqlite_name"],
            "BACKUP DATABASE SETUP (MongoDB)": ["backup_time", "db_host", "db_port", "db_backup_name"]
        }

        # Per-parameter explanations
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
            "unused_ch": "Unused channels. Use NaN for all sensors. Numbers separated by commas (e.g., 20, 22), where ij: i -> module number; j -> channel number.",
            "debug": "Enable debug mode (True/False).",
            "db_host": "MongoDB host.",
            "db_port": "MongoDB port.",
            "db_path": "SQLite database path.",
            "sqlite_name": "SQLite database name. Change the name if you want to save it in a new database. Use 'accelerations' by default.",
            "db_backup_name": "Name of the database for historical storage.",
            "backup_time": "Time in seconds to back up the buffer to the raw database.",
            "restart_time": "Example: '10s' every ten seconds, '1h' for an hour, '1d' for a day."
        }

        self.units = {
            "total_capture_time": "s",
            "restart_time": " ",
            "original_rate": "Hz",
            "buffer_size": "samples",
            "decimation_factor": "",
            "frequency_rate": "Hz",
            "min_val": "m/s²",
            "max_val": "m/s²",
            "sensitivity": "V/g",
            "backup_time": "s",
            "db_port": "",
        }

        self.locked_fields = {
            key: True for key in [
                "restart_time", "debug", "original_rate", "buffer_size","decimation_factor","backup_time","unused_ch",
                "db_path", "sqlite_name", "db_host", "db_port", "db_backup_name"
            ]
        }
        
        # Entry widgets for the parameters
        self.entries = {}

        # Tracks whether the data was modified
        self.is_updated = False

        # Holds the dynamic sensor checkboxes
        self.sensor_selection = {}  


        # Build the main panel, with a scrollbar
        self.create_scrollable_panel()

        # Output console
        self.console_output = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, width=200, height=15)
        self.console_output.pack(pady=10)
        self.update_console(
'''INSTRUCTIONS:
- Modify the default values if necessary and press 'Save Changes' to update the configuration.
- Press the 'Run Acquisition' button to start the data capture process.
- Press the 'Stop Acquisition' button to stop the acquisition at any time.
- To update the list of available sensors from the database, press 'Find Sensors'.
- To enable automatic updates of the plot every 2 seconds, check the 'Auto-update' box.
- To visualize frequency-domain data, press 'Check Data' to open the Check GUI with PSD and SVD plots.
- If you want to perform non-continuous captures, set the 'backup_time' to 0.
- Before starting a new acquisition, change the database name if you want to store the data in a new file.
- The only parameter that accepts time units is 'restart_time'; Use 's' for seconds (e.g., 10s), use 'h' for hours (e.g., 1h), use 'd' for days (e.g., 1d). This field defines the interval to restart the acquisition. If set to 0s, it won't restart and may accumulate delay.
- Always save your last configuration before closing the program if you wish to preserve it.
'''
        )

        # Plot, below the output console
        self.create_plot_panel()

        # Control buttons
        self.create_control_buttons()

        # Handle the window-close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Check whether the database exists
        db_path = self.config.get("sqlite_db_path", "")
        if not db_path or not os.path.exists(db_path):
            self.update_console("Database not found at the specified path. Some functions will be disabled.")


        
    def backup_setup_file(self):
        """Creates a backup of the SETUP.txt file"""
        try:
            shutil.copyfile('SETUP.txt', 'setupbak.txt')
            # print("Backup of SETUP.txt created.")
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
            # print("Backup deleted.")
        except Exception as e:
            print(f"Error deleting the backup: {e}")

    def create_scrollable_panel(self):
        """Creates a scrollable panel for configurations with adaptive height."""

        container = tk.Frame(self.root)
        container.pack(side="left", fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(-1 * (event.delta // 120), "units"))

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.create_setup_panel(self.scrollable_frame)


    def create_setup_panel(self, parent):
        """Creates the configuration panel content with proper alignment."""
        for section, keys in self.sections.items():
            # Section title label, centred
            section_label = tk.Label(parent, text=section, font=("Helvetica", 9, "bold"))
            section_label.pack(pady=5)

            # Frame holding the rows of the section
            section_frame = tk.Frame(parent)
            section_frame.pack(pady=5, fill=tk.X)

            row_offset = 0  # Tracks the extra rows

            for row, key in enumerate(keys):
                value = self.config.get(key, "")

                # Label
                unit = self.units.get(key, "")
                label_text = f"{key} ({unit})" if unit else key
                variable_label = tk.Label(section_frame, text=label_text, anchor="w", width=25)
                variable_label.grid(row=row + row_offset, column=0, padx=10, pady=5, sticky="w")

                # Entry
                entry = tk.Entry(section_frame, width=20)
                entry.insert(0, str(value))

                # Disable it if the field is in the locked list
                if key in self.locked_fields and self.locked_fields[key]:
                    entry.config(state='readonly')

                entry.grid(row=row + row_offset, column=1, padx=10, pady=5, sticky="w")
                self.entries[key] = entry


                # Tooltip
                description_text = self.explanations.get(key, "No description available")
                ToolTip(variable_label, description_text)

                # Lock button, where it applies
                if key in self.locked_fields:
                    lock_button = tk.Button(
                        section_frame,
                        text="🔒" if self.locked_fields[key] else "🔓",
                        width=2,
                        command=lambda k=key, e=entry, b=None: self.toggle_lock(k, e, b)
                    )
                    lock_button.config(command=lambda k=key, e=entry, b=lock_button: self.toggle_lock(k, e, b))
                    lock_button.grid(row=row + row_offset, column=2, padx=5)

                # For decimation_factor, add an extra frequency field underneath
                if key == "decimation_factor":
                    row_offset += 1  # Skip a row for the new field

                    freq_label = tk.Label(section_frame, text="frequency_rate", anchor="w", width=20)
                    freq_label.grid(row=row + row_offset, column=0, padx=10, pady=5, sticky="w")
                    ToolTip(freq_label, "Select desired sampling frequency in Hz. It will automatically set the appropriate decimation factor.")

                    freq_var = tk.StringVar()
                    freq_combo = ttk.Combobox(section_frame, textvariable=freq_var, state="readonly", width=18)
                    freq_combo['values'] = ["10 Hz", "20 Hz", "50 Hz", "75 Hz", "100 Hz", "150 Hz", "200 Hz", "250 Hz", "300 Hz", "400 Hz"]
                    freq_combo.grid(row=row + row_offset, column=1, padx=10, pady=5, sticky="w")

                    # Update the decimation factor from the frequency
                    def on_freq_selected(event, entry=entry, freq_var=freq_var):
                        try:
                            original_rate = int(self.entries["original_rate"].get())
                            freq = float(freq_var.get().split()[0])
                            decimation = round(original_rate / freq)
                            entry.config(state='normal')
                            entry.delete(0, tk.END)
                            entry.insert(0, str(decimation))
                            if self.locked_fields.get("decimation_factor", False):
                                entry.config(state='readonly')
                        except Exception as e:
                            print(f"Error updating decimation from frequency: {e}")

                    # Update the frequency from the decimation factor
                    def on_decimation_changed(event=None, entry=entry, freq_var=freq_var):
                        try:
                            original_rate = int(self.entries["original_rate"].get())
                            decimation = int(entry.get())
                            freq = round(original_rate / decimation, 2)
                            freq_var.set(f"{freq} Hz")
                        except Exception:
                            pass

                    freq_combo.bind("<<ComboboxSelected>>", on_freq_selected)
                    entry.bind("<KeyRelease>", on_decimation_changed)
                    on_decimation_changed()

        update_section_button = tk.Button(parent, text="Save Changes", command=self.update_config)
        update_section_button.pack(pady=(10, 15))

    
    def toggle_lock(self, key, entry_widget, button_widget):
        is_locked = self.locked_fields[key]
        if is_locked:
            entry_widget.config(state='normal')
            button_widget.config(text="🔓")
        else:
            entry_widget.config(state='readonly')
            button_widget.config(text="🔒")
        self.locked_fields[key] = not is_locked

            

    def create_plot_panel(self):
        """Creates a panel to display the plot and dynamic checkboxes."""
        plot_frame = tk.Frame(self.root)
        plot_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # Sub-frame for the buttons and the auto-refresh checkbox
        button_frame = tk.Frame(plot_frame)
        button_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        # Auto-refresh checkbox
        self.auto_update_var = tk.IntVar()
        tk.Checkbutton(
            button_frame, text="Auto-update", variable=self.auto_update_var, command=self.toggle_auto_update
        ).pack(side=tk.LEFT, padx=5)

        # Button that refreshes the plot manually
        tk.Button(button_frame, text="Plot Once", command=self.update_plot).pack(side=tk.LEFT, padx=5)

        # Button that queries the database again
        tk.Button(button_frame, text="Find Sensors", command=self.update_sensor_checkboxes).pack(side=tk.LEFT, padx=5)

        # Box showing the time lag
        self.time_lag_label = tk.Label(button_frame, text="Time Lag: 0.00s", width=20, anchor="w", relief=tk.SUNKEN)
        self.time_lag_label.pack(side=tk.LEFT, padx=5)

        # Build the initial plot
        self.figure = plt.Figure(figsize=(10, 2), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title('Last 20 seconds of recorded data')
        self.ax.set_xlabel('Time UTC+0')
        self.ax.set_ylabel('Acceleration (m/s²)')
        self.ax.grid(True)

        # Container for the plot
        graph_frame = tk.Frame(plot_frame)
        graph_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = FigureCanvasTkAgg(self.figure, master=graph_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=(0, 0))

        # Panel holding the dynamic sensor checkboxes
        self.checkbox_frame = tk.Frame(plot_frame)
        self.checkbox_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        # Build the checkboxes from the sensors that were detected
        self.update_sensor_checkboxes()

    def update_sensor_checkboxes(self):
        """Updates the checkboxes to reflect the sensors detected in the database."""
        # Remember the previous state of each sensor
        previous_states = {sensor: var.get() for sensor, var in self.sensor_selection.items()}

        # Read the database path from the configuration
        db_path = self.config.get("sqlite_db_path", "")
        if not db_path or not os.path.exists(db_path):
            self.update_console("Error: Database not found at the specified path.")
            self.disable_checkboxes()
            return

        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")

                # Check that the required tables exist
                query_tables = "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sensors', 'accelerations', 'timestamps')"
                existing_tables = [row[0] for row in conn.execute(query_tables).fetchall()]
                required_tables = {'sensors', 'accelerations', 'timestamps'}

                if not required_tables.issubset(set(existing_tables)):
                    self.update_console("Error: The database does not contain the necessary tables.")
                    self.disable_checkboxes()
                    return

                # Get the sensors seen in the last 20 seconds
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

            # Check whether the number of sensors changed
            if len(sensor_numbers) == len(self.sensor_selection) and all(sensor in self.sensor_selection for sensor in sensor_numbers):
                # Nothing changed, so there is no need to refresh
                return

            # Clear the dictionary and drop the widgets when something changed
            self.sensor_selection.clear()
            for widget in self.checkbox_frame.winfo_children():
                widget.destroy()

            # Lay the checkboxes out by column and row
            for sensor in sensor_numbers:
                # Column and row follow the sensor numbering
                col = int(str(sensor)[0])  # First digit gives the column
                row = int(str(sensor)[1])  # Second digit gives the row

                # Restore the previous state if there is one, otherwise default to True
                state = previous_states.get(sensor, True)
                var = tk.BooleanVar(value=state)
                chk = tk.Checkbutton(self.checkbox_frame, text=f"Sensor {sensor}", variable=var)
                chk.grid(row=row, column=col, padx=5, pady=5, sticky="w")
                self.sensor_selection[sensor] = var

        except Exception as e:
            self.update_console(f"Error loading data from the database: {e}")
            self.disable_checkboxes()

    def disable_checkboxes(self):
        """Disables the checkboxes and shows a message in the interface."""
        self.sensor_selection.clear()
        for widget in self.checkbox_frame.winfo_children():
            widget.destroy()
        tk.Label(self.checkbox_frame, text="No Sensors currently available").grid(row=0, column=0)

    def load_last_20_seconds(self):
        """
        Loads the last 20 seconds of recorded data from SQLite.
        Only the selected sensors are loaded.
        """
        db_path = self.config.get("sqlite_db_path", "")
        if not db_path or not os.path.exists(db_path):
            self.update_console("No database found at the specified path. Plot not updated.")
            return pd.DataFrame()

        # Get the selected sensors
        selected_sensors = [sensor for sensor, var in self.sensor_selection.items() if var.get()]

        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                # Get the most recent timestamp
                query_max = "SELECT MAX(timestamp) as max_time FROM timestamps"
                max_time = pd.read_sql_query(query_max, conn)['max_time'].iloc[0]
                if max_time is None:
                    return pd.DataFrame()  # No data, so return an empty frame
                end_timestamp = max_time
                start_timestamp = end_timestamp - 20  # Last 20 seconds

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
            self.update_console(f"Error loading data from the database: {e}")
            return pd.DataFrame()

        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df


    def update_plot(self):
        """
        Updates the plot with the last 20 seconds of recorded data.
        """
        # Check that a database exists before refreshing the plot
        db_path = self.config.get("sqlite_db_path", "")
        if not db_path or not os.path.exists(db_path):
            self.update_console("No database found at the specified path. Plot not updated.")
            self.auto_update_var.set(0)  # Turn the auto-refresh off
            return

        df = self.load_last_20_seconds()
        self.ax.clear()
        self.ax.set_title('Last 20 seconds of recorded data')
        self.ax.set_xlabel('Time UTC+0')
        self.ax.set_ylabel('Acceleration (m/s²)')
        self.ax.grid(True)

        if not df.empty:
            for sensor in df['sensor_number'].unique():
                sensor_data = df[df['sensor_number'] == sensor]
                self.ax.plot(sensor_data['timestamp'], sensor_data['acceleration_value'], label=f"Sensor {sensor}")

            self.ax.legend(loc='upper right')

            # Lag between the last timestamp and the current time
            last_timestamp = df['timestamp'].max()
            last_timestamp = pd.to_datetime(last_timestamp)
            if last_timestamp.tzinfo is None:
                last_timestamp = last_timestamp.tz_localize('UTC')

            current_time = pd.Timestamp.now(tz='UTC')

            time_lag = (current_time - last_timestamp).total_seconds()

            # Refresh the lag box
            self.time_lag_label.config(text=f"Time Lag: {time_lag:.2f}s")

        else:
            # No data, so report a lag of 0
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
        if self.acquisition_running:
            self.update_console("⚠️ Acquisition is already running.")
            messagebox.showinfo("Already Running", "An acquisition process is already running.")
            return

        # Save the updated configuration
        self.update_config()

        # Run main.py in a new console window
        self.update_console("Running main.py in a new console window...")
        if os.name == 'nt':  # Windows
            subprocess.Popen(['start', 'cmd', '/c', 'python', 'src/main.py'], shell=True)
        else:  # Linux, macOS
            subprocess.Popen(['x-terminal-emulator', '-e', 'python src/main.py'])

        self.acquisition_running = True
        self.update_console("Acquisition running. Press 'Stop Acquisition' button to stop the acquisition process.")

        # Disable the Run Acquisition button while the process is alive
        self.execute_button.config(state="disabled")


    def update_console(self, message):
        self.console_output.config(state=tk.NORMAL)  # Allow writing
        self.console_output.insert(tk.END, message + "\n")
        self.console_output.see(tk.END)  # Scroll to the end automatically
        self.console_output.config(state=tk.DISABLED)  # Block writing

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
            # Convert the numeric types where needed
            if key in ["total_capture_time", "original_rate", "buffer_size", "decimation_factor", "db_port", "backup_time"]:
                value = int(value)
            elif key in ["min_val", "max_val", "sensitivity"]:
                value = float(value)
            elif key == "debug":
                value = value.lower() == 'true'  # Convert to a boolean
            self.config[key] = value

        # Flag the data as modified
        self.is_updated = True

        # Write the new values into SETUP.txt
        save_config(self.config)
        self.update_console("Configuration data saved in SETUP.txt, Stop any acquisition before running a new one with new parameters.")

    def open_check_gui(self):
        script_path = os.path.join("src", "GUI_check.py")
        self.update_console("Running GUI_Check in a new window...")
        python_executable = sys.executable  # reuse the interpreter running this GUI
        subprocess.Popen([python_executable, script_path])

    def stop_acquisition(self):
        if not self.acquisition_running:
            messagebox.showinfo("Not Running", "There is no acquisition process running.")
            return

        try:
            with open("STOP.txt", "w") as f:
                f.write("stop")
            self.acquisition_running = False  # Only mark it as stopped once the file was written
            self.execute_button.config(state="normal")  # <-- AQUI
            messagebox.showinfo("Stop", "Stop signal sent. If the process doesn't close automatically, press ENTER in the acquisition window.")
        except Exception as e:
            self.update_console(f"❌ Failed to send stop signal: {e}")




    def create_control_buttons(self):
        """Creates the control buttons."""
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        self.execute_button = tk.Button(button_frame, text="Run Acquisition", command=self.execute_main)
        self.execute_button.grid(row=0, column=0, padx=10)

        stop_button = tk.Button(button_frame, text="Stop Acquisition", command=self.stop_acquisition)
        stop_button.grid(row=0, column=3, padx=10)

        check_button = tk.Button(button_frame, text="Check Data", command=self.open_check_gui)
        check_button.grid(row=0, column=5, padx=10)

if __name__ == "__main__":
    import time

    root = tk.Tk()
    root.withdraw()  # Hide the main window

    splash = SplashScreen()  # Show the splash screen straight away

    def load_gui():
        app = AcquisitionGUI(root)  # Full load happens here
        splash.close()
        root.deiconify()  # Show the main GUI

    # Load after 100 ms, so the splash screen has time to render
    root.after(100, load_gui)
    root.mainloop()
