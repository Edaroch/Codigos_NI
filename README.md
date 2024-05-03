
## Project Description

This project is the data acquisition of seismic sensors trough National Instruments (NI) DAQ. It provides endpoints for authentication, listing packages, and downloading packages. The sensor data is stored in text files and an SQLite database.

## Installation and Setup

1. Clone the repository to your local machine.
2. Modify the `php.ini` file in your XAMPP/PHP directory. Uncomment (remove the `;`) from `sqlite3` extension and save the changes.
3. Restart Apache server.
4. In XAMPP, stop MySQL and Apache, then start them again.
5. Set up a local web server environment (e.g., Apache, Nginx, or XAMPP).
6. Configure environment variables by creating a `.env` file in the project root directory if necessary.
7. Run `composer install` to install PHP dependencies.
8. Make sure the necessary PHP extensions are enabled (e.g., `pdo_sqlite`, `openssl`).
9. Access the application through the web server.

You can test the API with Postman using the following route: `ruta.../APIRest/sensordb.php?limit=100&page=1`.

## Folder Structure

- **src/**: Contains the PHP classes for the project.
- **controllers/**: Contains the PHP files that handle HTTP requests and responses.
- **data/**: Contains text files with sensor data.
- **sqldb/**: Contains an SQLite database (`dataraw.db`) for storing sensor data.
- **vendor/**: Contains the project dependencies.

The `.htaccess` files in the `data/` and `sqldb/` directories restrict direct access to the data.

## Files

- **.gitattributes**: Git configuration file for handling line endings.
- **index.php**: The main entry point for the API.
- **composer.json**: Defines the project dependencies.

## Classes

- **Authenticator.php**: Handles user authentication.
- **DatabaseHelper.php**: Provides methods for interacting with the database.
- **FileManager.php**: Provides methods for managing files.

## Usage
1. Navigate to the application URL in your web browser.
2. Log in with your credentials.
3. Use the control panel to list available data packages and download them.
4. Apply dynamic filters to refine your search.

## Dependencies
- **PHP**: Server-side scripting language for backend logic.
- **Composer**: Dependency manager for PHP.