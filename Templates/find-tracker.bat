@echo off
rem Sets TRACKER_HOME, where the tracker repository is on this machine: the TRACKER_HOME
rem environment variable when it is set, else the path in tool-path.txt next to this file (written
rem by track.init.bat, local to each machine and ignored by git). Called by the other launchers.
if defined TRACKER_HOME goto check
if not exist "%~dp0tool-path.txt" (
    echo find-tracker.bat: the tracker is not set up on this machine; run track.init.bat PATH_TO_THE_TRACKER 1>&2
    exit /b 1
)
set /p TRACKER_HOME=<"%~dp0tool-path.txt"
:check
if not exist "%TRACKER_HOME%\Tracker\track.py" (
    echo find-tracker.bat: no tracker at "%TRACKER_HOME%" 1>&2
    exit /b 1
)
exit /b 0
