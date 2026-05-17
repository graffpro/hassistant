"""
WorkflowRecorder — записывает действия пользователя и строит автоматизируемый workflow.

Как работает:
  1. Пользователь говорит/пишет "начни запись"
  2. Бот следит за мышью и клавиатурой в UE5
  3. Пользователь выполняет действия
  4. "Стоп запись" → бот анализирует через LLM → строит workflow → сохраняет в память

При следующем похожем запросе — workflow выполняется автоматически.
"""
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable

from core.logger import logger
from core.event_bus import bus, Events


@dataclass
class RecordedAction:
    """Одно записанное действие пользователя."""
    action_type: str     # "click" | "right_click" | "double_click" | "shortcut" | "type"
    target_pos: tuple    # (x, y) на экране
    value: str = ""      # напечатанный текст или комбинация клавиш
    timestamp: float = field(default_factory=time.time)
    ui_element: str = "" # что это за элемент (определяется через UI Automation)
    description: str = ""


class WorkflowRecorder:
    """
    Записывает действия пользователя в UE5 и превращает их в переиспользуемый workflow.
    """

    def __init__(self, llm, memory, ui_detector, screen_capture):
        self.llm = llm
        self.memory = memory
        self.ui_detector = ui_detector
        self.screen_capture = screen_capture

        self._recording = False
        self._actions: list[RecordedAction] = []
        self._workflow_name: str = ""
        self._mouse_listener = None
        self._kb_listener = None
        self._lock = threading.Lock()
        self._last_type_time: float = 0
        self._type_buffer: str = ""

    # ─────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЙ API
    # ─────────────────────────────────────────────────────────

    def start_recording(self, workflow_name: str = "") -> str:
        """Начинает запись действий пользователя."""
        if self._recording:
            return "⚠️ Запись уже идёт. Скажи 'стоп запись' чтобы закончить."

        self._recording = True
        self._actions = []
        self._workflow_name = workflow_name or f"workflow_{int(time.time())}"
        self._type_buffer = ""

        self._start_listeners()

        msg = (f"🔴 Запись начата: '{self._workflow_name}'\n"
               f"Выполняй действия в UE5. Скажи 'стоп запись' когда закончишь.")
        bus.emit(Events.STATUS_UPDATE, {"status": "thinking", "message": msg})
        logger.info(f"Recording started: {self._workflow_name}")
        return msg

    def stop_recording(self) -> str:
        """Останавливает запись и сохраняет workflow."""
        if not self._recording:
            return "⚠️ Запись не была запущена."

        self._recording = False
        self._stop_listeners()

        with self._lock:
            actions = list(self._actions)

        if not actions:
            return "⚠️ Не записано ни одного действия."

        bus.emit(Events.STATUS_UPDATE, {
            "status": "thinking",
            "message": f"🔄 Анализирую {len(actions)} записанных действий...",
        })

        # Анализируем и сохраняем в фоне
        threading.Thread(
            target=self._analyze_and_save,
            args=(actions,),
            daemon=True,
        ).start()

        return f"⏹ Запись остановлена. Записано {len(actions)} действий. Анализирую..."

    def is_recording(self) -> bool:
        return self._recording

    # ─────────────────────────────────────────────────────────
    # LISTENERS
    # ─────────────────────────────────────────────────────────

    def _start_listeners(self):
        """Запускает листенеры мыши и клавиатуры."""
        try:
            from pynput import mouse, keyboard

            def on_click(x, y, button, pressed):
                if not self._recording or not pressed:
                    return
                # Только если UE5 в фокусе
                if not self.ui_detector.is_ue5_open():
                    return
                action_type = "click"
                if str(button) == "Button.right":
                    action_type = "right_click"
                ui_el = self._get_ui_element(x, y)
                with self._lock:
                    self._actions.append(RecordedAction(
                        action_type=action_type,
                        target_pos=(x, y),
                        ui_element=ui_el,
                        description=f"{action_type} на {ui_el or f'({x},{y})'}",
                    ))
                logger.debug(f"Recorded: {action_type} @ ({x},{y}) [{ui_el}]")

            def on_double_click(x, y, button, pressed):
                if not self._recording or not pressed:
                    return
                if str(button) == "Button.left":
                    ui_el = self._get_ui_element(x, y)
                    with self._lock:
                        # Заменяем два одиночных клика на double_click
                        if (len(self._actions) >= 2 and
                                self._actions[-1].action_type == "click" and
                                self._actions[-2].action_type == "click"):
                            self._actions.pop()
                            self._actions.pop()
                        self._actions.append(RecordedAction(
                            action_type="double_click",
                            target_pos=(x, y),
                            ui_element=ui_el,
                            description=f"Двойной клик на {ui_el or f'({x},{y})'}",
                        ))

            def on_key(key, pressed):
                if not self._recording or not pressed:
                    return
                if not self.ui_detector.is_ue5_open():
                    return
                try:
                    char = key.char
                    if char:
                        self._type_buffer += char
                        self._last_type_time = time.time()
                        return
                except AttributeError:
                    pass
                # Специальные клавиши — флашим буфер и добавляем shortcut
                self._flush_type_buffer()
                key_str = self._key_to_str(key)
                if key_str:
                    with self._lock:
                        self._actions.append(RecordedAction(
                            action_type="shortcut",
                            target_pos=(0, 0),
                            value=key_str,
                            description=f"Нажата клавиша {key_str}",
                        ))

            self._mouse_listener = mouse.Listener(on_click=on_click)
            self._kb_listener = keyboard.Listener(on_press=lambda k: on_key(k, True))
            self._mouse_listener.start()
            self._kb_listener.start()

            # Фоновый поток для флаша буфера набора текста
            threading.Thread(target=self._type_flush_loop, daemon=True).start()

        except ImportError:
            logger.warning("pynput not installed — workflow recording unavailable")

    def _stop_listeners(self):
        """Останавливает листенеры."""
        self._flush_type_buffer()
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        if self._kb_listener:
            try:
                self._kb_listener.stop()
            except Exception:
                pass

    def _type_flush_loop(self):
        """Флашит буфер набора текста после паузы."""
        while self._recording:
            if self._type_buffer and time.time() - self._last_type_time > 0.8:
                self._flush_type_buffer()
            time.sleep(0.1)

    def _flush_type_buffer(self):
        """Сохраняет накопленный текст как одно действие."""
        if not self._type_buffer:
            return
        text = self._type_buffer
        self._type_buffer = ""
        with self._lock:
            self._actions.append(RecordedAction(
                action_type="type",
                target_pos=(0, 0),
                value=text,
                description=f"Напечатано: '{text}'",
            ))

    # ─────────────────────────────────────────────────────────
    # АНАЛИЗ И СОХРАНЕНИЕ
    # ─────────────────────────────────────────────────────────

    def _analyze_and_save(self, actions: list[RecordedAction]):
        """LLM анализирует записанные действия → строит переиспользуемый workflow."""
        try:
            # Формируем описание действий для LLM
            actions_text = "\n".join(
                f"{i+1}. {a.description}" + (f" (значение: '{a.value}')" if a.value else "")
                for i, a in enumerate(actions)
            )

            import json, re
            system = """Ты эксперт по Unreal Engine 5 и автоматизации.
Пользователь записал свои действия в UE5. Проанализируй их и:
1. Дай название workflow (что он делает)
2. Опиши в 1 предложении что делает этот workflow
3. Конвертируй в переиспользуемые шаги для автоматизации

Верни JSON:
{
  "name": "Название workflow",
  "description": "Что делает этот workflow",
  "triggers": ["фраза1", "фраза2"],  // как пользователь может его запустить
  "steps": [
    {"action_type": "click|double_click|right_click|shortcut|type|menu",
     "target": "UI элемент UE5 или описание",
     "value": null,
     "description": "Описание шага"}
  ]
}"""

            prompt = f"Записанные действия пользователя:\n{actions_text}"

            resp = self.llm.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ])
            content = resp.content if hasattr(resp, "content") else str(resp)
            m = re.search(r'\{.*\}', content, re.DOTALL)

            if not m:
                raise ValueError("LLM не вернул JSON")

            data = json.loads(m.group())
            name        = data.get("name", self._workflow_name)
            description = data.get("description", "")
            triggers    = data.get("triggers", [])
            steps       = data.get("steps", [])

            if not steps:
                bus.emit(Events.STATUS_UPDATE, {
                    "status": "idle",
                    "message": "⚠️ Не удалось построить workflow из записи.",
                })
                return

            # Сохраняем в память через стандартный механизм
            from brain.intent_parser import Intent
            from brain.task_planner import ActionStep, ActionPlan

            intent = Intent(
                raw_text=name,
                action="recorded_workflow",
                object_type="workflow",
            )
            plan_steps = [
                ActionStep(
                    step_id=i + 1,
                    action_type=s.get("action_type", "click"),
                    target=s.get("target", ""),
                    value=s.get("value"),
                    description=s.get("description", ""),
                    timeout_ms=3000,
                )
                for i, s in enumerate(steps)
            ]
            plan = ActionPlan(intent=intent, steps=plan_steps, name=name)
            self.memory.save_workflow(
                intent, plan,
                [{"step": s, "success": True} for s in plan_steps],
            )

            # Также сохраняем триггеры для быстрого поиска
            if hasattr(self.memory, "vectors") and triggers:
                for trigger in triggers:
                    self.memory.vectors.add(
                        text=trigger,
                        metadata={"action": "recorded_workflow", "workflow_name": name},
                    )

            msg = (f"✅ Workflow сохранён: '{name}'\n"
                   f"📝 {description}\n"
                   f"💡 Запустить: {' / '.join(triggers[:2]) if triggers else name}")
            logger.info(f"Workflow recorded: {name} ({len(plan_steps)} steps)")
            bus.emit(Events.STATUS_UPDATE, {"status": "idle", "message": msg})

        except Exception as e:
            logger.error(f"Workflow analysis error: {e}")
            bus.emit(Events.STATUS_UPDATE, {
                "status": "idle",
                "message": f"⚠️ Ошибка анализа записи: {e}",
            })

    # ─────────────────────────────────────────────────────────
    # ВСПОМОГАТЕЛЬНЫЕ
    # ─────────────────────────────────────────────────────────

    def _get_ui_element(self, x: int, y: int) -> str:
        """Определяет UI элемент UE5 под курсором через UI Automation."""
        try:
            import uiautomation as auto
            ctrl = auto.ControlFromPoint(x, y)
            if ctrl:
                name = ctrl.Name or ctrl.ClassName or ""
                return name[:50]
        except Exception:
            pass
        return ""

    def _key_to_str(self, key) -> str:
        """Конвертирует pynput key в читаемую строку."""
        special = {
            "Key.ctrl_l": "ctrl", "Key.ctrl_r": "ctrl",
            "Key.shift": "shift", "Key.shift_r": "shift",
            "Key.alt_l": "alt", "Key.alt_r": "alt",
            "Key.delete": "delete", "Key.backspace": "backspace",
            "Key.enter": "enter", "Key.tab": "tab",
            "Key.esc": "escape", "Key.space": "space",
            "Key.f1": "F1", "Key.f2": "F2", "Key.f3": "F3",
            "Key.f4": "F4", "Key.f5": "F5", "Key.f6": "F6",
            "Key.f7": "F7", "Key.f8": "F8",
        }
        key_str = str(key)
        return special.get(key_str, key_str.replace("Key.", ""))
