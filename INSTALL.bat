@echo off
echo =========================================================
echo WELCOME TO THE PROJECT SETUP
echo =========================================================

:: Step 1: Check if Python is installed and if version is >= 3.8
echo Step 1: Checking if Python is installed and if version is 3.8 or higher...

python --version 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed.
    echo Please install the latest version of Python from: https://www.python.org/downloads/
    pause
    exit /b
)

:: Check Python version
for /f "tokens=2 delims= " %%a in ('python --version') do set PYTHON_VERSION=%%a
echo Installed Python version: %PYTHON_VERSION%

:: Check if Python version is 3.8 or higher
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set MAJOR=%%a
    set MINOR=%%b
)

if %MAJOR% LSS 3 (
    echo ERROR: Python version is lower than 3.8. Please install Python 3.8 or higher.
    echo You can download the latest version from: https://www.python.org/downloads/
    pause
    exit /b
)

if %MAJOR%==3 (
    if %MINOR% LSS 8 (
        echo ERROR: Python version is lower than 3.8. Please install Python 3.8 or higher.
        echo You can download the latest version from: https://www.python.org/downloads/
        pause
        exit /b
    )
)

echo Python 3.8 or higher is installed.
echo.

:: Step 2: Check if NI MAX is installed
echo Step 2: This project requires NI MAX to be installed.
echo Is NI MAX installed on this computer? (y/n)
set /p nimax_installed="Answer: "

if /i "%nimax_installed%"=="y" (
    echo Continuing with the setup...
) else (
    echo =========================================================
    echo PLEASE DOWNLOAD AND INSTALL NI MAX FROM: https://www.ni.com
    echo After installation, run this script again.
    echo =========================================================
    pause
    exit /b
)

:: Step 3: Check for requirements.txt file
if not exist requirements.txt (
    echo ERROR: requirements.txt file not found in the current directory.
    echo Make sure the file is located in the project root folder.
    pause
    exit /b
)
echo requirements.txt file found.
echo.

:: Step 4: Create virtual environment
echo Step 4: Creating Python virtual environment (.venv)...
python -m venv .venv
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b
)

:: Step 5: Activate virtual environment and install packages
echo Step 5: Activating virtual environment and installing packages...
call .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to install packages from requirements.txt.
    deactivate
    pause
    exit /b
)
deactivate

echo =========================================================
echo SETUP COMPLETED SUCCESSFULLY.
echo =========================================================
echo Press any key to exit...
pause
