@echo off
echo ==========================================================
echo ESP32 RSSI Monitor — Windows Installer
echo ==========================================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not on PATH.
    echo Please install Python from https://python.org
    echo.
    set INSTALL_FAILED=1
)

REM Check requirements
if not defined INSTALL_FAILED (
    echo Installing Python dependencies...
    pip install -r requirements.txt >nul 2>&1
    if %errorlevel% neq 0 (
        echo Failed to install dependencies.
        echo Make sure pip is available and you have internet access.
        set INSTALL_FAILED=1
    )
)

REM Create venv if requested
:venv_loop
set VENV_Q=
echo.
echo Do you want to create a virtual environment? (y/n)
set /p VENV_Q=
if /i "%VENV_Q%" equ "y" (
    echo Creating venv...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo Failed to create venv.
        set INSTALL_FAILED=1
    )
)

if defined INSTALL_FAILED (
    echo.
    echo ==========================================================
    echo INSTALLATION FAILED
    echo ==========================================================
    echo.
    echo Please install Python, then run: pip install Flask pyserial
    echo Then rerun this installer, or run: python app.py
    echo.
) else (
    echo.
    echo ==========================================================
    echo Installation complete!
    echo ==========================================================
    echo.
    echo To run the dashboard: python app.py
    echo Then open http://127.0.0.1:5000 in your browser
    echo.
    echo Remember: Close Arduino Serial Monitor before connecting!
)

pause