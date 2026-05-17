"""
UE5GitIntegration — автоматический Git для UE5 проектов.

Умеет:
- Авто-коммит после выполнения задачи
- git status / log / diff
- Инициализация репозитория если нет
- Rollback к предыдущему коммиту
- Игнорирование тяжёлых папок (Binaries, Intermediate, Saved)

Команды:
  "сохрани в гит"            → commit с автоматическим сообщением
  "гит статус"               → покажи изменения
  "гит история"              → последние 10 коммитов
  "откати последнее"         → git revert HEAD
  "создай гит репозиторий"   → git init + .gitignore
"""
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Optional

from core.logger import logger
from core.event_bus import bus, Events


UE5_GITIGNORE = """# Unreal Engine
Binaries/
Build/
Intermediate/
Saved/
DerivedDataCache/
*.VC.db
*.opensdf
*.opendb
*.sdf
*.sln
*.suo
*.xcodeproj
*.xcworkspace

# OS
.DS_Store
Thumbs.db
desktop.ini

# IDE
.idea/
.vscode/
*.swp
"""


class UE5GitIntegration:
    """Git-менеджер для UE5 проекта."""

    def __init__(self, llm, scanner):
        self.llm = llm
        self.scanner = scanner
        self._git_path: Optional[Path] = None
        self._auto_commit = True          # авто-коммит после задач
        self._lock = threading.Lock()

    # ─────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЙ API
    # ─────────────────────────────────────────────────────────

    def setup(self) -> str:
        """Находит или инициализирует git репозиторий для текущего проекта."""
        project_dir = self._find_project_dir()
        if not project_dir:
            return "❌ UE5 проект не найден. Сначала открой проект."

        self._git_path = project_dir
        git_dir = project_dir / ".git"

        if not git_dir.exists():
            return self.init_repo()

        return f"✅ Git репозиторий найден: {project_dir.name}"

    def init_repo(self) -> str:
        """Инициализирует git репозиторий в папке проекта."""
        project_dir = self._find_project_dir()
        if not project_dir:
            return "❌ Проект не найден"

        self._git_path = project_dir

        # Создаём .gitignore
        gitignore = project_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(UE5_GITIGNORE, encoding="utf-8")

        # git init
        ok, out = self._git("init")
        if not ok:
            return f"❌ git init failed: {out}"

        # Первый коммит
        self._git("add", "-A")
        ok, out = self._git("commit", "-m", f"Initial commit: {project_dir.name}")

        msg = (f"✅ Git репозиторий создан: {project_dir.name}\n"
               f"📄 .gitignore настроен для UE5\n"
               f"💾 Первый коммит выполнен")
        logger.info(msg)
        bus.emit(Events.STATUS_UPDATE, {"status": "idle", "message": msg})
        return msg

    def commit(self, message: str = "") -> str:
        """Коммитит текущие изменения."""
        if not self._ensure_repo():
            return "❌ Git репозиторий не найден. Скажи 'создай гит репозиторий'."

        # Проверяем есть ли изменения
        ok, status = self._git("status", "--porcelain")
        if not status.strip():
            return "ℹ️ Нет изменений для коммита."

        # Автосообщение через LLM если не задано
        if not message:
            message = self._generate_commit_message(status)

        self._git("add", "-A")
        ok, out = self._git("commit", "-m", message)
        if ok:
            msg = f"✅ Коммит: {message}"
        else:
            msg = f"❌ Ошибка коммита: {out[:100]}"
        bus.emit(Events.STATUS_UPDATE, {"status": "idle", "message": msg})
        return msg

    def status(self) -> str:
        """Показывает статус репозитория."""
        if not self._ensure_repo():
            return "❌ Git репозиторий не инициализирован."

        ok, out = self._git("status", "--short")
        if not out.strip():
            return "✅ Нет изменений — всё чисто."

        lines = out.strip().splitlines()
        summary = []
        added = modified = deleted = 0
        for line in lines:
            if line.startswith("A"):  added += 1
            elif line.startswith("M"): modified += 1
            elif line.startswith("D"): deleted += 1

        msg = f"📊 Git статус:\n"
        if added:    msg += f"  ➕ Добавлено: {added}\n"
        if modified: msg += f"  ✏️ Изменено: {modified}\n"
        if deleted:  msg += f"  ➖ Удалено: {deleted}\n"
        msg += f"\nФайлы:\n" + "\n".join(f"  {l}" for l in lines[:10])
        if len(lines) > 10:
            msg += f"\n  ... и ещё {len(lines)-10}"
        return msg

    def log(self, count: int = 10) -> str:
        """Показывает историю коммитов."""
        if not self._ensure_repo():
            return "❌ Git репозиторий не инициализирован."

        ok, out = self._git("log", f"--oneline", f"-{count}")
        if not out.strip():
            return "📋 История коммитов пуста."

        lines = out.strip().splitlines()
        msg = f"📋 Последние {len(lines)} коммитов:\n"
        msg += "\n".join(f"  {l}" for l in lines)
        return msg

    def rollback(self) -> str:
        """Откатывает последний коммит (git revert HEAD)."""
        if not self._ensure_repo():
            return "❌ Git репозиторий не инициализирован."

        ok, out = self._git("revert", "HEAD", "--no-edit")
        if ok:
            msg = "↩️ Последний коммит откачен (revert HEAD)"
        else:
            # Если revert не работает — пробуем reset
            ok2, out2 = self._git("reset", "HEAD~1", "--soft")
            msg = "↩️ Откат выполнен (reset HEAD~1)" if ok2 else f"❌ Ошибка отката: {out}"
        bus.emit(Events.STATUS_UPDATE, {"status": "idle", "message": msg})
        return msg

    def auto_commit_after_task(self, task_description: str):
        """Вызывается оркестратором после успешного выполнения задачи."""
        if not self._auto_commit:
            return
        if not self._ensure_repo():
            return
        ok, status = self._git("status", "--porcelain")
        if not status.strip():
            return
        message = f"auto: {task_description[:60]}"
        threading.Thread(
            target=self.commit,
            args=(message,),
            daemon=True,
        ).start()

    # ─────────────────────────────────────────────────────────
    # ВНУТРЕННИЕ
    # ─────────────────────────────────────────────────────────

    def _ensure_repo(self) -> bool:
        if self._git_path and (self._git_path / ".git").exists():
            return True
        result = self.setup()
        return "✅" in result

    def _find_project_dir(self) -> Optional[Path]:
        if self.scanner and self.scanner.project.uproject_path:
            return Path(self.scanner.project.uproject_path).parent
        return None

    def _git(self, *args) -> tuple[bool, str]:
        """Выполняет git команду в папке проекта."""
        git_exe = self._find_git()
        if not git_exe:
            return False, "git not found"
        with self._lock:
            try:
                result = subprocess.run(
                    [git_exe] + list(args),
                    cwd=str(self._git_path),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding="utf-8",
                    errors="ignore",
                )
                output = result.stdout + result.stderr
                return result.returncode == 0, output
            except Exception as e:
                return False, str(e)

    @staticmethod
    def _find_git() -> Optional[str]:
        candidates = [
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files (x86)\Git\cmd\git.exe",
            "git",
        ]
        for c in candidates:
            if os.path.exists(c) or c == "git":
                return c
        return None

    def _generate_commit_message(self, git_status: str) -> str:
        """LLM генерирует осмысленное сообщение коммита."""
        try:
            resp = self.llm.chat([
                {"role": "system", "content":
                    "Напиши короткое сообщение git commit (до 60 символов) "
                    "описывающее изменения. Только сообщение, без кавычек."},
                {"role": "user", "content":
                    f"Изменения в UE5 проекте:\n{git_status[:500]}"},
            ])
            msg = resp.content if hasattr(resp, "content") else str(resp)
            return msg.strip()[:60] or "update UE5 project"
        except Exception:
            return "update UE5 project"
