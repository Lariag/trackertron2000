@echo off
rem The tracker GUI: the same CLI (Tools/Tracker/track.py) behind a window. Installs PySide6 into the
rem pw-tracker conda environment on first run.
setlocal
call "%~dp0..\Tracker\env_install.bat" "%~dp0requirements.txt" || exit /b 1
start "" pythonw "%~dp0main.py"
