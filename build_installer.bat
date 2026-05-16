@echo off
chcp 65001 >nul
title Сборка Install.exe

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║      Сборка Install.exe (PyInstaller)           ║
echo  ╚══════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: Проверяем pip
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден. Сначала установи Python 3.11+
    pause
    exit /b 1
)

:: Устанавливаем PyInstaller если нет
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo Устанавливаю PyInstaller...
    pip install pyinstaller --quiet
)

:: Устанавливаем зависимости для установщика
echo Устанавливаю зависимости установщика...
pip install requests --quiet

echo.
echo Собираю Install.exe ...
echo (это займёт 1-3 минуты)
echo.

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "Install" ^
    --add-data "installer/error_fixer.py;installer" ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --hidden-import tkinter.scrolledtext ^
    --hidden-import winreg ^
    --hidden-import ctypes ^
    --hidden-import urllib.request ^
    --hidden-import subprocess ^
    --hidden-import threading ^
    --hidden-import requests ^
    --icon NONE ^
    installer/installer_main.py

echo.
if exist "dist\Install.exe" (
    echo  ╔══════════════════════════════════════════════════╗
    echo  ║   Install.exe успешно собран!                   ║
    echo  ║   Файл: dist\Install.exe                        ║
    echo  ║                                                  ║
    echo  ║   Теперь можно запускать Install.exe            ║
    echo  ║   на любом Windows ПК без Python               ║
    echo  ╚══════════════════════════════════════════════════╝

    :: Копируем в папку проекта
    copy "dist\Install.exe" "Install.exe" >nul
    echo  Скопировано в: %~dp0Install.exe
) else (
    echo  [ОШИБКА] Сборка не удалась. Смотри логи выше.
)

echo.
pause
