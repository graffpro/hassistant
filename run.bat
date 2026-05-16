@echo off
title UE5 AI Assistant

echo.
echo  Starting UE5 AI Assistant...
echo.

cd /d "%~dp0"

python main.py

if errorlevel 1 (
    echo.
    echo  [ERROR] Failed to start. Check that Python is installed.
    echo.
    pause
)