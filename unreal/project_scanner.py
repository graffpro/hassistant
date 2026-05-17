"""
UE5ProjectScanner — сканирует текущий UE5 проект и строит карту ресурсов.

Знает:
- Какие Blueprint, Material, Texture, Mesh есть в проекте
- Структуру папок Content Browser
- Имя и путь .uproject файла
- Последние изменённые ассеты

Используется оркестратором чтобы отвечать на вопросы
"что есть в проекте?" и при создании новых ассетов знать куда класть.
"""
import os
import glob
import json
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.logger import logger
from core.event_bus import bus, Events


@dataclass
class UE5Asset:
    name: str
    asset_type: str    # "Blueprint" | "Material" | "Texture" | "StaticMesh" | "Level" | "Other"
    path: str          # путь внутри Content Browser (/Game/...)
    file_path: str     # абсолютный путь на диске
    size_kb: float = 0
    modified: float = 0


@dataclass
class ProjectInfo:
    name: str = ""
    uproject_path: str = ""
    content_dir: str = ""
    engine_version: str = ""
    assets: list[UE5Asset] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)
    last_scanned: float = 0

    def asset_count(self) -> dict:
        counts: dict[str, int] = {}
        for a in self.assets:
            counts[a.asset_type] = counts.get(a.asset_type, 0) + 1
        return counts

    def summary(self) -> str:
        if not self.name:
            return "Проект не найден"
        counts = self.asset_count()
        lines = [f"📁 Проект: {self.name}"]
        for atype, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            icon = {"Blueprint": "🔵", "Material": "🟢", "Texture": "🖼",
                    "StaticMesh": "📦", "Level": "🗺", "Other": "📄"}.get(atype, "📄")
            lines.append(f"  {icon} {atype}: {cnt}")
        lines.append(f"  📂 Папок: {len(self.folders)}")
        return "\n".join(lines)

    def find_assets(self, query: str) -> list[UE5Asset]:
        q = query.lower()
        return [a for a in self.assets if q in a.name.lower() or q in a.path.lower()]


ASSET_TYPE_MAP = {
    ".uasset": "Other",      # будем уточнять по имени
    ".umap": "Level",
}

ASSET_NAME_HINTS = {
    "BP_": "Blueprint", "_BP": "Blueprint",
    "M_": "Material", "MI_": "Material",
    "T_": "Texture",
    "SM_": "StaticMesh", "SK_": "SkeletalMesh",
    "WBP_": "Widget", "ABP_": "AnimBlueprint",
}


class UE5ProjectScanner:
    """Сканирует UE5 проект и поддерживает актуальную карту ресурсов."""

    RESCAN_INTERVAL = 60.0   # пересканируем каждые 60 сек

    def __init__(self):
        self.project = ProjectInfo()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Запускает фоновое сканирование."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Project scanner started")

    def stop(self):
        self._running = False

    def scan_now(self) -> ProjectInfo:
        """Синхронное сканирование (для вызова по требованию)."""
        uproject = self._find_uproject()
        if uproject:
            self._scan_project(uproject)
        return self.project

    # ─────────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                uproject = self._find_uproject()
                if uproject:
                    self._scan_project(uproject)
            except Exception as e:
                logger.debug(f"Scanner error: {e}")
            time.sleep(self.RESCAN_INTERVAL)

    def _find_uproject(self) -> Optional[Path]:
        """Ищет .uproject файл на дисках C/D."""
        # Сначала ищем в типичных местах
        search_paths = [
            "C:/Users/*/Documents/Unreal Projects/**/*.uproject",
            "C:/Users/*/Desktop/**/*.uproject",
            "D:/Unreal Projects/**/*.uproject",
            "D:/Projects/**/*.uproject",
            "C:/Users/*/OneDrive/**/*.uproject",
        ]
        for pattern in search_paths:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                # Берём самый свежий
                latest = max(matches, key=lambda p: Path(p).stat().st_mtime)
                return Path(latest)

        # Широкий поиск — медленнее, только если первый не нашёл
        for drive in ["C", "D"]:
            for uproject in glob.glob(f"{drive}:/**/*.uproject", recursive=True):
                p = Path(uproject)
                # Пропускаем папки движка
                if "Engine" not in str(p) and "EpicGames" not in str(p):
                    return p
        return None

    def _scan_project(self, uproject_path: Path):
        """Сканирует проект по пути к .uproject файлу."""
        content_dir = uproject_path.parent / "Content"
        if not content_dir.exists():
            return

        self.project.name = uproject_path.stem
        self.project.uproject_path = str(uproject_path)
        self.project.content_dir = str(content_dir)

        # Читаем версию движка
        try:
            with open(uproject_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.project.engine_version = data.get("EngineAssociation", "")
        except Exception:
            pass

        # Сканируем ассеты
        assets = []
        folders = set()

        for ext in [".uasset", ".umap"]:
            for file_path in content_dir.rglob(f"*{ext}"):
                try:
                    rel = file_path.relative_to(content_dir)
                    game_path = "/Game/" + str(rel).replace("\\", "/")
                    asset_type = self._detect_type(file_path.stem, ext)
                    stat = file_path.stat()

                    assets.append(UE5Asset(
                        name=file_path.stem,
                        asset_type=asset_type,
                        path=game_path,
                        file_path=str(file_path),
                        size_kb=round(stat.st_size / 1024, 1),
                        modified=stat.st_mtime,
                    ))
                    folders.add("/Game/" + str(rel.parent).replace("\\", "/"))
                except Exception:
                    pass

        self.project.assets = assets
        self.project.folders = sorted(folders)
        self.project.last_scanned = time.time()

        logger.info(f"Project scanned: {self.project.name} "
                    f"({len(assets)} assets, {len(folders)} folders)")
        bus.emit(Events.STATUS_UPDATE, {
            "status": "idle",
            "message": f"📂 Проект '{self.project.name}' просканирован: {len(assets)} ассетов"
        })

    def _detect_type(self, name: str, ext: str) -> str:
        if ext == ".umap":
            return "Level"
        for prefix, atype in ASSET_NAME_HINTS.items():
            if name.startswith(prefix) or name.endswith(prefix.strip("_")):
                return atype
        return "Other"
