"""
AutonomousSetup — самостоятельно решает проблемы окружения:
- Ollama не запущен → запускает / устанавливает
- UE5 не открыт → ищет и запускает
- UE5 не установлен → скачивает Epic Launcher, ставит на D:, запускает UE5
"""
import os
import time
import subprocess
import threading
from pathlib import Path
from core.logger import logger

# ── Целевой диск установки ────────────────────────────────────
INSTALL_DRIVE = "D:\\"
EPIC_INSTALL_DIR = r"D:\Epic Games"

# ── Известные пути UE5 (D: первым) ───────────────────────────
UE5_SEARCH_PATHS = [
    r"D:\Epic Games",
    r"D:\Program Files\Epic Games",
    r"C:\Program Files\Epic Games",
    r"C:\Program Files (x86)\Epic Games",
    r"E:\Epic Games",
]

EPIC_LAUNCHER_PATHS = [
    r"D:\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    r"D:\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
    r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    r"C:\Program Files (x86)\Epic Games\Launcher\Engine\Binaries\Win64\EpicGamesLauncher.exe",
]


def find_ue5_executable() -> str | None:
    """Ищет UE5Editor.exe — сначала D:, потом все диски."""
    for base in UE5_SEARCH_PATHS:
        base_path = Path(base)
        if not base_path.exists():
            continue
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
    """Ищет Epic Games Launcher на D: и C:."""
    for path in EPIC_LAUNCHER_PATHS:
        if Path(path).exists():
            return path
    # Реестр
    try:
        import winreg
        for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                key = winreg.OpenKey(hive, r"SOFTWARE\EpicGames\Unreal Engine")
                path, _ = winreg.QueryValueEx(key, "INSTALLDIR")
                for sub in [
                    "Launcher\\Portal\\Binaries\\Win32\\EpicGamesLauncher.exe",
                    "Launcher\\Portal\\Binaries\\Win64\\EpicGamesLauncher.exe",
                ]:
                    launcher = Path(path).parent / sub
                    if launcher.exists():
                        return str(launcher)
            except Exception:
                pass
    except Exception:
        pass
    return None


def launch_ue5(status_callback) -> bool:
    """
    Полностью автономный запуск UE5:
    1. Найти UE5Editor.exe → запустить
    2. Найти Epic Launcher → открыть
    3. Скачать и установить Epic Launcher на D: → запустить
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
        status_callback("🚀 Открываю Epic Games Launcher...")
        subprocess.Popen([epic])
        status_callback(
            "📋 Epic Launcher открыт!\n"
            "Иди в 'Unreal Engine' → '+' → 'Install Engine'\n"
            "Выбери путь D:\\Epic Games и нажми Install.\n"
            "После установки скажи: 'запусти UE5'"
        )
        return True

    # 3. Качаем и ставим Epic Launcher на D: автоматически
    status_callback("📥 Epic Launcher не найден. Скачиваю и устанавливаю на D:...")
    threading.Thread(
        target=_install_epic_launcher_to_d,
        args=(status_callback,),
        daemon=True
    ).start()
    return False


def _install_epic_launcher_to_d(status_callback):
    """Скачивает и тихо устанавливает Epic Games Launcher на D:\\Epic Games."""
    import urllib.request

    def _log(msg):
        logger.info(msg)
        status_callback(msg)

    # Убедимся что D: существует
    if not Path("D:\\").exists():
        _log("⚠️ Диск D: не найден. Устанавливаю на C:")
        install_dir = r"C:\Epic Games"
    else:
        install_dir = EPIC_INSTALL_DIR

    Path(install_dir).mkdir(parents=True, exist_ok=True)

    temp = Path(os.environ.get("TEMP", "C:\\Windows\\Temp"))
    dest = temp / "EpicInstaller.msi"

    # Пробуем скачать через winget сначала (быстрее и надёжнее)
    _log("⚡ Пробую установить через winget...")
    try:
        result = subprocess.run(
            ["winget", "install", "--id", "EpicGames.EpicGamesLauncher",
             "--location", install_dir,
             "--silent", "--accept-package-agreements",
             "--accept-source-agreements"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            _log("✅ Epic Games Launcher установлен на " + install_dir)
            _launch_epic_after_install(install_dir, _log)
            return
        else:
            _log("winget не сработал, скачиваю MSI...")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _log("winget недоступен, скачиваю MSI...")

    # Скачиваем MSI
    url = "https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicInstaller-14.0.8.msi"
    try:
        _log("📥 Скачиваю Epic Games Launcher (~50MB)...")

        # Прогресс скачивания
        def _progress(count, block, total):
            if total > 0:
                pct = int(count * block * 100 / total)
                if pct % 20 == 0:
                    _log(f"📥 Скачиваю... {pct}%")

        urllib.request.urlretrieve(url, str(dest), reporthook=_progress)
        _log("📦 Устанавливаю Epic Games Launcher на " + install_dir + "...")

        # Тихая установка MSI с указанием пути
        result = subprocess.run(
            ["msiexec", "/i", str(dest),
             "/quiet", "/norestart",
             f"TARGETDIR={install_dir}",
             f"INSTALLDIR={install_dir}"],
            timeout=300
        )

        if result.returncode == 0:
            _log("✅ Epic Games Launcher установлен!")
        else:
            # Пробуем без /quiet (с UI)
            _log("📦 Запускаю установщик с UI...")
            subprocess.Popen(["msiexec", "/i", str(dest)])

        _launch_epic_after_install(install_dir, _log)

    except Exception as e:
        _log(
            f"❌ Ошибка установки: {e}\n"
            "Скачай вручную: https://www.unrealengine.com/download\n"
            "Установи на D:\\Epic Games"
        )


def _launch_epic_after_install(install_dir: str, log_fn):
    """Ждёт появления Epic Launcher и запускает его."""
    log_fn("⏳ Жду завершения установки Epic Launcher...")
    for _ in range(60):
        time.sleep(5)
        epic = find_epic_launcher()
        if epic:
            log_fn("🚀 Epic Launcher установлен! Запускаю...")
            subprocess.Popen([epic])
            log_fn(
                "📋 Epic Games Launcher запущен!\n"
                "1. Войди в аккаунт Epic Games\n"
                "2. Иди в 'Unreal Engine' → вкладка 'Library'\n"
                "3. Нажми '+' → выбери версию UE5\n"
                "4. Путь установки: D:\\Epic Games\\UE_5.x\n"
                "5. Нажми Install и дождись завершения\n"
                "6. Скажи мне: 'запусти UE5'"
            )
            return
    log_fn(
        "⚠️ Epic Launcher установился, но не найден.\n"
        "Запусти его из D:\\Epic Games вручную,\n"
        "установи UE5 и скажи: 'запусти UE5'"
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
        requests.get("http://localhost:11434", timeout=3)
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
        _log("❌ Ollama не найден. Скачиваю и устанавливаю...")
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

    # Сначала пробуем winget
    _log("⚡ Пробую winget install ollama...")
    try:
        result = subprocess.run(
            ["winget", "install", "--id", "Ollama.Ollama",
             "--silent", "--accept-package-agreements",
             "--accept-source-agreements"],
            capture_output=True, text=True, timeout=180
        )
        if result.returncode == 0:
            _log("✅ Ollama установлен через winget!")
            time.sleep(5)
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Скачиваем вручную
    dest = Path(os.environ.get("TEMP", "C:\\Windows\\Temp")) / "OllamaSetup.exe"
    url = "https://ollama.com/download/OllamaSetup.exe"
    try:
        _log("📥 Скачиваю Ollama (~60MB)...")
        urllib.request.urlretrieve(url, str(dest))
        _log("📦 Устанавливаю Ollama тихо...")
        subprocess.run([str(dest), "/S"], timeout=120)
        time.sleep(8)
        _log("✅ Ollama установлен! Перезапусти ассистента.")
    except Exception as e:
        _log(f"❌ Не удалось установить Ollama: {e}\nСкачай вручную: https://ollama.com/download")
