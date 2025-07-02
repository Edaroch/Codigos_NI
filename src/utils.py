import os
import numpy as np
import scipy as sp
import pandas as pd
import matplotlib.pyplot as plt
# import warnings
from json import load, dump
from sqlite3 import connect
from typing import Tuple, Optional, List, Dict

from setup_database import initialize_mongodb_client, close_mongodb_client
from load_setup_data import load_config


def get_last_seconds_from_sqlite(seconds: int,
                                 output_file: str = 'last_seconds.json',
                                 export_to_json: bool = True) -> List[Dict]:
    """
    Retrieves the last `seconds` of acceleration records from a local SQLite database
    and saves them in the same JSON format used by the MongoDB version.

    Args:
        seconds (int): Time range in seconds to look back.
        output_file (str): File name to export the results.
        export_to_json (bool): Whether to save the results to a JSON file.

    Returns:
        List[Dict]: A list of records in the same format as the MongoDB export.
    """
    # Load configuration
    config = load_config()
    sqlite_db_path = config['sqlite_db_path']

    if not os.path.exists(sqlite_db_path):
        print(f"❌ SQLite file not found at: {sqlite_db_path}")
        return []

    conn = connect(sqlite_db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA journal_mode=WAL;")

    try:
        # Get the latest timestamp
        cursor.execute("SELECT MAX(timestamp) FROM timestamps")
        max_ts_row = cursor.fetchone()
        if not max_ts_row or max_ts_row[0] is None:
            print("⚠️ No data found in the SQLite database.")
            return []

        max_timestamp = max_ts_row[0]
        from_timestamp = max_timestamp - seconds

        # Query all timestamps within the time range
        cursor.execute("""
            SELECT id, timestamp FROM timestamps 
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        """, (from_timestamp,))
        ts_rows = cursor.fetchall()

        if not ts_rows:
            print("⚠️ No data found within the requested time range.")
            return []

        ts_id_map = {row[0]: row[1] for row in ts_rows}
        ts_ids = tuple(ts_id_map.keys())

        # Get all sensor mappings
        cursor.execute("SELECT id, sensor_number FROM sensors")
        sensor_map = {row[0]: row[1] for row in cursor.fetchall()}

        # Query acceleration data for those timestamps
        placeholders = ",".join(["?"] * len(ts_ids))
        cursor.execute(f"""
            SELECT timestamp_id, sensor_id, acceleration_value 
            FROM accelerations 
            WHERE timestamp_id IN ({placeholders})
        """, ts_ids)

        # Build data grouped by timestamp
        result_dict = {}
        for ts_id, sensor_id, accel in cursor.fetchall():
            ts = ts_id_map[ts_id]
            if ts not in result_dict:
                result_dict[ts] = []
            result_dict[ts].append({
                "sensor_id": str(sensor_map[sensor_id]),
                "acceleration": accel
            })

        # Convert to list of dictionaries sorted by timestamp
        result_list = [
            {"timestamp": ts, "sensor_data": sorted(sensor_list, key=lambda s: int(s["sensor_id"]))}
            for ts, sensor_list in sorted(result_dict.items())
        ]

        if export_to_json:
            with open(output_file, "w") as f:
                dump(result_list, f, indent=4)
            print(f"✅ {len(result_list)} records exported to '{os.path.abspath(output_file)}'")

        return result_list

    finally:
        conn.close()


def get_last_seconds_from_mongodb(seconds: int, 
                          output_file: str = 'last_seconds.json', 
                          export_to_json: bool = True) -> List[Dict]:
    """
    Retrieves the last `seconds` minutes of records from the 'accelerations' collection in MongoDB.
    
    Args:
        seconds (int): Number of minutes to look back from the latest timestamp in the collection.
        output_file (str, optional): Path to the JSON file to save the output. If None, defaults to 'last_{seconds}_minutes.json'.
        export_to_json (bool): Whether to export the retrieved data to a JSON file.
    
    Returns:
        List[dict]: A list of documents matching the time filter.
    """

    # Load configuration parameters from SETUP.txt
    config = load_config()
    host = config['db_host']
    port = int(config['db_port'])
    db_name = config['db_backup_name']
    collection_name = "accelerations"

    # Connect to MongoDB using the setup_database utility
    client = initialize_mongodb_client(config)
    if not client:
        print("❌ Failed to connect to MongoDB.")
        return []

    try:
        db = client[db_name]
        collection = db[collection_name]

        # Find the most recent document to get the maximum timestamp
        most_recent_doc = collection.find_one(sort=[("timestamp", -1)])
        if not most_recent_doc:
            print("⚠️ No data found in the collection.")
            return []

        max_timestamp = most_recent_doc["timestamp"]
        from_timestamp = max_timestamp - (seconds)

        # Query for documents within the time window
        query = {"timestamp": {"$gte": from_timestamp}}
        results = list(collection.find(query))

        # If results are incomplete, show available duration
        if results:
            earliest_timestamp = results[0]["timestamp"]
            duration_available = max_timestamp - earliest_timestamp + 1
            if duration_available < (seconds):
                min_avail = int(duration_available // 60)
                sec_avail = int(duration_available % 60)
                print(f"ℹ️ Only {min_avail} minutes and {sec_avail} seconds of data are available.")
        else:
            print("⚠️ No data found within the requested time range.")
            return []

        # Convert ObjectId to string for JSON serialization
        for result in results:
            result["_id"] = str(result["_id"])

        # Export to JSON if requested
        if export_to_json:
            if output_file is None:
                output_file = f"last_{seconds}_seconds.json"
            temp_file = output_file + ".tmp"
            with open(temp_file, "w") as file:
                dump(results, file, indent=4)
            os.replace(temp_file, output_file)
            print(f"✅ {len(results)} documents exported to '{os.path.abspath(output_file)}'")

        return results

    finally:
        # Ensure the MongoDB client is closed properly
        close_mongodb_client()


def get_PSD_SVD_from_file(file_path: str = "last_seconds.json",
                          window: str = 'hann',
                          pov: float = 0.5,
                          df_target: float = 0.01,
                          plot: bool = False,
                          psd_channels: Optional[List[int]] = None
                          ) -> Optional[Tuple[Tuple[np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray]]]:
    """
    Computes the Power Spectral Density (PSD) matrix and its Singular Value Decomposition (SVD)
    using acceleration data loaded from a MongoDB-exported JSON file.

    Args:
        file_path (str): Path to the JSON file containing sensor data.
        window (str): Type of window to use for spectral analysis (e.g., 'hann').
        pov (float): Overlap percentage between windows (0 to 1).
        df_target (float): Desired frequency resolution in Hz.
        plot (bool): Whether to plot the PSD and singular values.
        psd_channels (Optional[List[int]]): List of sensor IDs (1-based) to plot in PSD graph (e.g., [1, 3, 5]).

    Returns:
        Tuple: ((frequencies, PSD_matrix), (S_values, U1_transposed))
        If no data is found, returns None.
    """
    if not os.path.exists(file_path):
        print("No data available for analysis.")
        return None

    with open(file_path, "r") as file:
        raw_data = load(file)

    # Convert MongoDB data to DataFrame
    timestamps = []
    sensor_map = {}

    for entry in raw_data:
        timestamps.append(entry["timestamp"])
        for s in entry["sensor_data"]:
            sid = f"ch_{s['sensor_id']}"
            if sid not in sensor_map:
                sensor_map[sid] = []
            sensor_map[sid].append(s["acceleration"])

    df = pd.DataFrame(sensor_map)
    df.insert(0, "t", timestamps)
    df = df.sort_values(by="t").reset_index(drop=True)

    t = df["t"].to_numpy()
    if t[-1] == t[0]:
        print("⚠️ Not enough variation in time values to compute sampling rate.")
        return None

    channels = df.drop(columns=["t"]).columns
    sps = len(t) / (t[-1] - t[0])  # Sampling frequency
    L = len(t)
    nxseg = int(sps / df_target) if df_target > 0 else 1

    if nxseg > L:
        df_old = float(df_target)
        nxseg = L
        df_target = sps / nxseg
        # warnings.warn(
        #     f"Desired frequency resolution df={df_old:.2g}Hz is not achievable; "
        #     f"setting df={df_target:.2g}Hz instead.",
        #     UserWarning
        # )

    noverlap = int(pov * nxseg)
    PSD_matr = np.zeros((len(channels), len(channels), int(nxseg // 2 + 1)), dtype=complex)

    # Compute cross PSD
    for i, ch_i in enumerate(channels):
        for j, ch_j in enumerate(channels):
            f, Pxy = sp.signal.csd(df[ch_i], df[ch_j], fs=sps, nperseg=nxseg,
                                   noverlap=noverlap, window=window)
            PSD_matr[i, j, :] = Pxy

    # Compute SVD over frequencies
    S_val = np.zeros_like(PSD_matr.real)
    for i in range(PSD_matr.shape[2]):
        U, S, _ = np.linalg.svd(PSD_matr[:, :, i])
        U1_1 = U.T
        S_val[:, :, i] = np.diag(S)

    # print(f"✅ PSD + SVD computed for {len(channels)} channels.")

    # Save results to JSON for GUI visualization
    export = {
        "frequencies": f.tolist(),
        "psd": {
            f"Sensor {i+1}": PSD_matr[i, i, :].real.tolist()
            for i in range(len(channels))
        },
        "singular_values": {
            f"Mode {i+1}": S_val[i, i, :].tolist()
            for i in range(S_val.shape[0])
        },
        "metadata": {
            "sampling_rate": sps,
            "window": window,
            "df_target": df_target,
            "num_channels": len(channels),
            "points": L
        }
    }

    with open("psd_results.json", "w") as f_out:
        dump(export, f_out, indent=4)

    # print("📁 PSD + SVD results saved to 'psd_results.json'")


    # Plot if requested
    if plot:
        num_channels = len(channels)
        fig, axs = plt.subplots(num_channels, 1, figsize=(10, 2 * num_channels), sharex=True)

        if num_channels == 1:
            axs = [axs]  # Ensure axs is iterable

        for i in range(num_channels):
            axs[i].plot(f, PSD_matr[i, i, :].real, label=f"Sensor {i+1}")
            axs[i].set_ylabel("PSD")
            axs[i].set_title(f"Auto-PSD – Sensor {i+1}")
            axs[i].grid(True)
            axs[i].legend()

        axs[-1].set_xlabel("Frequency [Hz]")
        plt.tight_layout()
        plt.show()



if __name__ == "__main__":
    # get_last_seconds_from_sqlite(seconds=30)
    # get_last_seconds_from_mongodb(seconds=30)
    # get_PSD_SVD_from_file(plot=True)
    pass