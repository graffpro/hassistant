"""
UE5 Output Log Monitor — читает лог UE5 в реальном времени,
детектит ошибки и автоматически ищет + применяет исправления.

Цикл:
  Мониторинг лога → Обнаружена ошибка → LLM анализирует →
  Ищет fix в памяти/Epic docs → Применяет → Проверяет → Запоминает
"""
import os
import re
import time
import threading
import glob
from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path

from core.logger import logger
from core.event_bus import bus, Events


# ─────────────────────────────────────────────────────────────
# ТИПЫ ОШИБОК
# ─────────────────────────────────────────────────────────────

@dataclass
class UE5Error:
    """Одна обнаруженная ошибка из лога."""
    error_type: str          # "blueprint_compile" | "shader" | "linker" | "crash" | "general"
    message: str             # Полный текст ошибки
    file: str = ""           # Файл где ошибка (если есть)
    line: int = 0            # Строка (если есть)
    asset: str = ""          # UE5 ассет (Blueprint/Material)
    severity: str = "error"  # "error" | "fatal" | "warning"
    raw_log: str = ""        # Оригинальная строка из лога
    timestamp: float = field(default_factory=time.time)

    def short(self) -> str:
        if self.asset:
            return f"[{self.error_type}] {self.asset}: {self.message[:80]}"
        return f"[{self.error_type}] {self.message[:100]}"


# ─────────────────────────────────────────────────────────────
# ПАТТЕРНЫ ОШИБОК UE5
# ─────────────────────────────────────────────────────────────

ERROR_PATTERNS = [
    # Blueprint compile errors
    (r"LogBlueprintCompiler: Error:?\s*(.+)",           "blueprint_compile", "error"),
    (r"LogCompile: Error:?\s*(.+)",                      "blueprint_compile", "error"),
    (r"Blueprint compile error.+?'([^']+)'.*?:\s*(.+)", "blueprint_compile", "error"),

    # Shader errors
    (r"LogShaderCompilers: Error:?\s*(.+)",              "shader",            "error"),
    (r"Failed to compile shader\s*(.+)",                 "shader",            "error"),

    # Linker / load errors
    (r"LogLinker: Error:?\s*(.+)",                       "linker",            "error"),
    (r"Can't find file for asset '([^']+)'",             "missing_asset",     "error"),
    (r"Failed to load '([^']+)'",                        "missing_asset",     "error"),

    # Python / script errors
    (r"LogPython: Error:?\s*(.+)",                       "script",            "error"),

    # Fatal / crash
    (r"Fatal error!(.+)",                                "crash",             "fatal"),
    (r"Assertion failed: (.+)",                          "crash",             "fatal"),
    (r"Access violation - code c0000005",                "crash",             "fatal"),
    (r"LowLevelFatalError\[(.+?)\]",                     "crash",             "fatal"),

    # General errors (последний — самый широкий)
    (r"LogTemp: Error:?\s*(.+)",                         "general",           "error"),
    (r"\bError\b:?\s*(.{10,})",                          "general",           "error"),
]

# Строки которые НЕ являются настоящими ошибками (ложные срабатывания)
FALSE_POSITIVE_FILTERS = [
    "no errors", "0 error", "errors found: 0",
    "errorlevel", "error_code = 0", "shader cache",
    "errorreporting", "errordomain",
]


# ─────────────────────────────────────────────────────────────
# МОНИТОР ЛОГА
# ─────────────────────────────────────────────────────────────

class UE5LogMonitor:
    """
    Следит за логом UE5, детектит ошибки, вызывает on_error callback.
    Работает в фоновом потоке — не блокирует UI.
    """

    # Возможные пути к логу UE5
    LOG_SEARCH_PATHS = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "UnrealEngine" / "*" / "Saved" / "Logs" / "UnrealEditor.log",
        Path("C:/Program Files/Epic Games/UE_5*/Engine/Programs/UnrealEditor/Saved/Logs/UnrealEditor.log"),
        Path("D:/Program Files/Epic Games/UE_5*/Engine/Programs/UnrealEditor/Saved/Logs/UnrealEditor.log"),
        Path("D:/Epic Games/UE_5*/Engine/Programs/UnrealEditor/Saved/Logs/UnrealEditor.log"),
    ]

    def __init__(self, on_error: Callable[[UE5Error], None], poll_interval: float = 2.0):
        self.on_error = on_error
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._log_path: Optional[Path] = None
        self._file_pos: int = 0
        self._seen_errors: set[str] = set()   # дедупликация
        self._last_error_time: float = 0.0
        self._error_cooldown: float = 5.0     # не спамим одинаковыми ошибками

    def start(self):
        """Запускает мониторинг в фоновом потоке."""
        self._log_path = self._find_log_file()
        if not self._log_path:
            logger.warning("UE5 log file not found — will retry when UE5 starts")
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"Log monitor started (log: {self._log_path})")

    def stop(self):
        self._running = False

    def _find_log_file(self) -> Optional[Path]:
        """Ищет лог файл UE5 по известным путям."""
        for pattern in self.LOG_SEARCH_PATHS:
            matches = glob.glob(str(pattern))
            if matches:
                # Берём самый свежий файл
                latest = max(matches, key=lambda p: Path(p).stat().st_mtime)
                return Path(latest)

        # Ищем в папках проекта на дисках C/D
        for drive in ["C", "D"]:
            for project_log in glob.glob(f"{drive}:/**/Saved/Logs/UnrealEditor.log", recursive=True):
                return Path(project_log)

        return None

    def _loop(self):
        """Фоновый цикл: читаем новые строки лога каждые poll_interval секунд."""
        while self._running:
            try:
                # Переподключаемся если UE5 только что запустился
                if not self._log_path or not self._log_path.exists():
                    new_path = self._find_log_file()
                    if new_path:
                        self._log_path = new_path
                        self._file_pos = 0
                        logger.info(f"Log file found: {self._log_path}")

                if self._log_path and self._log_path.exists():
                    self._read_new_lines()

            except Exception as e:
                logger.debug(f"Log monitor loop error: {e}")

            time.sleep(self.poll_interval)

    def _read_new_lines(self):
        """Читает новые строки в конце лога."""
        try:
            size = self._log_path.stat().st_size
            if size < self._file_pos:
                # Лог перезаписан (UE5 перезапустился)
                self._file_pos = 0
                self._seen_errors.clear()

            if size <= self._file_pos:
                return

            with open(self._log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._file_pos)
                new_text = f.read()
                self._file_pos = f.tell()

            for line in new_text.splitlines():
                error = self._parse_line(line)
                if error:
                    self._dispatch_error(error)

        except Exception as e:
            logger.debug(f"Log read error: {e}")

    def _parse_line(self, line: str) -> Optional[UE5Error]:
        """Проверяет строку лога на ошибки."""
        line_lower = line.lower()

        # Фильтруем ложные срабатывания
        if any(fp in line_lower for fp in FALSE_POSITIVE_FILTERS):
            return None

        for pattern, error_type, severity in ERROR_PATTERNS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                message = m.group(1) if m.lastindex and m.lastindex >= 1 else line
                message = message.strip()

                # Извлекаем имя ассета если есть
                asset_match = re.search(r"'([^']+Blueprint[^']*|[^']+\.uasset)'", line)
                asset = asset_match.group(1) if asset_match else ""

                # Извлекаем файл/строку если есть
                file_match = re.search(r"\[(.+?):(\d+)\]", line)
                file_name = file_match.group(1) if file_match else ""
                line_num = int(file_match.group(2)) if file_match else 0

                return UE5Error(
                    error_type=error_type,
                    message=message[:200],
                    file=file_name,
                    line=line_num,
                    asset=asset,
                    severity=severity,
                    raw_log=line[:300],
                )

        return None

    def _dispatch_error(self, error: UE5Error):
        """Дедупликация + вызов callback."""
        key = f"{error.error_type}:{error.message[:60]}"
        now = time.time()

        if key in self._seen_errors and now - self._last_error_time < self._error_cooldown:
            return

        self._seen_errors.add(key)
        self._last_error_time = now
        logger.warning(f"UE5 error detected: {error.short()}")
        self.on_error(error)


# ─────────────────────────────────────────────────────────────
# АВТО-ФИКС МЕНЕДЖЕР
# ─────────────────────────────────────────────────────────────

class LogAutoFixer:
    """
    Получает ошибки от LogMonitor и автоматически их исправляет.

    Цикл:
      ошибка → анализ LLM → поиск fix в памяти/Epic docs → выполнение → проверка
    """

    def __init__(self, llm, memory, researcher, orchestrator):
        self.llm = llm
        self.memory = memory
        self.researcher = researcher
        self.orchestrator = orchestrator
        self._fix_queue: list[UE5Error] = []
        self._fixing = False
        self._lock = threading.Lock()

    def on_error(self, error: UE5Error):
        """Вызывается при каждой новой ошибке из лога."""
        with self._lock:
            self._fix_queue.append(error)

        # Эмитим в UI
        bus.emit(Events.STATUS_UPDATE, {
            "status": "error",
            "message": f"⚠️ Ошибка UE5: {error.short()}\n🔧 Ищу исправление...",
        })

        # Запускаем fix в фоне если не уже запущен
        if not self._fixing:
            threading.Thread(target=self._fix_loop, daemon=True).start()

    def _fix_loop(self):
        """Обрабатывает очередь ошибок."""
        self._fixing = True
        while True:
            with self._lock:
                if not self._fix_queue:
                    break
                error = self._fix_queue.pop(0)
            try:
                self._fix_error(error)
            except Exception as e:
                logger.error(f"AutoFixer error: {e}")
        self._fixing = False

    def _fix_error(self, error: UE5Error):
        """Главный метод исправления одной ошибки."""
        logger.info(f"Fixing: {error.short()}")

        # 1. Формируем задачу поиска
        task = self._error_to_fix_task(error)

        # 2. Ищем fix в памяти и Epic docs
        research = self.researcher.research(task, context=f"UE5 error: {error.message}")

        if not research or not research.ue5_steps:
            # Нет готового решения — спрашиваем LLM напрямую
            fix_steps = self._ask_llm_for_fix(error)
        else:
            fix_steps = research.ue5_steps

        if not fix_steps:
            bus.emit(Events.STATUS_UPDATE, {
                "status": "idle",
                "message": (f"❌ Не нашёл автоматического исправления для:\n{error.message[:120]}\n"
                            f"Проверь Output Log в UE5 для деталей."),
            })
            return

        # 3. Применяем fix
        bus.emit(Events.STATUS_UPDATE, {
            "status": "executing",
            "message": f"🔧 Применяю исправление ({len(fix_steps)} шагов)...",
        })

        from brain.task_planner import ActionStep, ActionPlan
        from brain.intent_parser import Intent

        steps = [
            ActionStep(
                step_id=i + 1,
                action_type=s.get("action_type", "click"),
                target=s.get("target", ""),
                value=s.get("value"),
                description=s.get("description", ""),
                timeout_ms=s.get("timeout_ms", 5000),
            )
            for i, s in enumerate(fix_steps)
        ]

        intent = Intent(raw_text=task, action="fix", object_type="error")
        plan = ActionPlan(intent=intent, steps=steps, name=f"Fix: {error.error_type}")
        result = self.orchestrator._execute_plan(plan, intent)

        # 4. Докладываем
        if result.success:
            bus.emit(Events.STATUS_UPDATE, {
                "status": "idle",
                "message": f"✅ Исправлено! ({error.error_type})\n{error.message[:80]}",
            })
            # Сохраняем fix в память чтобы в следующий раз применить мгновенно
            self.memory.save_workflow(intent, plan,
                                      [{"step": s, "success": True} for s in steps])
        else:
            bus.emit(Events.STATUS_UPDATE, {
                "status": "idle",
                "message": (f"⚠️ Попытался исправить, но не уверен в результате.\n"
                            f"Ошибка: {error.message[:100]}"),
            })

    def _error_to_fix_task(self, error: UE5Error) -> str:
        """Конвертирует ошибку в поисковый запрос для fix."""
        templates = {
            "blueprint_compile": f"Fix Blueprint compile error in Unreal Engine 5: {error.message}",
            "shader":            f"Fix shader compile error UE5: {error.message}",
            "missing_asset":     f"Fix missing asset error UE5: {error.asset or error.message}",
            "linker":            f"Fix linker error Unreal Engine 5: {error.message}",
            "script":            f"Fix Python script error UE5: {error.message}",
            "crash":             f"Fix UE5 crash: {error.message}",
            "general":           f"Fix Unreal Engine 5 error: {error.message}",
        }
        return templates.get(error.error_type, f"Fix UE5 error: {error.message}")

    def _ask_llm_for_fix(self, error: UE5Error) -> list[dict]:
        """Спрашивает LLM как исправить ошибку."""
        system = """Ты эксперт по Unreal Engine 5.
Пользователь получил ошибку. Дай конкретные шаги для исправления в редакторе UE5.

Верни JSON:
{
  "steps": [
    {"action_type": "click|shortcut|menu|type", "target": "UI элемент UE5", "value": null, "description": "описание"}
  ]
}

Если ошибку нельзя исправить кликами — верни пустой список steps."""

        prompt = (
            f"Тип ошибки: {error.error_type}\n"
            f"Сообщение: {error.message}\n"
            f"Файл: {error.file or 'неизвестен'}\n"
            f"Ассет: {error.asset or 'неизвестен'}"
        )

        try:
            import json
            resp = self.llm.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ])
            content = resp.content if hasattr(resp, "content") else str(resp)
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return data.get("steps", [])
        except Exception as e:
            logger.error(f"LLM fix error: {e}")
        return []
