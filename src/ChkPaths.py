from os import stat, mkdir

def check_and_create_paths(config):
    db_path = fr'{config["db_fold"]}{config["db_file"]}.db'

    try:
        stat(config["db_fold"])
    except FileNotFoundError:
        mkdir("Accelerations/")
        db_path = fr'Accelerations/{config["db_file"]}.db'  # Reassign db_path if needed

    return db_path # Return the paths which are now always defined

