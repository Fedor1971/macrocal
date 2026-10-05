@echo off
rem MacroCal - one-click launcher (no PowerShell, no admin rights needed).
rem ecocal ships inside this folder (vendor\ecocal), so there is no separate ecocal install step.
rem First run: creates a private Python environment and installs the dependencies
rem (from the bundled "wheels" folder if present = works with no internet).
setlocal
cd /d "%~dp0"
set "PORT=8510"
set "URL=http://localhost:%PORT%"
title MacroCal

rem --- already running? just open it ----------------------------------------
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo The app is already running - opening %URL%
    start "" "%URL%"
    exit /b 0
)

rem --- find Python 3.11+ -----------------------------------------------------
set "PY="
for %%V in (3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo.
    echo  Python 3.11 or newer was not found.
    echo  Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^)
    echo  or ask your IT department, then run this file again.
    echo.
    pause
    exit /b 1
)

rem --- first-run setup -------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Creating the private Python environment ^(first run only^)...
    %PY% -m venv .venv
    if errorlevel 1 goto :setup_failed
)
if not exist ".venv\installed.flag" (
    if exist "wheels" (
        echo Installing bundled dependencies ^(offline^)...
        ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheels -r requirements.txt
    ) else (
        echo Installing dependencies from the internet / your package mirror...
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    )
    if errorlevel 1 goto :setup_failed
    echo ok> ".venv\installed.flag"
)

rem --- start the app and open the browser ------------------------------------
echo.
echo Starting MacroCal at %URL%
echo Keep this window open while you use the app. Close it ^(or press Ctrl+C^) to stop.
echo.
start "" cmd /c "ping -n 8 127.0.0.1 >nul & start "" "%URL%""
".venv\Scripts\python.exe" -m streamlit run app.py --server.port %PORT% --server.address localhost --server.headless true --browser.gatherUsageStats false
if errorlevel 1 (
    echo.
    echo The app stopped with an error ^(see above^).
    pause
)
exit /b 0

:setup_failed
echo.
echo  Setup failed ^(see the messages above^).
echo  - No internet / blocked PyPI?  Use the "offline" release zip that contains a "wheels" folder.
echo  - Half-finished setup?  Delete the ".venv" folder and run this file again.
echo.
pause
exit /b 1
