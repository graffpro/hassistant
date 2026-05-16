@echo off
chcp 65001 >nul
echo ============================================
echo   UE5 AI Assistant — Установка зависимостей
echo ============================================
echo.

:: Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден. Установи Python 3.11+ с python.org
    pause
    exit /b 1
)

echo [OK] Python найден
echo.

:: Обновляем pip
python -m pip install --upgrade pip --quiet

:: Устанавливаем зависимости
echo [1/5] Устанавливаем PyQt6...
pip install PyQt6 PyQt6-Qt6 --quiet

echo [2/5] Устанавливаем Ollama клиент...
pip install ollama --quiet

echo [3/5] Устанавливаем Vision (OpenCV + Tesseract)...
pip install opencv-python pytesseract Pillow mss --quiet

echo [4/5] Устанавливаем Automation...
pip install pyautogui pywin32 comtypes pynput --quiet

echo [5/5] Устанавливаем Memory (ChromaDB)...
pip install chromadb sentence-transformers --quiet

echo.
echo [6/6] Устанавливаем Autonomous Agent зависимости...
pip install yt-dlp openai-whisper soundfile requests --quiet

echo.
echo [ОК] Устанавливаем остальные зависимости...
pip install sounddevice numpy pydantic pydantic-settings loguru python-dotenv --quiet

echo.
echo ============================================
echo   Проверка Ollama
echo ============================================
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [ВНИМАНИЕ] Ollama не установлен!
    echo Скачай с: https://ollama.com/download
    echo После установки запусти: ollama pull qwen2.5:7b
) else (
    echo [OK] Ollama найден
    echo Убедись что модель скачана: ollama pull qwen2.5:7b
)

echo.
echo ============================================
echo   Установка завершена!
echo   Запуск: python main.py
echo ============================================
pause
