@echo off
rem The initial configuration of a project's tracker: installs the environment, then creates the
rem project's tracker folder. Run as init.bat FOLDER LANGUAGE (LANGUAGE: en or es).
setlocal
if "%~2"=="" (
    echo usage: init.bat FOLDER LANGUAGE   ^(LANGUAGE: en or es^) 1>&2
    exit /b 1
)
call "%~dp0install.bat" || exit /b 1
call "%~dp0env.bat" || exit /b 1
python "%~dp0track.py" --dir "%~1" init --language %2
