@echo off
chcp 65001 >nul
echo ============================================
echo   UE5 AI Assistant — Сборка .exe (PyInstaller)
echo ============================================
echo.

cd /d "%~dp0"

:: Проверка PyInstaller
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo Устанавливаем PyInstaller...
    pip install pyinstaller --quiet
)

:: Сборка
echo Собираем ue5_assistant.exe...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "UE5_Assistant" ^
    --add-data "assets;assets" ^
    --add-data "unreal;unreal" ^
    --hidden-import PyQt6 ^
    --hidden-import PyQt6.QtWidgets ^
    --hidden-import PyQt6.QtCore ^
    --hidden-import PyQt6.QtGui ^
    --hidden-import ollama ^
    --hidden-import chromadb ^
    --hidden-import cv2 ^
    --hidden-import pytesseract ^
    --hidden-import pyautogui ^
    --hidden-import pynput ^
    --hidden-import sounddevice ^
    --hidden-import whisper ^
    --hidden-import loguru ^
    --hidden-import sqlite3 ^
    --collect-all chromadb ^
    --collect-all sentence_transformers ^
    main.py

echo.
if exist "dist\UE5_Assistant.exe" (
    echo [OK] Сборка завершена: dist\UE5_Assistant.exe
) else (
    echo [ОШИБКА] Сборка не удалась. Смотри логи выше.
)
pause
