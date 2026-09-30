@echo off
echo Starting GUI...
call .venv\Scripts\activate
python src\GUI.py
deactivate
pause
