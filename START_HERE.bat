@echo off
title UE5 AI Assistant - Auto Setup

echo.
echo  ====================================================
echo   UE5 AI Assistant - Auto Setup
echo   Please wait, everything installs automatically...
echo  ====================================================
echo.

powershell -Command "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy Bypass -Force" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_auto.ps1"

if errorlevel 1 (
    echo.
    echo  [ERROR] Setup failed. Check setup_log.txt for details.
    echo.
    pause
)