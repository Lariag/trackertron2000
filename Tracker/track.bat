@echo off
rem The tracker CLI: track next / list / show / add / note / set / close / drop / rank / subjects.
setlocal
call "%~dp0env.bat" || exit /b 1
python "%~dp0track.py" %*