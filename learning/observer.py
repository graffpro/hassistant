"""
WorkflowObserver — пассивно наблюдает за действиями пользователя.
Записывает успешные workflows в память для будущего использования.
"""
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from core.logger import logger


@dataclass
class UserAction:
    """Одно действие пользователя."""
    action_type: str       # mouse_click | key_press | key_combo
    target_info: str       # window title или описание
    value: Optional[str]   # введённый текст или клавиша
    timestamp: float = field(default_factory=time.time)


class WorkflowObserver:
    """
    Пассивный наблюдатель — записывает действия пользователя.
    Сохраняет успешные workflows в MemoryManager.
    """

    def __init__(self, memory):
        self.memory = memory
        self._action_buffer: deque = deque(maxlen=200)
        self._observer_thread: Optional[threading.Thread] = None
        self._running = False
        self._keyboard = None
        self._mouse = None

    def start_observing(self):
        """Запускает пассивное наблюдение через pynput."""
        try:
            from pynput import mouse, keyboard

            def on_click(x, y, button, pressed):
                if pressed:
                    self._record_action(UserAction(
                        action_type="mouse_click",
                        target_info=f"screen({x},{y})",
                        value=str(button),
                    ))

            def on_key(key):
                try:
                    k = key.char if hasattr(key, 'char') else str(key)
                    self._record_action(UserAction(
                        action_type="key_press",
                        target_info="keyboard",
                        value=k,
                    ))
                except Exception:
                    pass

            self._mouse = mouse.Listener(on_click=on_click)
            self._keyboard = keyboard.Listener(on_press=on_key)
            self._mouse.daemon = True
            self._keyboard.daemon = True
            self._mouse.start()
            self._keyboard.start()
            self._running = True
            logger.info("WorkflowObserver: passive observation started")

        except ImportError:
            logger.warning("pynput not installed — passive observation disabled")

    def stop_observing(self):
        self._running = False
        try:
            if self._mouse:
                self._mouse.stop()
        except Exception as e:
            logger.debug(f"Mouse listener stop error: {e}")
        try:
            if self._keyboard:
                self._keyboard.stop()
        except Exception as e:
            logger.debug(f"Keyboard listener stop error: {e}")

    def _record_action(self, action: UserAction):
        self._action_buffer.append(action)

    def record_workflow(self, intent, plan, results: list):
        """
        Записывает успешно выполненный workflow в долгосрочную память.
        Вызывается Orchestrator после успешного выполнения.
        """
        if not results:
            return

        success_count = sum(1 for r in results if r.get("success"))
        if success_count == len(results):  # Все шаги успешны
            wf_id = self.memory.save_workflow(intent, plan, results)
            logger.info(f"Workflow recorded: {intent.action}/{intent.object_type} (id={wf_id})")
        else:
            failed = len(results) - success_count
            logger.warning(f"Workflow partially failed: {failed}/{len(results)} steps failed")
            self.memory.record_failure(
                intent=intent,
                error=f"{failed} steps failed",
                steps=[r.get("step") for r in results],
            )

    def get_recent_actions(self, count: int = 20) -> list[UserAction]:
        """Возвращает последние N действий пользователя."""
        return list(self._action_buffer)[-count:]

    def detect_repeated_pattern(self, min_repeats: int = 2) -> Optional[list[UserAction]]:
        """
        Ищет повторяющиеся последовательности действий.
        Если найдено — можно предложить автоматизацию.
        """
        actions = list(self._action_buffer)
        if len(actions) < 6:
            return None

        # Простой алгоритм: ищем повторяющийся блок
        n = len(actions)
        for seq_len in range(3, n // 2 + 1):
            for start in range(n - seq_len * 2 + 1):
                seq1 = actions[start:start + seq_len]
                seq2 = actions[start + seq_len:start + seq_len * 2]
                if self._sequences_match(seq1, seq2):
                    logger.info(f"Repeated pattern detected: {seq_len} steps × {min_repeats}")
                    return seq1
        return None

    def _sequences_match(self, s1: list, s2: list) -> bool:
        if len(s1) != len(s2):
            return False
        matches = sum(
            1 for a, b in zip(s1, s2)
            if a.action_type == b.action_type and a.value == b.value
        )
        return matches / len(s1) >= 0.8  # 80% совпадение
