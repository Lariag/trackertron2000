@echo off
rem Activates the pw-tracker conda environment and nothing else: no environment check, no creation,
rem no installs and nothing on stdout, so the CLI starts fast and its output (JSON included) stays
rem clean. Called by track.bat and test.bat. env_install.bat creates the environment and installs.
call conda activate pw-tracker 2>nul
if errorlevel 1 (
    echo env.bat: cannot activate the conda environment pw-tracker; run env_install.bat once 1>&2
    exit /b 1
)
exit /b 0
