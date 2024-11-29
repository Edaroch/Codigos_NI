@echo off
echo Iniciando proceso principal...
call .venv\Scripts\activate
python main.py
deactivate
pause
