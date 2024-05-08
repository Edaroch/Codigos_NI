from os import stat, mkdir

def check_and_create_paths(config):
    db_path = fr'{config["db_fold"]}{config["db_file"]}.db'
    data_path = config["data_path"]  # Define data_path at the start of the function

    try:
        stat(config["db_fold"])
    except FileNotFoundError:
        mkdir("Accelerations/")
        db_path = fr'Accelerations/{config["db_file"]}.db'  # Reassign db_path if needed

    try:
        stat(data_path)
    except FileNotFoundError:
        mkdir(data_path)  # Correctly use data_path to create the directory

    return db_path, data_path  # Return the paths which are now always defined

