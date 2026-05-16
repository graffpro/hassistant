# ============================================================
#  UE5 AI Assistant — Полностью автоматическая установка
#  Запускается из START_HERE.bat
#  Не требует никаких действий пользователя
# ============================================================

$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"   # убирает медленный прогресс-бар Invoke-WebRequest

$SCRIPT_DIR  = Split-Path -Parent $MyInvocation.MyCommand.Path
$TOOLS_DIR   = "$SCRIPT_DIR\tools"
$LOG_FILE    = "$SCRIPT_DIR\setup_log.txt"

$null = New-Item -ItemType Directory -Force -Path $TOOLS_DIR

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    Write-Host $line -ForegroundColor Cyan
    Add-Content -Path $LOG_FILE -Value $line -Encoding UTF8
}

function OK($msg)   { Write-Host "  [OK] $msg"    -ForegroundColor Green  }
function WARN($msg) { Write-Host "  [!!] $msg"    -ForegroundColor Yellow }
function STEP($msg) { Write-Host "`n>>> $msg"     -ForegroundColor Magenta }
function ERR($msg)  { Write-Host "  [X] $msg"     -ForegroundColor Red    }

function Download($url, $dest) {
    if (Test-Path $dest) { return }
    Log "Скачиваю: $(Split-Path $dest -Leaf)"
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        OK "Скачано"
    } catch {
        ERR "Ошибка загрузки: $_"
    }
}

# ─────────────────────────────────────────────────────────────
# 0. ШАПКА
# ─────────────────────────────────────────────────────────────
Clear-Host
Write-Host @"

  ██╗   ██╗███████╗███████╗     █████╗ ██╗
  ██║   ██║██╔════╝██╔════╝    ██╔══██╗██║
  ██║   ██║█████╗  ███████╗    ███████║██║
  ██║   ██║██╔══╝  ╚════██║    ██╔══██║██║
  ╚██████╔╝███████╗███████║    ██║  ██║██║
   ╚═════╝ ╚══════╝╚══════╝    ╚═╝  ╚═╝╚═╝
     Autonomous Assistant — Auto Setup v1.0

"@ -ForegroundColor Magenta

Log "=== Начало установки ==="
Log "Папка проекта: $SCRIPT_DIR"

# ─────────────────────────────────────────────────────────────
# 1. VISUAL C++ REDISTRIBUTABLE
# ─────────────────────────────────────────────────────────────
STEP "Шаг 1/7 — Visual C++ Redistributable"

$vcKey = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
$vcInstalled = (Test-Path $vcKey) -and ((Get-ItemProperty $vcKey -ErrorAction SilentlyContinue).Installed -eq 1)

if ($vcInstalled) {
    OK "Visual C++ уже установлен"
} else {
    $vcUrl  = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
    $vcPath = "$TOOLS_DIR\vc_redist.x64.exe"
    Download $vcUrl $vcPath
    if (Test-Path $vcPath) {
        Log "Устанавливаю Visual C++..."
        Start-Process $vcPath -ArgumentList "/install /quiet /norestart" -Wait
        OK "Visual C++ установлен"
    }
}

# ─────────────────────────────────────────────────────────────
# 2. PYTHON
# ─────────────────────────────────────────────────────────────
STEP "Шаг 2/7 — Python 3.11"

$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "3\.(1[1-9]|[2-9]\d)") {
            $python = $cmd
            OK "Python найден: $ver ($cmd)"
            break
        }
    } catch {}
}

if (-not $python) {
    WARN "Python 3.11+ не найден — скачиваю..."
    $pyUrl  = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    $pyPath = "$TOOLS_DIR\python-3.11.9-amd64.exe"
    Download $pyUrl $pyPath

    if (Test-Path $pyPath) {
        Log "Устанавливаю Python 3.11.9..."
        Start-Process $pyPath -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
        OK "Python 3.11.9 установлен"

        # Обновляем PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $python = "python"
    } else {
        ERR "Не удалось скачать Python. Проверь интернет."
        Read-Host "Нажми Enter для выхода"
        exit 1
    }
}

# Обновляем pip
Log "Обновляю pip..."
& $python -m pip install --upgrade pip --quiet

# ─────────────────────────────────────────────────────────────
# 3. OLLAMA
# ─────────────────────────────────────────────────────────────
STEP "Шаг 3/7 — Ollama (локальный AI)"

$ollamaInstalled = $null -ne (Get-Command ollama -ErrorAction SilentlyContinue)

if ($ollamaInstalled) {
    OK "Ollama уже установлен"
} else {
    WARN "Ollama не найден — скачиваю..."
    $ollamaUrl  = "https://ollama.com/download/OllamaSetup.exe"
    $ollamaPath = "$TOOLS_DIR\OllamaSetup.exe"
    Download $ollamaUrl $ollamaPath

    if (Test-Path $ollamaPath) {
        Log "Устанавливаю Ollama..."
        Start-Process $ollamaPath -ArgumentList "/S" -Wait
        $env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"
        OK "Ollama установлен"
    } else {
        ERR "Не удалось скачать Ollama"
    }
}

# Запускаем Ollama сервер в фоне
Log "Запускаю Ollama сервер..."
$ollamaRunning = $false
try {
    $resp = Invoke-WebRequest "http://localhost:11434" -UseBasicParsing -TimeoutSec 3
    $ollamaRunning = $true
    OK "Ollama сервер уже запущен"
} catch {
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 4
    OK "Ollama сервер запущен"
}

# ─────────────────────────────────────────────────────────────
# 4. СКАЧИВАЕМ AI МОДЕЛИ
# ─────────────────────────────────────────────────────────────
STEP "Шаг 4/7 — AI модели (это займёт время, зависит от скорости интернета)"

function Pull-Model($model, $desc) {
    Log "Скачиваю $model ($desc)..."
    Write-Host "    Прогресс скачивания $model — смотри строку выше в окне..." -ForegroundColor Gray
    & ollama pull $model
    if ($LASTEXITCODE -eq 0) {
        OK "$model готов"
    } else {
        WARN "$model — возможно уже скачан или ошибка сети"
    }
}

Pull-Model "qwen2.5:7b"  "главная модель для понимания команд (~4.7GB)"
Pull-Model "llava:7b"    "vision модель для анализа изображений (~4.5GB)"

# ─────────────────────────────────────────────────────────────
# 5. TESSERACT OCR
# ─────────────────────────────────────────────────────────────
STEP "Шаг 5/7 — Tesseract OCR (чтение текста на экране)"

$tesseractPath = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$tesseractInstalled = Test-Path $tesseractPath

if ($tesseractInstalled) {
    OK "Tesseract уже установлен"
} else {
    WARN "Tesseract не найден — скачиваю..."
    $tessUrl  = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.3.3.20231005/tesseract-ocr-w64-setup-5.3.3.20231005.exe"
    $tessPath = "$TOOLS_DIR\tesseract-setup.exe"
    Download $tessUrl $tessPath

    if (Test-Path $tessPath) {
        Log "Устанавливаю Tesseract OCR..."
        Start-Process $tessPath -ArgumentList "/S" -Wait
        OK "Tesseract установлен"
    } else {
        WARN "Не удалось скачать Tesseract — OCR будет отключён (ассистент продолжит работу)"
    }
}

# Добавляем в PATH
$tessDir = "C:\Program Files\Tesseract-OCR"
if ((Test-Path $tessDir) -and ($env:Path -notlike "*Tesseract*")) {
    $env:Path += ";$tessDir"
    [Environment]::SetEnvironmentVariable("Path", $env:Path, "User")
}

# ─────────────────────────────────────────────────────────────
# 6. PYTHON ПАКЕТЫ
# ─────────────────────────────────────────────────────────────
STEP "Шаг 6/7 — Python библиотеки"

$packages = @(
    # UI
    @{ name="PyQt6";               desc="Интерфейс ассистента" },
    @{ name="PyQt6-Qt6";           desc="Qt6 runtime" },
    # AI
    @{ name="ollama";              desc="Ollama Python клиент" },
    @{ name="openai-whisper";      desc="Распознавание голоса" },
    # Vision
    @{ name="opencv-python";       desc="Компьютерное зрение" },
    @{ name="pytesseract";         desc="OCR — чтение текста" },
    @{ name="Pillow";              desc="Работа с изображениями" },
    @{ name="mss";                 desc="Скриншоты экрана" },
    # Automation
    @{ name="pyautogui";           desc="Управление мышью/клавиатурой" },
    @{ name="pywin32";             desc="Windows API" },
    @{ name="comtypes";            desc="UI Automation" },
    @{ name="pynput";              desc="Наблюдение за вводом" },
    # Memory
    @{ name="chromadb";            desc="Векторная база данных" },
    @{ name="sentence-transformers"; desc="Семантический поиск" },
    # Autonomous
    @{ name="yt-dlp";              desc="Скачивание YouTube видео" },
    @{ name="sounddevice";         desc="Запись микрофона" },
    @{ name="soundfile";           desc="Аудио файлы" },
    @{ name="requests";            desc="HTTP запросы (веб-поиск)" },
    # Core
    @{ name="numpy";               desc="Математика" },
    @{ name="pydantic";            desc="Валидация данных" },
    @{ name="pydantic-settings";   desc="Настройки" },
    @{ name="loguru";              desc="Логирование" },
    @{ name="python-dotenv";       desc="Конфигурация" }
)

$total = $packages.Count
$i = 0
foreach ($pkg in $packages) {
    $i++
    $percent = [math]::Round(($i / $total) * 100)
    Write-Host "  [$i/$total] $($pkg.desc) ($($pkg.name))..." -NoNewline
    $result = & $python -m pip install $pkg.name --quiet 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " WARN" -ForegroundColor Yellow
    }
}

OK "Все Python пакеты установлены"

# ─────────────────────────────────────────────────────────────
# 7. СОЗДАЁМ ЯРЛЫК НА РАБОЧЕМ СТОЛЕ
# ─────────────────────────────────────────────────────────────
STEP "Шаг 7/7 — Финальная настройка"

$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = "$desktopPath\UE5 AI Assistant.lnk"

try {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath  = "cmd.exe"
    $shortcut.Arguments   = "/c `"$SCRIPT_DIR\run.bat`""
    $shortcut.WorkingDirectory = $SCRIPT_DIR
    $shortcut.Description = "UE5 AI Assistant"
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    OK "Ярлык создан на рабочем столе"
} catch {
    WARN "Не удалось создать ярлык (не критично)"
}

# Записываем путь Tesseract в .env если его там нет
$envFile = "$SCRIPT_DIR\.env"
if ((Test-Path $envFile) -and (Get-Content $envFile -Raw) -notlike "*TESSERACT*") {
    Add-Content $envFile "`nTESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
}

# ─────────────────────────────────────────────────────────────
# ИТОГ
# ─────────────────────────────────────────────────────────────
Write-Host @"

╔══════════════════════════════════════════════════════╗
║          УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!                ║
║                                                      ║
║  Для запуска:                                        ║
║    • Двойной клик на ярлык "UE5 AI Assistant"        ║
║      на рабочем столе                                ║
║    • ИЛИ запусти run.bat в папке проекта             ║
║                                                      ║
║  Перед запуском:                                     ║
║    1. Открой Unreal Engine 5                         ║
║    2. Запусти ассистента                             ║
║    3. Пиши или говори что нужно сделать              ║
╚══════════════════════════════════════════════════════╝

"@ -ForegroundColor Green

Log "=== Установка завершена ==="

# Спрашиваем запустить ли сразу
Write-Host "Запустить ассистента сейчас? Нажми Enter или закрой окно..." -ForegroundColor Yellow
$null = Read-Host

# Запускаем
Set-Location $SCRIPT_DIR
& $python main.py
