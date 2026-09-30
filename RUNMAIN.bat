@echo off
echo Starting main process...
call .venv\Scripts\activate
python src\main.py
deactivate
pause
