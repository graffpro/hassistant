"""
AutonomousSetup — самостоятельно решает проблемы окружения:
- Ollama не запущен → запускает
- UE5 не открыт → ищет и запускает
- UE5 не установлен → устанавливает Epic Games Launcher
"""
import os
import time
import subprocess
import threading
from pathlib import Path
from core.logger import logger


# ── Известные пути UE5 ───────────────────────────────────────
UE5_SEARCH_PATHS = [
    r"C:\Program Files\Epic Games",
    r"C:\Program Files (x86)\Epic Games",
    r"D:\Epic Games",
    r"D:\Program Files\Epic Games",
    r"E:\Epic Games",
]

EPIC_LAUNCHER_PATHS = [
    r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    r"C:\Program Files (x86)\Epic Games\Launcher\Engine\Binaries\Win64\EpicGamesLauncher.exe",
]


def find_ue5_executable() -> str | None:
    """Ищет UE5Editor.exe на всех дисках."""
    for base in UE5_SEARCH_PATHS:
        base_path = Path(base)
        if not base_path.exists():
            continue
        # Ищем рекурсивно UE5Editor.exe
        for exe in base_path.rglob("UE5Editor.exe"):
            logger.info(f"Found UE5: {exe}")
            return str(exe)

    # Расширенный поиск по всем дискам
    import string
    for drive in string.ascii_uppercase:
        drive_path = Path(f"{drive}:\\Epic Games")
        if drive_path.exists():
            for exe in drive_path.rglob("UE5Editor.exe"):
                logger.info(f"Found UE5: {exe}")
                return str(exe)
    return None


def find_epic_launcher() -> str | None:
    """Ищет Epic Games Launcher."""
    for path in EPIC_LAUNCHER_PATHS:
        if Path(path).exists():
            return path
    # Реестр
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\EpicGames\Unreal Engine")
        path, _ = winreg.QueryValueEx(key, "INSTALLDIR")
        launcher = Path(path).parent / "Launcher" / "Portal" / "Binaries" / "Win32" / "EpicGamesLauncher.exe"
        if launcher.exists():
            return str(launcher)
    except Exception:
        pass
    return None


def launch_ue5(status_callback) -> bool:
    """
    Пытается запустить UE5. Если нет — Epic Launcher. Если нет — скачивает.
    Возвращает True если запустил.
    """
    # 1. Ищем UE5Editor.exe
    status_callback("🔍 Ищу Unreal Engine 5...")
    ue5_exe = find_ue5_executable()

    if ue5_exe:
        status_callback(f"🚀 Запускаю UE5: {Path(ue5_exe).parent.parent.name}")
        subprocess.Popen([ue5_exe])
        status_callback("⏳ UE5 запускается, подожди 30-60 секунд...")
        return True

    # 2. Ищем Epic Games Launcher
    status_callback("🔍 UE5 не найден. Ищу Epic Games Launcher...")
    epic = find_epic_launcher()

    if epic:
        status_callback("🚀 Открываю Epic Games Launcher для установки UE5...")
        subprocess.Popen([epic])
        status_callback(
            "📋 Epic Launcher открыт!\n"
            "1. Перейди в 'Unreal Engine'\n"
            "2. Нажми '+' → 'Install Engine'\n"
            "3. Выбери версию UE5\n"
            "4. После установки скажи мне 'запусти UE5'"
        )
        return True

    # 3. Скачиваем Epic Games Launcher
    status_callback(
        "📥 Epic Games Launcher не найден.\n"
        "Скачиваю установщик..."
    )
    _download_epic_launcher(status_callback)
    return False


def _download_epic_launcher(status_callback):
    """Скачивает и запускает установщик Epic Games Launcher."""
    import urllib.request
    url = "https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicInstaller-14.0.8.msi"
    dest = Path(os.environ.get("TEMP", "C:\\Temp")) / "EpicInstaller.msi"

    try:
        status_callback("📥 Скачиваю Epic Games Launcher (~50MB)...")
        urllib.request.urlretrieve(url, str(dest))
        status_callback("📦 Запускаю установщик Epic Games Launcher...")
        subprocess.Popen(["msiexec", "/i", str(dest)])
        status_callback(
            "✅ Установщик запущен!\n"
            "После установки Epic Launcher:\n"
            "1. Войди в аккаунт\n"
            "2. Установи Unreal Engine 5\n"
            "3. Скажи мне 'запусти UE5'"
        )
    except Exception as e:
        status_callback(
            f"❌ Не удалось скачать автоматически.\n"
            f"Скачай вручную: https://www.unrealengine.com/download\n"
            f"Ошибка: {e}"
        )


def ensure_ollama_running(status_callback=None) -> bool:
    """
    Гарантирует что Ollama запущен. Возвращает True если успешно.
    """
    def _log(msg):
        logger.info(msg)
        if status_callback:
            status_callback(msg)

    # Проверяем
    try:
        import requests
        r = requests.get("http://localhost:11434", timeout=3)
        logger.info("Ollama is running")
        return True
    except Exception:
        pass

    _log("🔄 Запускаю Ollama...")

    # Пробуем запустить
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        # Ждём до 15 секунд
        import requests
        for i in range(15):
            time.sleep(1)
            try:
                requests.get("http://localhost:11434", timeout=2)
                _log("✅ Ollama запущен")
                return True
            except Exception:
                pass
        _log("⚠️ Ollama запускается медленно, подожди...")
        return False
    except FileNotFoundError:
        _log("❌ Ollama не найден. Скачиваю...")
        _install_ollama(status_callback)
        return False
    except Exception as e:
        _log(f"❌ Ошибка запуска Ollama: {e}")
        return False


def _install_ollama(status_callback=None):
    """Скачивает и устанавливает Ollama."""
    import urllib.request

    def _log(msg):
        logger.info(msg)
        if status_callback:
            status_callback(msg)

    dest = Path(os.environ.get("TEMP", "C:\\Temp")) / "OllamaSetup.exe"
    url = "https://ollama.com/download/OllamaSetup.exe"
    try:
        _log("📥 Скачиваю Ollama (~60MB)...")
        urllib.request.urlretrieve(url, str(dest))
        _log("📦 Устанавливаю Ollama...")
        subprocess.Popen([str(dest), "/S"])
        time.sleep(10)
        _log("✅ Ollama установлен! Перезапусти ассистента.")
    except Exception as e:
        _log(f"❌ Не удалось установить Ollama: {e}\nСкачай вручную: https://ollama.com/download")
