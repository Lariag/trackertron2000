@echo off
rem Creates the tracker's conda environment if missing and installs what the CLI and the GUI need
rem (each requirements file only when it changed). Called by init.bat and by each project's
rem track.init.bat.
call "%~dp0env_install.bat" "%~dp0requirements.txt" || exit /b 1
call "%~dp0env_install.bat" "%~dp0..\TrackerGui\requirements.txt" || exit /b 1
exit /b 0
