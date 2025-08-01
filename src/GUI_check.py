import tkinter as tk
from tkinter import ttk
import threading
import time
import json
import os
from utils import get_last_seconds_from_sqlite, get_PSD_SVD_from_file
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import numpy as np
import queue


class CheckGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Data Checking GUI")

        self.plot_queue = queue.Queue()
        self.root.after(100, self.process_plot_queue)

        # State
        self.auto_var = tk.BooleanVar()
        self.running = False
        self.data = None
        self.channel_vars = {}
        self.mosaic_canvas = None
        self.mosaic_fig = None
        self.annotations = []
        self.log_scale_var = tk.BooleanVar(value=False)
        self.mosaic_ready = False
        self.plotting_in_progress = False


        # Layout
        top_frame = ttk.Frame(root)
        top_frame.pack(padx=10, pady=5, fill="x")

        self.auto_check = ttk.Checkbutton(top_frame, text="Auto-update", variable=self.auto_var,
                                          command=self.toggle_auto)
        self.auto_check.grid(row=0, column=0, padx=5)

        self.check_button = ttk.Button(top_frame, text="Plot Once", command=self.check_data)
        self.check_button.grid(row=0, column=1, padx=5)






        # Frequency Range Controls
        self.freq_min_var = tk.DoubleVar(value=0.0)
        min_freq_label = ttk.Label(top_frame, text="Min Frequency (Hz):")
        min_freq_label.grid(row=0, column=2, padx=(10, 5))

        self.freq_min_entry = ttk.Entry(top_frame, textvariable=self.freq_min_var, width=6)
        self.freq_min_entry.grid(row=0, column=3, padx=5)

        self.freq_max_var = tk.DoubleVar(value=50.0)
        freq_label = ttk.Label(top_frame, text="Max Frequency (Hz):")
        freq_label.grid(row=0, column=4, padx=(20, 5))

        self.freq_entry = ttk.Entry(top_frame, textvariable=self.freq_max_var, width=6)
        self.freq_entry.grid(row=0, column=5, padx=5)

        self.freq_refresh_btn = ttk.Button(top_frame, text="Refresh", command=self.update_all_plots)
        self.freq_refresh_btn.grid(row=0, column=6, padx=5)

 

        self.log_check = ttk.Checkbutton(top_frame, text="Log Scale", variable=self.log_scale_var,
                            command=self.update_all_plots)
        self.log_check.grid(row=0, column=7, padx=5)


        # PSD buttons
        graph_frame = ttk.LabelFrame(root, text="Show Graphs")
        graph_frame.pack(padx=10, pady=5, fill="x")

        self.psd_all_btn = ttk.Button(graph_frame, text="Show PSDs Overlay", command=self.plot_psd_overlay)
        self.psd_all_btn.pack(side="left", padx=5)

        self.psd_mosaic_btn = ttk.Button(graph_frame, text="Show PSDs Mosaic", command=self.plot_psd_mosaic)
        self.psd_mosaic_btn.pack(side="left", padx=5)

        self.svd_btn = ttk.Button(graph_frame, text="Show SVD", command=self.plot_singular_values)
        self.svd_btn.pack(side="left", padx=5)

        # # SVD button
        # svd_frame = ttk.LabelFrame(root, text="Singular Values")
        # svd_frame.pack(padx=10, pady=5, fill="x")

        # self.svd_btn = ttk.Button(svd_frame, text="Show SVD", command=self.plot_singular_values)
        # self.svd_btn.pack(padx=5)

        # Sensor filter checkboxes
        self.checkbox_frame = ttk.LabelFrame(root, text="Sensor Selection (Overlay Only)")

        # Plot area

        self.plot_frame = ttk.Frame(root)
        self.plot_frame.pack(fill="both", expand=True)

        # Persistent canvas for overlay/svd
        self.fig = plt.Figure(figsize=(8, 4))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)
        # self.canvas.mpl_connect("motion_notify_event", self.on_hover_main)
        # self.canvas._cid = self.canvas.mpl_connect("motion_notify_event", self.on_hover_main)
        # self.annotation = self.ax.annotate(
        #     "", xy=(0, 0), xytext=(10, 10), textcoords="offset points",
        #     bbox=dict(boxstyle="round", fc="w"),
        #     arrowprops=dict(arrowstyle="->"))
        # self.annotation.set_visible(False)

        # self.vline = self.ax.axvline(color='gray', linestyle='--', linewidth=0.8)
        # self.vline.set_visible(False)

        self.active_view = "overlay"

    def prevent_if_plotting(func):
        def wrapper(self, *args, **kwargs):
            if self.plotting_in_progress:
                print(f"⏳ Ignored: {func.__name__} is waiting for current plot.")
                return
            self.plotting_in_progress = True
            try:
                return func(self, *args, **kwargs)
            finally:
                self.plotting_in_progress = False
        return wrapper

    def check_data(self):
        get_last_seconds_from_sqlite(seconds=30)
        get_PSD_SVD_from_file()
        self.load_data()
        if self.auto_var.get():
            self.plot_psd_overlay()

    def toggle_auto(self):
        if self.auto_var.get():
            self.running = True
            threading.Thread(target=self.auto_loop, daemon=True).start()
        else:
            self.running = False

    def auto_loop(self):
        while self.running:
            get_last_seconds_from_sqlite(seconds=30)
            get_PSD_SVD_from_file()
            self.plot_queue.put("update")
            time.sleep(5)

    def process_plot_queue(self):
        try:
            while not self.plot_queue.empty():
                task = self.plot_queue.get_nowait()
                if task == "update":
                    self.root.after(0, self.safe_update_all)
        except queue.Empty:
            pass
        finally:
            # vuelve a revisar en 100 ms
            self.root.after(100, self.process_plot_queue)

    def sync_gui_update_if_overlay(self):
        self.load_data()
        self.update_all_plots()

    def clear_plot_queue(self):
        with self.plot_queue.mutex:
            self.plot_queue.queue.clear()

    def safe_update_all(self):
        self.load_data()
        self.update_all_plots()



    def sync_gui_update(self):
        self.load_data()
        self.plot_psd_overlay()

    def load_data(self):
        if not os.path.exists("psd_results.json"):
            print("⚠️ psd_results.json not found.")
            return
        with open("psd_results.json", "r") as f:
            self.data = json.load(f)

        # Solo prepara info, luego actualiza widgets desde hilo principal
        self.root.after(0, self.update_sensor_checkboxes)

    def update_sensor_checkboxes(self):
        previous_states = {
            k: v.get() for k, v in self.channel_vars.items()
        }

        self.channel_vars.clear()
        for widget in self.checkbox_frame.winfo_children():
            widget.destroy()

        for sensor_label in self.data.get("psd", {}):
            var = tk.BooleanVar(value=previous_states.get(sensor_label, True))
            self.channel_vars[sensor_label] = var
            chk = ttk.Checkbutton(self.checkbox_frame, text=sensor_label, variable=var,
                                command=self.plot_psd_overlay)
            chk.pack(side="left", padx=5)

        # 🔁 Redibujar overlay si estamos en esa vista
        if self.active_view == "overlay":
            self.plot_psd_overlay()

    def update_all_plots(self):
        if not self.data:
            return

        if self.active_view == "overlay":
            self.plot_psd_overlay()
        elif self.active_view == "mosaic":
            self.plot_psd_mosaic()
        elif self.active_view == "svd":
            self.plot_singular_values()


    @prevent_if_plotting
    def plot_psd_overlay(self):
        self.clear_plot_queue()
        if not self.data:
            self.load_data()
            if not self.data:
                return
        self.active_view = "overlay"

        self.checkbox_frame.pack(padx=10, pady=5, fill="x")
        self.canvas_widget.pack(fill="both", expand=True)
        if self.mosaic_canvas:
            self.mosaic_canvas.get_tk_widget().pack_forget()

        self.ax.cla()

        f = np.array(self.data["frequencies"])
        fmin = self.freq_min_var.get()
        fmax = self.freq_max_var.get()
        has_data = False
        ymax = 0

        for sensor_label, values in self.data["psd"].items():
            if self.channel_vars.get(sensor_label, tk.BooleanVar()).get():
                f_arr = np.array(f)
                v_arr = np.array(values)
                mask = (f_arr >= fmin) & (f_arr <= fmax)
                if not np.any(mask):
                    continue
                self.ax.plot(f_arr[mask], v_arr[mask], label=sensor_label)
                local_max = np.max(v_arr[mask])
                if local_max > ymax:
                    ymax = local_max
                has_data = True

        if has_data:
            self.ax.set_title("Selected PSDs Overlay")
            self.ax.set_xlabel("Frequency [Hz]")
            self.ax.set_xlim([fmin, fmax])
            self.ax.set_ylim(bottom=0, top=1.05 * ymax)

            if self.log_scale_var.get():
                self.ax.set_yscale("log")
                self.ax.set_ylabel("PSD [dB]")
            else:
                self.ax.set_yscale("linear")
                self.ax.set_ylabel("PSD [(m/s²)²/Hz]")

            self.ax.grid(True)
            self.ax.legend()
        else:
            self.ax.set_title("No sensors selected")

        self.canvas.draw_idle()



    @prevent_if_plotting
    def plot_psd_mosaic(self):
        self.clear_plot_queue()
        self.mosaic_ready = False
        self.load_data()
        if not self.data:
            return

        self.active_view = "mosaic"

        self.canvas_widget.pack_forget()
        self.checkbox_frame.pack_forget()

        if self.mosaic_canvas:
            self.root.after(0, lambda: self.mosaic_canvas.get_tk_widget().destroy())
            self.mosaic_canvas = None

        f = np.array(self.data["frequencies"])
        psd = self.data["psd"]
        num = len(psd)

        self.mosaic_fig, axs = plt.subplots(num, 1, figsize=(8, 2.5 * num), sharex=True)
        if num == 1:
            axs = [axs]

        try:
            fmin = self.freq_min_var.get()
            fmax = self.freq_max_var.get()
        except tk.TclError:
            fmin, fmax = 0, np.max(f)

        self.annotations = []
        for i, (label, values) in enumerate(psd.items()):
            f_arr = np.array(f)
            v_arr = np.array(values)
            mask = (f_arr >= fmin) & (f_arr <= fmax)
            if not np.any(mask):
                continue
            axs[i].plot(f_arr[mask], v_arr[mask], label=label)
            axs[i].set_xlim([fmin, fmax])

            local_max = np.max(v_arr[mask]) if np.any(mask) else 1.0
            axs[i].set_ylim(bottom=0, top=1.05 * local_max)

            if self.log_scale_var.get():
                axs[i].set_yscale("log")
                axs[i].set_ylabel(f"{label}\n[dB]")
            else:
                axs[i].set_yscale("linear")
                axs[i].set_ylabel(f"{label}\n[(m/s²)²/Hz]")

            axs[i].grid(True)

            ann = axs[i].annotate("", xy=(0, 0), xytext=(10, 10), textcoords="offset points",
                                bbox=dict(boxstyle="round", fc="w"),
                                arrowprops=dict(arrowstyle="->"))
            ann.set_visible(False)
            self.annotations.append(ann)

        axs[-1].set_xlabel("Frequency [Hz]")
        self.mosaic_fig.suptitle("PSD Mosaic")
        self.mosaic_fig.tight_layout()

        self.mosaic_canvas = FigureCanvasTkAgg(self.mosaic_fig, master=self.plot_frame)
        self.mosaic_canvas.get_tk_widget().pack(fill="both", expand=True)
        self.mosaic_canvas.draw()
        self.mosaic_canvas.mpl_connect("motion_notify_event", self.on_hover_mosaic)
        plt.close(self.mosaic_fig)
        self.mosaic_ready = True


    @prevent_if_plotting
    def plot_singular_values(self):
        self.clear_plot_queue()
        self.load_data()
        if not self.data:
            return

        self.active_view = "svd"

        self.checkbox_frame.pack_forget()
        self.canvas_widget.pack(fill="both", expand=True)
        if self.mosaic_canvas:
            self.mosaic_canvas.get_tk_widget().pack_forget()

        self.ax.cla()

        f = np.array(self.data["frequencies"])
        sv = self.data["singular_values"]

        try:
            fmin = self.freq_min_var.get()
            fmax = self.freq_max_var.get()
        except tk.TclError:
            fmin, fmax = 0, np.max(f)

        has_data = False
        y_max = 0

        for label, values in sv.items():
            f_arr = np.array(f)
            v_arr = np.array(values)
            mask = (f_arr >= fmin) & (f_arr <= fmax)
            if not np.any(mask):
                continue
            self.ax.plot(f_arr[mask], v_arr[mask], label=label)
            local_max = np.max(v_arr[mask])
            y_max = max(y_max, local_max)
            has_data = True

        if has_data:
            self.ax.set_title("Singular Value Decomposition")
            self.ax.set_xlabel("Frequency [Hz]")
            self.ax.set_xlim([fmin, fmax])

            if self.log_scale_var.get():
                self.ax.set_yscale("log")
                self.ax.set_ylabel("Singular Value [dB]")
            else:
                self.ax.set_yscale("linear")
                self.ax.set_ylabel("Singular Value [Amplitude]")
                self.ax.set_ylim(bottom=0, top=1.05 * y_max)

            self.ax.grid(True)
            self.ax.legend()
        else:
            self.ax.set_title("No singular values to display")

        self.canvas.draw_idle()
        
    def on_hover_mosaic(self, event):
        if not self.mosaic_ready or not self.mosaic_fig or not event.inaxes:
            for ann in self.annotations:
                ann.set_visible(False)
            if self.mosaic_canvas:
                self.mosaic_canvas.draw_idle()
            return

        for i, ax in enumerate(self.mosaic_fig.axes):
            ann = self.annotations[i]
            if event.inaxes == ax and ax.lines:
                line = ax.lines[0]
                xdata = line.get_xdata()
                ydata = line.get_ydata()
                index = np.searchsorted(xdata, event.xdata)
                if 0 <= index < len(xdata):
                    x = xdata[index]
                    y = ydata[index]
                    label = line.get_label()
                    ann.xy = (x, y)
                    ann.set_text(f"{label}\n{float(x):.2f} Hz\n{float(y):.2e}")
                    ann.set_visible(True)
                else:
                    ann.set_visible(False)
            else:
                ann.set_visible(False)

        if self.mosaic_canvas:
            self.mosaic_canvas.draw_idle()

    def on_closing(self):
        self.running = False
        self.plot_queue.queue.clear()
        self.plotting_in_progress = False
        self.root.after(100, self.root.destroy)


if __name__ == "__main__":
    root = tk.Tk()
    app = CheckGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
