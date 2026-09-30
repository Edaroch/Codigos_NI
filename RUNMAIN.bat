@echo off
echo Iniciando proceso principal...
call .venv\Scripts\activate
python src\main.py
deactivate
pause
