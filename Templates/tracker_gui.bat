@echo off
rem The tracker GUI for this project: the window of the tracker repository on this folder.
setlocal
call "%~dp0find-tracker.bat" || exit /b 1
call "%TRACKER_HOME%\Tracker\env.bat" || exit /b 1
start "" pythonw "%TRACKER_HOME%\TrackerGui\main.py" --dir "%~dp0."
