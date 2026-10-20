@echo off
rem Creates the pw-tracker conda environment if missing, activates it, installs a requirements file
rem when it changed since the last install (stamp: <file>.installed next to it). Called by the tracker
rem GUI launcher, and by hand once on a new machine; the argument is the requirements file, default
rem this folder's. The CLI and its tests use env.bat, which only activates.
set ENV_NAME=pw-tracker
set REQ=%~1
if "%REQ%"=="" set REQ=%~dp0requirements.txt
call conda env list 2>nul | findstr /B /C:"%ENV_NAME% " >nul
if errorlevel 1 (
    echo Creating conda environment %ENV_NAME%...
    call conda create -y -n %ENV_NAME% python=3.12 >nul
    if errorlevel 1 exit /b 1
)
call conda activate %ENV_NAME%
if errorlevel 1 exit /b 1
fc "%REQ%" "%REQ%.installed" >nul 2>&1
if errorlevel 1 (
    echo Installing %REQ%...
    pip install -q -r "%REQ%"
    if errorlevel 1 exit /b 1
    copy /y "%REQ%" "%REQ%.installed" >nul
)
exit /b 0
