@echo off
echo Iniciando GUI...
call .venv\Scripts\activate
python interface.py
deactivate
pause
