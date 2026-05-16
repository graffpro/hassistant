@echo off
title UE5 AI Assistant - Build

echo.
echo  Building UE5 AI Assistant...
echo.

cd /d "%~dp0"

python -m PyInstaller --onefile --windowed --name "UE5_Assistant" main.py

if errorlevel 1 (
    echo  [ERROR] Build failed.
    pause
) else (
    echo  [OK] Build complete! Check dist folder.
    pause
)