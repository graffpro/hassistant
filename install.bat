@echo off
title UE5 AI Assistant - Install packages

echo.
echo  Installing Python packages...
echo.

cd /d "%~dp0"

python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo  [ERROR] Some packages failed. Try running as Administrator.
    echo.
    pause
) else (
    echo.
    echo  [OK] All packages installed!
    echo.
    pause
)