# ============================================================
#  UE5 AI Assistant - Fully Automatic Setup
#  Called from START_HERE.bat
# ============================================================

$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$TOOLS_DIR  = "$SCRIPT_DIR\tools"
$LOG_FILE   = "$SCRIPT_DIR\setup_log.txt"

$null = New-Item -ItemType Directory -Force -Path $TOOLS_DIR

function Log($msg)  { $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"; Write-Host $line -ForegroundColor Cyan; Add-Content -Path $LOG_FILE -Value $line -Encoding UTF8 }
function OK($msg)   { Write-Host "  [OK] $msg"  -ForegroundColor Green  }
function WARN($msg) { Write-Host "  [!!] $msg"  -ForegroundColor Yellow }
function STEP($msg) { Write-Host "`n>>> $msg"   -ForegroundColor Magenta }
function ERR($msg)  { Write-Host "  [X] $msg"   -ForegroundColor Red    }

function Download($url, $dest) {
    if (Test-Path $dest) { return }
    Log "Downloading: $(Split-Path $dest -Leaf)"
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        OK "Downloaded"
    } catch {
        ERR "Download failed: $_"
    }
}

Clear-Host
Write-Host "
  ==========================================
    UE5 AI Assistant - Auto Setup v1.0
    Please wait while everything installs...
  ==========================================
" -ForegroundColor Magenta

Log "=== Setup started ==="
Log "Project folder: $SCRIPT_DIR"

# ----------------------------------------------------------
# 1. VISUAL C++ REDISTRIBUTABLE
# ----------------------------------------------------------
STEP "Step 1/7 - Visual C++ Redistributable"

$vcKey = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
$vcInstalled = (Test-Path $vcKey) -and ((Get-ItemProperty $vcKey -ErrorAction SilentlyContinue).Installed -eq 1)

if ($vcInstalled) {
    OK "Visual C++ already installed"
} else {
    $vcUrl  = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
    $vcPath = "$TOOLS_DIR\vc_redist.x64.exe"
    Download $vcUrl $vcPath
    if (Test-Path $vcPath) {
        Log "Installing Visual C++..."
        Start-Process $vcPath -ArgumentList "/install /quiet /norestart" -Wait
        OK "Visual C++ installed"
    }
}

# ----------------------------------------------------------
# 2. PYTHON
# ----------------------------------------------------------
STEP "Step 2/7 - Python 3.11"

$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "3\.(1[1-9]|[2-9]\d)") {
            $python = $cmd
            OK "Python found: $ver ($cmd)"
            break
        }
    } catch {}
}

if (-not $python) {
    WARN "Python 3.11+ not found - downloading..."
    $pyUrl  = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    $pyPath = "$TOOLS_DIR\python-3.11.9-amd64.exe"
    Download $pyUrl $pyPath

    if (Test-Path $pyPath) {
        Log "Installing Python 3.11.9..."
        Start-Process $pyPath -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
        OK "Python 3.11.9 installed"
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $python = "python"
    } else {
        ERR "Failed to download Python. Check your internet connection."
        Read-Host "Press Enter to exit"
        exit 1
    }
}

Log "Upgrading pip..."
& $python -m pip install --upgrade pip --quiet

# ----------------------------------------------------------
# 3. OLLAMA
# ----------------------------------------------------------
STEP "Step 3/7 - Ollama (local AI)"

$ollamaInstalled = $null -ne (Get-Command ollama -ErrorAction SilentlyContinue)

if ($ollamaInstalled) {
    OK "Ollama already installed"
} else {
    WARN "Ollama not found - downloading..."
    $ollamaUrl  = "https://ollama.com/download/OllamaSetup.exe"
    $ollamaPath = "$TOOLS_DIR\OllamaSetup.exe"
    Download $ollamaUrl $ollamaPath

    if (Test-Path $ollamaPath) {
        Log "Installing Ollama..."
        Start-Process $ollamaPath -ArgumentList "/S" -Wait
        $env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"
        OK "Ollama installed"
    } else {
        ERR "Failed to download Ollama"
    }
}

Log "Starting Ollama server..."
try {
    $resp = Invoke-WebRequest "http://localhost:11434" -UseBasicParsing -TimeoutSec 3
    OK "Ollama server already running"
} catch {
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 4
    OK "Ollama server started"
}

# ----------------------------------------------------------
# 4. AI MODELS
# ----------------------------------------------------------
STEP "Step 4/7 - AI models (this may take a while depending on your internet speed)"

function Pull-Model($model, $desc) {
    Log "Downloading $model ($desc)..."
    & ollama pull $model
    if ($LASTEXITCODE -eq 0) { OK "$model ready" }
    else { WARN "$model - may already exist or network error" }
}

Pull-Model "qwen2.5:7b" "main command model (~4.7GB)"
Pull-Model "llava:7b"   "vision model for image analysis (~4.5GB)"

# ----------------------------------------------------------
# 5. TESSERACT OCR
# ----------------------------------------------------------
STEP "Step 5/7 - Tesseract OCR (reads text on screen)"

$tesseractPath = "C:\Program Files\Tesseract-OCR\tesseract.exe"

if (Test-Path $tesseractPath) {
    OK "Tesseract already installed"
} else {
    WARN "Tesseract not found - installing via winget..."
    $wingetTest = Get-Command winget -ErrorAction SilentlyContinue
    $installed = $false

    if ($wingetTest) {
        winget install --id UB-Mannheim.TesseractOCR --silent --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
        if (Test-Path $tesseractPath) { OK "Tesseract installed via winget"; $installed = $true }
    }

    if (-not $installed) {
        Log "Trying direct download..."
        $tessUrl  = "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.3.20231005.exe"
        $tessPath2 = "$TOOLS_DIR\tesseract-setup.exe"
        try {
            Invoke-WebRequest -Uri $tessUrl -OutFile $tessPath2 -UseBasicParsing -TimeoutSec 60
        } catch {}
        if (Test-Path $tessPath2) {
            Start-Process $tessPath2 -ArgumentList "/S" -Wait
            if (Test-Path $tesseractPath) { OK "Tesseract installed"; $installed = $true }
        }
    }

    if (-not $installed) {
        WARN "Could not install Tesseract - OCR disabled (assistant will still work without it)"
    }
}

$tessDir = "C:\Program Files\Tesseract-OCR"
if ((Test-Path $tessDir) -and ($env:Path -notlike "*Tesseract*")) {
    $env:Path += ";$tessDir"
    [Environment]::SetEnvironmentVariable("Path", $env:Path, "User")
}

# ----------------------------------------------------------
# 6. PYTHON PACKAGES
# ----------------------------------------------------------
STEP "Step 6/7 - Python packages"

$packages = @(
    @{ name="PyQt6";                 desc="UI framework" },
    @{ name="PyQt6-Qt6";             desc="Qt6 runtime" },
    @{ name="ollama";                desc="Ollama Python client" },
    @{ name="openai-whisper";        desc="Voice recognition" },
    @{ name="opencv-python";         desc="Computer vision" },
    @{ name="pytesseract";           desc="OCR - text reading" },
    @{ name="Pillow";                desc="Image processing" },
    @{ name="mss";                   desc="Screen capture" },
    @{ name="pyautogui";             desc="Mouse/keyboard control" },
    @{ name="pywin32";               desc="Windows API" },
    @{ name="comtypes";              desc="UI Automation" },
    @{ name="pynput";                desc="Input monitoring" },
    @{ name="chromadb";              desc="Vector database" },
    @{ name="sentence-transformers"; desc="Semantic search" },
    @{ name="yt-dlp";                desc="YouTube video download" },
    @{ name="sounddevice";           desc="Microphone recording" },
    @{ name="soundfile";             desc="Audio files" },
    @{ name="requests";              desc="HTTP requests" },
    @{ name="numpy";                 desc="Math library" },
    @{ name="pydantic";              desc="Data validation" },
    @{ name="pydantic-settings";     desc="Settings management" },
    @{ name="loguru";                desc="Logging" },
    @{ name="python-dotenv";         desc="Configuration" }
)

$total = $packages.Count
$i = 0
foreach ($pkg in $packages) {
    $i++
    Write-Host "  [$i/$total] $($pkg.desc) ($($pkg.name))..." -NoNewline
    $result = & $python -m pip install $pkg.name --quiet 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host " OK" -ForegroundColor Green }
    else { Write-Host " WARN" -ForegroundColor Yellow }
}

OK "All Python packages installed"

# ----------------------------------------------------------
# 7. FINALIZE
# ----------------------------------------------------------
STEP "Step 7/7 - Final setup"

$desktopPath  = [Environment]::GetFolderPath("Desktop")
$shortcutPath = "$desktopPath\UE5 AI Assistant.lnk"

try {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($shortcutPath)
    $sc.TargetPath       = "cmd.exe"
    $sc.Arguments        = "/c `"$SCRIPT_DIR\run.bat`""
    $sc.WorkingDirectory = $SCRIPT_DIR
    $sc.Description      = "UE5 AI Assistant"
    $sc.WindowStyle      = 1
    $sc.Save()
    OK "Desktop shortcut created"
} catch {
    WARN "Could not create shortcut (not critical)"
}

$envFile = "$SCRIPT_DIR\.env"
if ((Test-Path $envFile) -and (Get-Content $envFile -Raw) -notlike "*TESSERACT*") {
    Add-Content $envFile "`nTESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
}

Write-Host "
  ==========================================
    SETUP COMPLETE!

    To launch:
      - Double-click 'UE5 AI Assistant' on Desktop
      - OR run run.bat in the project folder

    Before starting:
      1. Open Unreal Engine 5
      2. Launch the assistant
      3. Type or speak your commands
  ==========================================
" -ForegroundColor Green

Log "=== Setup complete ==="

Write-Host "Launch assistant now? Press Enter or close window..." -ForegroundColor Yellow
$null = Read-Host

Set-Location $SCRIPT_DIR
& $python main.py