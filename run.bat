@echo off
chcp 65001 >nul
echo Запуск UE5 AI Assistant...
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Ассистент завершился с ошибкой.
    pause
)
