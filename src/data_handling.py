from sqlite3 import connect
import time
from pandas import DataFrame
from colorama import Fore, Style
from setup_database import initialize_mongodb_client, close_mongodb_client


def buffer_to_db(persistent_buffer, sqlite_db_path, config, max_retries=5, initial_delay=0.5):
    """
    Inserts data into the SQLite3 database.
    """
    attempt = 0
    delay = initial_delay

    while attempt < max_retries:
        try:
            # Connect to SQLite3
            conn = connect(sqlite_db_path)
            cursor = conn.cursor()

            # Enable WAL
            cursor.execute("PRAGMA journal_mode=WAL;")

            # Build a DataFrame to handle the data
            df = DataFrame(persistent_buffer)

            if config["debug"]:
                print(f"5) Data passing through the database: {len(df)} records per sensor.")

            # Get the unique timestamps and insert them into `timestamps`
            timestamps = df['time'].unique()
            cursor.executemany("INSERT OR IGNORE INTO timestamps (timestamp) VALUES (?)", [(ts,) for ts in timestamps])
            conn.commit()

            # Map each timestamp to its id
            timestamp_ids = {
                ts: cursor.execute("SELECT id FROM timestamps WHERE timestamp = ?", (ts,)).fetchone()[0]
                for ts in timestamps
            }

            # Map each sensor to its id
            sensor_ids = {
                col: cursor.execute("SELECT id FROM sensors WHERE sensor_number = ?", (col,)).fetchone()[0]
                for col in df.columns if col != 'time'
            }

            # Prepare the rows to insert into `accelerations`
            sensor_data = []
            for index, row in df.iterrows():
                timestamp = row['time']
                timestamp_id = timestamp_ids[timestamp]
                for col in df.columns:
                    if col != 'time':  # Skip the time column
                        sensor_number = col
                        sensor_id = sensor_ids[sensor_number]
                        sensor_data.append((timestamp_id, sensor_id, row[col]))

            # Insert the rows into the `accelerations` table
            cursor.executemany(
                "INSERT INTO accelerations (timestamp_id, sensor_id, acceleration_value) VALUES (?, ?, ?)",
                sensor_data
            )
            conn.commit()  # Commit the transaction
            conn.close()

            persistent_buffer.clear()

            if config["debug"]:
                print(f"6) Buffer to SQLite3 successful. {len(sensor_data)} accelerations inserted.")
            break

        except Exception as e:
            print(f"Error: {e}")
            attempt += 1
            if attempt < max_retries:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2
            else:
                print("Maximum attempts reached. Data could not be saved.")
            break

        finally:
            if 'conn' in locals() and conn:
                conn.close()

def backup_data(db_config, sqlite_db_path, raw_db, config, sensor_numbers, stop_event, backup_time, persistent_buffer, total_capture_time):
    """
    Performs a backup of all data from the SQLite3 database (buffer) to the MongoDB (raw) database.
    Processes data in batches based on timestamps and correctly deletes processed records.
    """

    if backup_time == 0:
        
        print(Fore.RED + "The backup time is 0. No backups to MongoDB will be performed." + Style.RESET_ALL)
        return

    client = initialize_mongodb_client(db_config)  # Connect to MongoDB
    if not client:
        config['backup_time'] = 0  # Disable backups if MongoDB is unavailable
        print(Fore.RED + "MongoDB Server is unavailable, backups are disabled." + Style.RESET_ALL)
        return

    raw_collection = client[raw_db]['accelerations']
    max_timestamps_per_batch = 20000  # Batch size, in number of timestamps
    delete_in_progress = False

    while not stop_event.is_set() or delete_in_progress:
        start_time = time.time()  # Start time of each backup cycle

        if config["debug"]:
            print(Fore.GREEN + "----------------------------------------------Starting backup process..." + Style.RESET_ALL)

        try:
            # Connect to the SQLite3 database (buffer)
            conn = connect(sqlite_db_path)
            cursor = conn.cursor()

            # Enable WAL
            cursor.execute("PRAGMA journal_mode=WAL;")

            # Get every unique timestamp, in order
            cursor.execute("""
                SELECT DISTINCT t.id, t.timestamp 
                FROM timestamps t 
                JOIN accelerations a ON t.id = a.timestamp_id 
                ORDER BY t.timestamp ASC
            """)
            all_timestamps = cursor.fetchall()

            if all_timestamps:
                total_timestamps = len(all_timestamps)
                if config["debug"]:
                    print(Fore.YELLOW + f"Found {total_timestamps} timestamps in SQLite3. Processing in batches of up to {max_timestamps_per_batch} timestamps." + Style.RESET_ALL)

                total_backed_up = 0
                delete_in_progress = True  # Flag that a deletion is under way

                # Process every record in batches
                for i in range(0, total_timestamps, max_timestamps_per_batch):
                    timestamp_batch = all_timestamps[i:i + max_timestamps_per_batch]

                    bulk_insert = []

                    for timestamp_row in timestamp_batch:
                        timestamp_id, timestamp = timestamp_row

                        # Get every acceleration linked to the current timestamp
                        cursor.execute("""
                            SELECT a.sensor_id, a.acceleration_value
                            FROM accelerations a
                            WHERE a.timestamp_id = ?
                        """, (timestamp_id,))
                        acceleration_data = cursor.fetchall()

                        sensor_data = [
                            {"sensor_id": str(sensor_id), "acceleration": acceleration_value}
                            for sensor_id, acceleration_value in acceleration_data
                        ]

                        # Check whether the timestamp already exists in MongoDB
                        existing_doc = raw_collection.find_one({"timestamp": timestamp})
                        if existing_doc:
                            # Merge the data if it is already there
                            updated_sensor_data = existing_doc["sensor_data"] + sensor_data
                            raw_collection.update_one(
                                {"_id": existing_doc["_id"]},
                                {"$set": {"sensor_data": updated_sensor_data}}
                            )
                        else:
                            # Insert a new document
                            bulk_insert.append({
                                "timestamp": timestamp,
                                "sensor_data": sensor_data
                            })

                    # Insert all the new documents into MongoDB
                    if bulk_insert:
                        raw_collection.insert_many(bulk_insert, ordered=False)

                    # Delete the processed data from the SQLite buffer
                    timestamp_ids = [(row[0],) for row in timestamp_batch]
                    cursor.executemany("DELETE FROM timestamps WHERE id = ?", timestamp_ids)
                    cursor.execute("""
                        DELETE FROM accelerations
                        WHERE timestamp_id NOT IN (
                            SELECT id FROM timestamps
                        )
                    """)
                    conn.commit()

                    total_backed_up += len(timestamp_batch)

                    if config["debug"]:
                        print(Fore.CYAN + f"Batch backup completed ({len(timestamp_batch)} timestamps processed)." + Style.RESET_ALL)

                delete_in_progress = False  # Flag that the deletion is finished

                if config["debug"]:
                    print(Fore.YELLOW + f"Backup completed. {total_backed_up} timestamps transferred in {time.time() - start_time:.5f} seconds." + Style.RESET_ALL)

            else:
                if config["debug"]:
                    print(Fore.GREEN + "No new data in the buffer database to back up." + Style.RESET_ALL)

            # Work out the time left, so each cycle takes exactly backup_time.
            process_duration = time.time() - start_time
            remaining_time = max(0, backup_time - process_duration)  # Never negative
            time.sleep(remaining_time)

        except Exception as e:
            print(Fore.RED + f"Error during data backup: {e}" + Style.RESET_ALL)

        finally:
            conn.close()  # Close the SQLite3 connection

    # If the stop event was set, make sure the backup finishes cleanly
    if stop_event.is_set() and delete_in_progress:
        print(Fore.YELLOW + "Stop requested, completing ongoing backup..." + Style.RESET_ALL)
        try:
            conn = connect(sqlite_db_path)
            cursor = conn.cursor()

            # Enable WAL
            cursor.execute("PRAGMA journal_mode=WAL;")

            # Process whatever data is left
            cursor.execute("""
                SELECT DISTINCT t.id, t.timestamp 
                FROM timestamps t 
                JOIN accelerations a ON t.id = a.timestamp_id 
                ORDER BY t.timestamp ASC
            """)
            timestamp_batch = cursor.fetchall()

            while timestamp_batch:
                bulk_insert = []

                for timestamp_row in timestamp_batch:
                    timestamp_id, timestamp = timestamp_row

                    # Get every acceleration linked to the current timestamp
                    cursor.execute("""
                        SELECT a.sensor_id, a.acceleration_value
                        FROM accelerations a
                        WHERE a.timestamp_id = ?
                    """, (timestamp_id,))
                    acceleration_data = cursor.fetchall()

                    sensor_data = [
                        {"sensor_id": str(sensor_id), "acceleration": acceleration_value}
                        for sensor_id, acceleration_value in acceleration_data
                    ]

                    # Check whether the timestamp already exists in MongoDB
                    existing_doc = raw_collection.find_one({"timestamp": timestamp})
                    if existing_doc:
                        # Merge the data if it is already there
                        updated_sensor_data = existing_doc["sensor_data"] + sensor_data
                        raw_collection.update_one(
                            {"_id": existing_doc["_id"]},
                            {"$set": {"sensor_data": updated_sensor_data}}
                        )
                    else:
                        # Insert a new document
                        bulk_insert.append({
                            "timestamp": timestamp,
                            "sensor_data": sensor_data
                        })

                # Insert all the new documents into MongoDB
                if bulk_insert:
                    raw_collection.insert_many(bulk_insert, ordered=False)

                # Delete the processed data from the SQLite buffer
                timestamp_ids = [(row[0],) for row in timestamp_batch]
                cursor.executemany("DELETE FROM timestamps WHERE id = ?", timestamp_ids)
                cursor.execute("""
                    DELETE FROM accelerations
                    WHERE timestamp_id NOT IN (
                        SELECT id FROM timestamps
                    )
                """)
                conn.commit()

                cursor.execute("""
                    SELECT DISTINCT t.id, t.timestamp 
                    FROM timestamps t 
                    JOIN accelerations a ON t.id = a.timestamp_id 
                    ORDER BY t.timestamp ASC
                """)
                timestamp_batch = cursor.fetchall()

            print(Fore.GREEN + "Final backup completed. Buffer completely cleared." + Style.RESET_ALL)

        except Exception as e:
            print(Fore.RED + f"Error during data backup: {e}" + Style.RESET_ALL)

        finally:
            conn.close()

    close_mongodb_client()
    print(Fore.RED + "**The backup process has been stopped successfully.**" + Style.RESET_ALL)



    if persistent_buffer:  # Flush whatever is left in the buffer
        buffer_to_db(persistent_buffer, sqlite_db_path, config)  # Use SQLite3 as the buffer

    if total_capture_time == 0:
        print(Fore.GREEN + "Continuous capture. Press ENTER to stop."+ Style.RESET_ALL)
    else:
        print(Fore.RED + "DATA CAPTURE COMPLETED. Press ENTER to finish."+ Style.RESET_ALL)

    stop_event.set()
