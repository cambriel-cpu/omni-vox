@echo off
echo === Sonos Bridge Installer ===
echo.

REM Check for Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python not found! Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Installing dependencies...
pip install soco flask
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo === Installation complete! ===
echo.
echo To start the bridge, run: start.bat
echo Or manually: python server.py
echo.
pause
