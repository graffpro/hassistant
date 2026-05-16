@echo off
title UE5 AI Assistant - Build Installer

echo.
echo  Building Install.exe...
echo.

cd /d "%~dp0"

python -m PyInstaller --onefile --windowed --name "Install" installer\installer_main.py

if errorlevel 1 (
    echo  [ERROR] Build failed.
    pause
) else (
    echo  [OK] Install.exe created in dist folder.
    pause
)