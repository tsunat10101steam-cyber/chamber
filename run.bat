@echo off
cd /d "%~dp0"
if not exist .venv (
  echo First run: creating venv and installing packages...
  python -m venv .venv
  .venv\Scripts\python -m pip install -q -r requirements.txt
)
rem Run as an app window without a console (closing the window stops the server)
start "" .venv\Scripts\pythonw.exe app.py
