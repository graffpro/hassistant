"""
AutoUpdater — обновляет Python-код ассистента без переустановки.

Архитектура разделена на два слоя:
  RUNTIME (Install.exe устанавливает один раз):
    Python, Ollama, pip-пакеты, Tesseract — НЕ меняются при обновлении

  CODE (обновляется автоматически):
    Все .py файлы проекта — скачиваются заново при новой версии

Источник обновлений: GitHub releases или локальная папка.
"""
import os
import sys
import json
import shutil
import hashlib
import zipfile
import tempfile
import threading
import subprocess
from pathlib import Path
from typing import Optional, Callable

from core.logger import logger

# ─────────────────────────────────────────────────────────────
# КОНФИГУРАЦИЯ
# ─────────────────────────────────────────────────────────────

VERSION_FILE  = Path(__file__).parent.parent / "version.json"
APP_DIR       = Path(__file__).parent.parent

# Источник обновлений — можно поменять на свой сервер / GitHub
UPDATE_SOURCES = [
    # GitHub releases (основной)
    "https://api.github.com/repos/graffpro/hassistant/releases/latest",
    # Локальная сеть (запасной)
    # "\\\\fileserver\\updates\\ue5_assistant",
]

CURRENT_VERSION = "0.1.0"


# ─────────────────────────────────────────────────────────────
# VERSION FILE
# ─────────────────────────────────────────────────────────────

def get_local_version() -> str:
    """Читает текущую версию из version.json."""
    try:
        if VERSION_FILE.exists():
            data = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
            return data.get("version", CURRENT_VERSION)
    except Exception:
        pass
    return CURRENT_VERSION


def save_local_version(version: str, notes: str = ""):
    """Сохраняет версию в version.json."""
    data = {"version": version, "notes": notes}
    VERSION_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────────────────────
# UPDATER
# ─────────────────────────────────────────────────────────────

class AutoUpdater:
    """
    Проверяет наличие обновлений и применяет их.
    Обновляет только .py файлы — runtime не трогает.
    """

    def __init__(self, on_status: Optional[Callable] = None,
                 on_update_available: Optional[Callable] = None):
        self._on_status = on_status or logger.info
        self._on_update_available = on_update_available
        self._current = get_local_version()

    def check_and_update(self, silent: bool = True) -> bool:
        """
        Проверяет обновления. Если есть — применяет.
        silent=True → не показывает сообщение если версия актуальна.
        Возвращает True если было обновление.
        """
        self._status("🔍 Проверяю обновления...")

        info = self._fetch_update_info()
        if not info:
            if not silent:
                self._status("✓ Нет соединения с сервером обновлений")
            return False

        latest = info.get("version", self._current)

        if not self._is_newer(latest, self._current):
            if not silent:
                self._status(f"✓ Версия актуальна: {self._current}")
            return False

        # Есть обновление
        notes = info.get("notes", "")
        self._status(f"🆕 Доступна версия {latest} (текущая: {self._current})")
        if notes:
            self._status(f"   Что нового: {notes}")

        if self._on_update_available:
            self._on_update_available(latest, notes)
            return False  # Пусть UI спросит пользователя

        return self._apply_update(info)

    def apply_update_background(self, info: dict):
        """Применяет обновление в фоновом потоке."""
        thread = threading.Thread(
            target=self._apply_update,
            args=(info,),
            daemon=True
        )
        thread.start()

    def _apply_update(self, info: dict) -> bool:
        """Скачивает и применяет обновление кода."""
        try:
            download_url = info.get("download_url", "")
            version = info.get("version", "")

            if not download_url:
                self._status("⚠ Нет ссылки на скачивание")
                return False

            self._status(f"📥 Скачиваю обновление {version}...")

            with tempfile.TemporaryDirectory() as tmp_dir:
                zip_path = Path(tmp_dir) / "update.zip"

                # Скачиваем
                import requests
                r = requests.get(download_url, stream=True, timeout=60)
                r.raise_for_status()

                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded / total * 100)
                            self._status(f"📥 Скачиваю... {pct}%")

                self._status("📦 Применяю обновление...")

                # Создаём резервную копию
                backup_dir = APP_DIR.parent / f"backup_{self._current}"
                self._backup_code(backup_dir)

                # Распаковываем
                self._apply_zip(zip_path, tmp_dir)
                self._status(f"✅ Обновлено до версии {version}")

                # Сохраняем новую версию
                save_local_version(version, info.get("notes", ""))
                self._current = version

                # Перезапускаем
                self._restart_app()
                return True

        except Exception as e:
            logger.exception(f"Update error: {e}")
            self._status(f"❌ Ошибка обновления: {e}")
            return False

    def _apply_zip(self, zip_path: Path, tmp_dir: str):
        """Распаковывает только .py файлы из архива."""
        with zipfile.ZipFile(zip_path, 'r') as zf:
            py_files = [f for f in zf.namelist() if f.endswith('.py')]
            total = len(py_files)

            for i, name in enumerate(py_files):
                # Убираем корневую папку из пути
                parts = Path(name).parts
                if len(parts) > 1:
                    rel_path = Path(*parts[1:])
                else:
                    rel_path = Path(name)

                target = APP_DIR / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)

                with zf.open(name) as src, open(target, 'wb') as dst:
                    dst.write(src.read())

                pct = int((i + 1) / total * 100)
                self._status(f"📝 Файлы: {pct}% ({i+1}/{total})")

    def _backup_code(self, backup_dir: Path):
        """Создаёт резервную копию текущих .py файлов."""
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            for py_file in APP_DIR.rglob("*.py"):
                rel = py_file.relative_to(APP_DIR)
                target = backup_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(py_file, target)
            logger.info(f"Backup created: {backup_dir}")
        except Exception as e:
            logger.warning(f"Backup failed: {e}")

    def _restart_app(self):
        """Перезапускает приложение с новым кодом."""
        self._status("🔄 Перезапуск...")
        import time
        time.sleep(1)

        python = sys.executable
        script = APP_DIR / "main.py"

        subprocess.Popen([python, str(script)],
                         cwd=str(APP_DIR),
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

        # Завершаем текущий процесс
        os._exit(0)

    def _fetch_update_info(self) -> Optional[dict]:
        """Получает информацию об обновлении с сервера."""
        import requests

        for source in UPDATE_SOURCES:
            try:
                if source.startswith("http"):
                    # GitHub API или HTTP сервер
                    r = requests.get(source, timeout=8,
                                     headers={"Accept": "application/vnd.github.v3+json"})
                    if r.ok:
                        data = r.json()

                        # GitHub releases формат
                        if "tag_name" in data:
                            version = data["tag_name"].lstrip("v")
                            notes   = data.get("body", "")
                            assets  = data.get("assets", [])
                            dl_url  = ""
                            for asset in assets:
                                if asset["name"].endswith(".zip"):
                                    dl_url = asset["browser_download_url"]
                                    break
                            return {"version": version, "notes": notes, "download_url": dl_url}

                        # Простой JSON формат: {"version": "0.2.0", "download_url": "..."}
                        if "version" in data:
                            return data

                else:
                    # Локальная папка / сетевой путь
                    ver_file = Path(source) / "version.json"
                    if ver_file.exists():
                        data = json.loads(ver_file.read_text(encoding="utf-8"))
                        data["download_url"] = str(Path(source) / f"update_{data['version']}.zip")
                        return data

            except Exception as e:
                logger.debug(f"Update source failed ({source}): {e}")
                continue

        return None

    def _is_newer(self, latest: str, current: str) -> bool:
        """Сравнивает версии (semver)."""
        try:
            def parse(v):
                return tuple(int(x) for x in v.strip("v").split("."))
            return parse(latest) > parse(current)
        except Exception:
            return False

    def _status(self, msg: str):
        logger.info(f"[Updater] {msg}")
        if callable(self._on_status):
            self._on_status(msg)


# ─────────────────────────────────────────────────────────────
# ЛОКАЛЬНОЕ ОБНОВЛЕНИЕ (разработка)
# ─────────────────────────────────────────────────────────────

class LocalUpdater:
    """
    Для разработки: синхронизирует код из локальной папки.
    Не нужно деплоить на GitHub — просто правишь файлы и они обновляются.
    """

    def __init__(self, source_dir: str, app_dir: Path = APP_DIR):
        self._source = Path(source_dir)
        self._app = app_dir

    def sync(self) -> int:
        """Копирует изменённые файлы. Возвращает количество обновлённых."""
        updated = 0
        if not self._source.exists():
            return 0

        for src_file in self._source.rglob("*.py"):
            rel = src_file.relative_to(self._source)
            dst_file = self._app / rel

            if not dst_file.exists() or self._file_changed(src_file, dst_file):
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                logger.info(f"Updated: {rel}")
                updated += 1

        return updated

    def _file_changed(self, src: Path, dst: Path) -> bool:
        def md5(path):
            return hashlib.md5(path.read_bytes()).hexdigest()
        return md5(src) != md5(dst)
