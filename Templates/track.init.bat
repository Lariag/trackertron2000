@echo off
rem Sets this project's tracker up on this machine. With a path, it first records where the tracker
rem repository is (tool-path.txt, local and ignored by git); then it creates the conda environment
rem if missing and installs what the CLI and the GUI need. Once per machine: track.init.bat [PATH].
setlocal
if not "%~1"=="" (
    > "%~dp0tool-path.txt" echo %~f1
)
call "%~dp0find-tracker.bat" || exit /b 1
call "%TRACKER_HOME%\Tracker\install.bat"
