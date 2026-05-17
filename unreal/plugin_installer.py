"""
UE5PluginInstaller — автоматически находит и устанавливает UE5 плагины.

Источники:
  1. Fab Marketplace (fab.com) — официальный магазин
  2. GitHub — open-source плагины
  3. Локальные .uplugin файлы

Команды:
  "установи плагин Voxel"       → ищет и устанавливает
  "найди плагин для воксель"    → поиск без установки
  "список плагинов"             → установленные плагины
  "установи плагин из github X" → GitHub плагин
"""
import os
import re
import json
import shutil
import zipfile
import threading
import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import requests

from core.logger import logger
from core.event_bus import bus, Events


@dataclass
class PluginInfo:
    name: str
    description: str
    version: str = ""
    source: str = ""       # "fab" | "github" | "local"
    url: str = ""
    free: bool = True
    download_url: str = ""


class UE5PluginInstaller:
    """Устанавливает плагины в UE5 проект автоматически."""

    GITHUB_SEARCH = "https://api.github.com/search/repositories?q={query}+unreal+plugin&sort=stars"

    def __init__(self, llm, scanner):
        self.llm = llm
        self.scanner = scanner
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/vnd.github.v3+json",
        })

    # ─────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЙ API
    # ─────────────────────────────────────────────────────────

    def find_plugin(self, query: str) -> list[PluginInfo]:
        """Ищет плагины по запросу. Возвращает список найденных."""
        bus.emit(Events.STATUS_UPDATE, {
            "status": "thinking",
            "message": f"🔍 Ищу плагин: {query}...",
        })
        results = []
        results.extend(self._search_github(query))
        results.extend(self._search_known_plugins(query))
        return results[:5]

    def install_plugin(self, query: str) -> str:
        """Ищет и устанавливает плагин в текущий проект."""
        plugins = self.find_plugin(query)
        if not plugins:
            return f"❌ Плагин '{query}' не найден. Попробуй установить вручную с fab.com"

        plugin = plugins[0]
        bus.emit(Events.STATUS_UPDATE, {
            "status": "thinking",
            "message": f"📦 Найден: '{plugin.name}'\nУстанавливаю...",
        })

        if plugin.source == "github" and plugin.download_url:
            return self._install_from_github(plugin)
        elif plugin.source == "local":
            return self._install_local(plugin)
        else:
            return (f"ℹ️ Плагин '{plugin.name}' найден:\n"
                    f"🔗 {plugin.url}\n"
                    f"Этот плагин нужно скачать вручную с Fab Marketplace.\n"
                    f"Открыть: {plugin.url}")

    def list_installed(self) -> str:
        """Показывает установленные плагины."""
        project_dir = self._get_project_dir()
        if not project_dir:
            return "❌ Проект не найден"

        plugins_dir = project_dir / "Plugins"
        if not plugins_dir.exists():
            return "📦 Нет установленных плагинов в проекте."

        uplugins = list(plugins_dir.rglob("*.uplugin"))
        if not uplugins:
            return "📦 Папка Plugins пуста."

        lines = [f"📦 Установленные плагины ({len(uplugins)}):"]
        for p in uplugins[:15]:
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                ver = data.get("VersionName", "?")
                desc = data.get("Description", "")[:50]
                lines.append(f"  • {p.stem} v{ver} — {desc}")
            except Exception:
                lines.append(f"  • {p.stem}")

        return "\n".join(lines)

    def open_fab(self, query: str = "") -> str:
        """Открывает Fab Marketplace в браузере."""
        import webbrowser
        if query:
            url = f"https://www.fab.com/search?q={query.replace(' ', '+')}&category=plugins"
        else:
            url = "https://www.fab.com/category/plugins?compatible_with=unreal-engine"
        webbrowser.open(url)
        return f"🌐 Открыл Fab Marketplace: '{query}'"

    # ─────────────────────────────────────────────────────────
    # ПОИСК
    # ─────────────────────────────────────────────────────────

    def _search_github(self, query: str) -> list[PluginInfo]:
        """Ищет open-source плагины на GitHub."""
        try:
            url = self.GITHUB_SEARCH.format(query=query.replace(" ", "+"))
            resp = self._session.get(url, timeout=8)
            if not resp.ok:
                return []
            items = resp.json().get("items", [])[:5]
            plugins = []
            for item in items:
                name = item.get("name", "")
                if any(kw in name.lower() for kw in
                       ["plugin", "ue4", "ue5", "unreal"]):
                    plugins.append(PluginInfo(
                        name=name,
                        description=item.get("description", "")[:100],
                        source="github",
                        url=item.get("html_url", ""),
                        free=True,
                        download_url=self._get_github_zip_url(item),
                    ))
            return plugins
        except Exception as e:
            logger.debug(f"GitHub search error: {e}")
            return []

    def _get_github_zip_url(self, repo: dict) -> str:
        """Формирует URL для скачивания ZIP архива репозитория."""
        full_name = repo.get("full_name", "")
        default_branch = repo.get("default_branch", "main")
        if full_name:
            return f"https://github.com/{full_name}/archive/refs/heads/{default_branch}.zip"
        return ""

    def _search_known_plugins(self, query: str) -> list[PluginInfo]:
        """База известных популярных UE5 плагинов."""
        known = [
            PluginInfo("VoxelPlugin", "Voxel terrain и world generation",
                       source="github", free=True,
                       url="https://github.com/Phyronnaz/VoxelPlugin",
                       download_url="https://github.com/Phyronnaz/VoxelPlugin/archive/refs/heads/main.zip"),
            PluginInfo("JsonBlueprint", "Read/Write JSON from Blueprint",
                       source="github", free=True,
                       url="https://github.com/ufna/VaRest",
                       download_url="https://github.com/ufna/VaRest/archive/refs/heads/master.zip"),
            PluginInfo("RuntimeMeshComponent", "Dynamic meshes at runtime",
                       source="github", free=True,
                       url="https://github.com/TriAxis-Games/RuntimeMeshComponent",
                       download_url="https://github.com/TriAxis-Games/RuntimeMeshComponent/archive/refs/heads/master.zip"),
            PluginInfo("UINavigation", "Gamepad-friendly UI navigation",
                       source="github", free=True,
                       url="https://github.com/gantenpanter/UINavigation"),
            PluginInfo("Procedural Mesh", "Procedural mesh generation",
                       source="builtin", free=True,
                       url="", description="Встроен в UE5 — включи в Edit→Plugins→ProceduralMeshComponent"),
            PluginInfo("Paper2D", "2D sprites and tilemaps",
                       source="builtin", free=True,
                       url="", description="Встроен — Edit→Plugins→Paper2D"),
            PluginInfo("Chaos Vehicles", "Vehicle physics simulation",
                       source="builtin", free=True,
                       url="", description="Встроен — Edit→Plugins→ChaosVehicles"),
            PluginInfo("Water", "Water system (lakes, rivers, ocean)",
                       source="builtin", free=True,
                       url="", description="Встроен — Edit→Plugins→Water"),
            PluginInfo("Fab", "Marketplace integration",
                       source="fab", free=False,
                       url="https://www.fab.com/"),
        ]
        q = query.lower()
        return [p for p in known if q in p.name.lower() or q in p.description.lower()]

    # ─────────────────────────────────────────────────────────
    # УСТАНОВКА
    # ─────────────────────────────────────────────────────────

    def _install_from_github(self, plugin: PluginInfo) -> str:
        """Скачивает и устанавливает плагин с GitHub."""
        project_dir = self._get_project_dir()
        if not project_dir:
            return "❌ Проект не найден"

        plugins_dir = project_dir / "Plugins"
        plugins_dir.mkdir(exist_ok=True)

        try:
            bus.emit(Events.STATUS_UPDATE, {
                "status": "thinking",
                "message": f"⬇️ Скачиваю {plugin.name}...",
            })

            # Скачиваем ZIP
            resp = self._session.get(plugin.download_url, timeout=60, stream=True)
            if not resp.ok:
                return f"❌ Ошибка скачивания: {resp.status_code}"

            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                for chunk in resp.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                tmp_path = tmp.name

            # Распаковываем
            extract_dir = plugins_dir / plugin.name
            if extract_dir.exists():
                shutil.rmtree(extract_dir)

            with zipfile.ZipFile(tmp_path, "r") as z:
                z.extractall(plugins_dir)

            os.unlink(tmp_path)

            # Переименовываем если нужно (GitHub добавляет -main к имени)
            for item in plugins_dir.iterdir():
                if item.is_dir() and plugin.name.lower() in item.name.lower():
                    if item.name != plugin.name:
                        item.rename(plugins_dir / plugin.name)
                    break

            msg = (f"✅ Плагин '{plugin.name}' установлен!\n"
                   f"📂 {plugins_dir / plugin.name}\n"
                   f"⚡ Перезапусти UE5 чтобы плагин загрузился.")
            bus.emit(Events.STATUS_UPDATE, {"status": "idle", "message": msg})
            return msg

        except Exception as e:
            logger.error(f"Plugin install error: {e}")
            return f"❌ Ошибка установки: {e}"

    def _install_local(self, plugin: PluginInfo) -> str:
        """Устанавливает плагин из локального пути."""
        src = Path(plugin.url)
        if not src.exists():
            return f"❌ Файл не найден: {src}"

        project_dir = self._get_project_dir()
        if not project_dir:
            return "❌ Проект не найден"

        dest = project_dir / "Plugins" / src.stem
        try:
            if src.is_file() and src.suffix == ".zip":
                dest.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(src) as z:
                    z.extractall(dest)
            elif src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)

            msg = f"✅ Плагин установлен из {src.name}. Перезапусти UE5."
            bus.emit(Events.STATUS_UPDATE, {"status": "idle", "message": msg})
            return msg
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def _get_project_dir(self) -> Optional[Path]:
        if self.scanner and self.scanner.project.uproject_path:
            return Path(self.scanner.project.uproject_path).parent
        return None
