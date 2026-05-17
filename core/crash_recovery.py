"""
CrashRecovery — детектирует краш UE5 и автоматически восстанавливается.

Что делает:
  1. Следит что UE5 процесс живой
  2. При крэше — сохраняет контекст (что делали)
  3. Перезапускает UE5
  4. Загружает последний проект
  5. Продолжает с того места где остановились
  6. Сохраняет краш-репорт в память для избежания в будущем
"""
import time
import threading
import subprocess
from pathlib import Path
from typing import Optional

from core.logger import logger
from core.event_bus import bus, Events


class CrashRecovery:
    """Мониторит UE5 процесс и восстанавливается после краша."""

    CHECK_INTERVAL  = 5.0     # проверяем каждые 5 сек
    RESTART_DELAY   = 10.0    # ждём 10 сек перед перезапуском
    MAX_RESTARTS    = 3       # максимум 3 авто-рестарта подряд

    def __init__(self, ui_detector, scanner, memory, orchestrator):
        self.ui_detector  = ui_detector
        self.scanner      = scanner
        self.memory       = memory
        self.orchestrator = orchestrator

        self._running           = False
        self._thread: Optional[threading.Thread] = None
        self._ue5_was_open      = False
        self._restart_count     = 0
        self._last_restart      = 0.0
        self._last_task: str    = ""   # последняя задача — возобновим после рестарта
        self._crash_count       = 0    # всего крашей в сессии
        self._enabled           = True

        # Слушаем команды — запоминаем что делали
        bus.subscribe(Events.USER_MESSAGE, self._on_user_message)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Crash recovery monitor started")

    def stop(self):
        self._running = False

    # ─────────────────────────────────────────────────────────

    def _on_user_message(self, text: str):
        """Запоминаем последнюю команду пользователя."""
        self._last_task = text

    def _loop(self):
        """Фоновый цикл мониторинга."""
        while self._running:
            try:
                if self._enabled:
                    self._check_ue5()
            except Exception as e:
                logger.debug(f"Crash monitor error: {e}")
            time.sleep(self.CHECK_INTERVAL)

    def _check_ue5(self):
        """Проверяет состояние UE5 процесса."""
        is_open = self.ui_detector.is_ue5_open()

        if is_open:
            self._ue5_was_open = True
            self._restart_count = 0  # сбрасываем счётчик рестартов при успешной работе
            return

        # UE5 закрылся
        if not self._ue5_was_open:
            return  # Никогда и не был открыт — ок

        # UE5 был открыт и теперь закрылся — это краш или ручное закрытие?
        if self._is_crash():
            self._handle_crash()
        else:
            # Пользователь сам закрыл
            self._ue5_was_open = False
            logger.info("UE5 closed by user")

    def _is_crash(self) -> bool:
        """Определяет это краш или пользователь сам закрыл UE5."""
        # Проверяем наличие crash репорта
        crash_dirs = [
            Path.home() / "AppData/Local/UnrealEngine/*/Saved/Crashes",
            Path("C:/Users") / "*" / "AppData/Local/UnrealEngine/*/Saved/Crashes",
        ]
        import glob
        for pattern in crash_dirs:
            crashes = glob.glob(str(pattern), recursive=True)
            if crashes:
                latest_crash_dir = max(crashes, key=lambda p: Path(p).stat().st_mtime
                                       if Path(p).exists() else 0, default=None)
                if latest_crash_dir:
                    crash_path = Path(latest_crash_dir)
                    if crash_path.exists():
                        # Краш был в последние 30 сек?
                        mtime = crash_path.stat().st_mtime
                        if time.time() - mtime < 30:
                            return True

        # Проверяем лог на Fatal error
        if self.scanner and self.scanner.project.uproject_path:
            log_path = (Path(self.scanner.project.uproject_path).parent /
                        "Saved/Logs/UnrealEditor.log")
            if log_path.exists():
                try:
                    # Читаем последние 50 строк
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    last_lines = content[-3000:]
                    if any(kw in last_lines for kw in
                           ["Fatal error!", "Assertion failed", "LowLevelFatalError",
                            "Access violation"]):
                        return True
                except Exception:
                    pass
        return False

    def _handle_crash(self):
        """Обрабатывает краш UE5."""
        self._crash_count += 1
        self._ue5_was_open = False
        now = time.time()

        logger.warning(f"UE5 crash detected! (total crashes: {self._crash_count})")

        # Сбрасываем счётчик если с последнего рестарта прошло много времени
        if now - self._last_restart > 300:
            self._restart_count = 0

        # Уведомляем пользователя
        bus.emit(Events.STATUS_UPDATE, {
            "status": "error",
            "message": (
                f"💥 UE5 упал (краш #{self._crash_count})!\n"
                f"{'🔄 Перезапускаю автоматически...' if self._restart_count < self.MAX_RESTARTS else '⚠️ Слишком много крашей подряд — перезапусти вручную.'}"
            ),
        })

        # Сохраняем контекст краша в память
        self._save_crash_context()

        if self._restart_count >= self.MAX_RESTARTS:
            logger.error("Too many restarts — giving up auto-recovery")
            return

        # Ждём и перезапускаем
        time.sleep(self.RESTART_DELAY)
        self._restart_ue5()

    def _restart_ue5(self):
        """Перезапускает UE5 и загружает последний проект."""
        from core.autonomous_setup import launch_ue5

        self._restart_count += 1
        self._last_restart = time.time()

        bus.emit(Events.STATUS_UPDATE, {
            "status": "thinking",
            "message": f"🔄 Перезапускаю UE5 (попытка {self._restart_count})...",
        })

        # Запускаем UE5
        result = launch_ue5(lambda m: logger.info(f"[restart] {m}"))

        if result == "launched":
            # Ждём пока загрузится
            for _ in range(24):   # до 2 минут
                time.sleep(5)
                if self.ui_detector.is_ue5_open():
                    self._ue5_was_open = True
                    self._on_ue5_recovered()
                    return
            bus.emit(Events.STATUS_UPDATE, {
                "status": "error",
                "message": "⚠️ UE5 не загрузился за 2 минуты. Попробуй запустить вручную.",
            })
        else:
            bus.emit(Events.STATUS_UPDATE, {
                "status": "idle",
                "message": f"🚀 Epic Launcher открыт. Открой проект вручную после входа.",
            })

    def _on_ue5_recovered(self):
        """UE5 успешно перезапустился — продолжаем работу."""
        msg = "✅ UE5 восстановлен после краша!"
        if self._last_task:
            msg += f"\n💡 Последняя задача: '{self._last_task}'\nПовторить?"
        bus.emit(Events.STATUS_UPDATE, {"status": "idle", "message": msg})
        logger.info("UE5 recovered after crash")

    def _save_crash_context(self):
        """Сохраняет контекст краша в память для будущего анализа."""
        try:
            if hasattr(self.memory, "record_failure"):
                from brain.intent_parser import Intent
                intent = Intent(
                    raw_text=self._last_task or "unknown",
                    action="crash",
                    object_type="ue5",
                )
                self.memory.record_failure(intent, "UE5 crash detected")
        except Exception as e:
            logger.debug(f"Save crash context error: {e}")
