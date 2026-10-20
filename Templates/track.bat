@echo off
rem This project's tracker: the CLI of the tracker repository, on this folder. Run as
rem Tracker\track.bat <command>; Tracker\track.bat guide prints how to use it.
setlocal
call "%~dp0find-tracker.bat" || exit /b 1
call "%TRACKER_HOME%\Tracker\env.bat" || exit /b 1
python "%TRACKER_HOME%\Tracker\track.py" --dir "%~dp0." %*
