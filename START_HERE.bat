@echo off
chcp 65001 >nul
title UE5 AI Assistant — Автоустановка

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║       UE5 AI Assistant — Auto Setup             ║
echo  ║                                                  ║
echo  ║  Запускаю автоматическую установку...            ║
echo  ║  Просто наблюдай — всё сделается само.           ║
echo  ╚══════════════════════════════════════════════════╝
echo.

:: Разрешаем запуск PowerShell скриптов
powershell -Command "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy Bypass -Force" >nul 2>&1

:: Запускаем основной PowerShell установщик
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_auto.ps1"

:: Если PowerShell вылетел с ошибкой
if errorlevel 1 (
    echo.
    echo  [ОШИБКА] Что-то пошло не так.
    echo  Смотри файл setup_log.txt для деталей.
    echo.
    pause
)
