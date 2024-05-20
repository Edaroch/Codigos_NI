from os import stat, makedirs, path

def check_and_create_paths(config):
    db_path = fr'{config["db_fold"]}{config["db_file"]}.db'
    data_path = config["data_path"]  # Define data_path at the start of the function

    # Check if the db_path directory exists
    if not path.exists(config["db_fold"]):
        # Check if the 'Accelerations/' folder exists, otherwise create it with intermediate directories
        if not path.exists("Accelerations/"):
            makedirs("Accelerations/")
        # Use 'Accelerations/' as the new db_folder
        db_path = fr'Accelerations/{config["db_file"]}.db'

    # Check if the data path exists, otherwise create it with all intermediate directories
    if not path.exists(data_path):
        makedirs(data_path, exist_ok=True)

    return db_path, data_path  # Return the updated paths
