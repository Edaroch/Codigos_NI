from pymongo import MongoClient
'''

Just to check if raw data in MongoDB is duplicated or orphaned.

'''    
# MongoDB connection settings
DB_HOST = "localhost"
DB_PORT = 27017
RAW_DB_NAME = "acquisition_db_raw"  # Name of the MongoDB database
RAW_COLLECTION_NAME = "accelerations"  # Collection holding the data

def check_mongo_data():
    try:
        # Connect to MongoDB
        client = MongoClient(DB_HOST, DB_PORT)
        db = client[RAW_DB_NAME]
        collection = db[RAW_COLLECTION_NAME]

        print("Connected to the database.")

        # Look for duplicated timestamps
        duplicate_timestamps = collection.aggregate([
            {
                "$group": {
                    "_id": "$timestamp",
                    "count": {"$sum": 1},
                    "documents": {"$push": "$$ROOT"}
                }
            },
            {
                "$match": {
                    "count": {"$gt": 1}
                }
            }
        ])

        duplicates = list(duplicate_timestamps)
        if duplicates:
            print(f"Found {len(duplicates)} duplicated timestamps:")
            for dup in duplicates[:10]:
                print(f"\n- Timestamp: {dup['_id']} | Repeats: {dup['count']}")
                for doc in dup["documents"]:
                    print(f"  - ID: {doc['_id']}")
                    for sensor_data in doc["sensor_data"]:
                        print(f"    Sensor ID: {sensor_data['sensor_id']} | Acceleration: {sensor_data['acceleration']}")
        else:
            print("No duplicated timestamps were found.")

        # Look for orphaned accelerations (no sensor data)
        orphaned_accelerations = collection.find({
            "$or": [
                {"sensor_data": {"$exists": False}},
                {"sensor_data": {"$size": 0}}
            ]
        })

        orphaned_list = list(orphaned_accelerations)
        if orphaned_list:
            print(f"\nFound {len(orphaned_list)} orphaned acceleration records.")
            for orphan in orphaned_list[:10]:  # Show the first 10 orphaned records
                print(f"  - ID: {orphan['_id']} | Timestamp: {orphan.get('timestamp', 'N/A')}")
        else:
            print("\nNo orphaned acceleration records were found.")

    except Exception as e:
        print(f"Error while checking the data in MongoDB: {e}")

    finally:
        client.close()
        print("Database connection closed.")

if __name__ == "__main__":
    check_mongo_data()
