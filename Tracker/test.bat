@echo off
rem Runs the CLI tests against a temporary database (never Spec/tracker.db).
setlocal
call "%~dp0env.bat" || exit /b 1
python "%~dp0test_track.py" %*
