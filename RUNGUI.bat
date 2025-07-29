@echo off
echo Iniciando GUI...
call .venv\Scripts\activate
python src\GUI.py
deactivate
pause
