"""
ActionExecutor — выполняет шаги плана в UE5.
Семантический: сначала ищет элемент, потом действует.
"""
import time
from typing import Optional, Tuple

from brain.task_planner import ActionStep
from core.logger import logger


class ActionExecutor:
    def __init__(self):
        self._ui_detector = None  # Инжектируется при необходимости
        self._available = self._check_deps()

    def _check_deps(self) -> bool:
        try:
            import pyautogui
            import win32api
            return True
        except ImportError as e:
            logger.warning(f"Automation deps missing: {e}")
            return False

    def set_ui_detector(self, detector):
        self._ui_detector = detector

    def execute(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Выполняет один шаг. Возвращает (success, error)."""
        logger.info(f"Executing step {step.step_id}: {step.description}")

        try:
            if step.action_type == "shortcut":
                return self._do_shortcut(step)
            elif step.action_type == "click":
                return self._do_click(step)
            elif step.action_type == "right_click":
                return self._do_right_click(step)
            elif step.action_type == "double_click":
                return self._do_double_click(step)
            elif step.action_type == "type":
                return self._do_type(step)
            elif step.action_type == "wait":
                return self._do_wait(step)
            elif step.action_type == "drag":
                return self._do_drag(step)
            else:
                logger.warning(f"Unknown action_type: {step.action_type}")
                return False, f"Unknown action: {step.action_type}"
        except Exception as e:
            logger.error(f"Execute error on step {step.step_id}: {e}")
            return False, str(e)

    def execute_fallback(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Резервный метод если основной не сработал."""
        if step.fallback:
            fallback_step = ActionStep(
                step_id=step.step_id,
                action_type=step.fallback.get("action_type", step.action_type),
                target=step.fallback.get("target", step.target),
                value=step.fallback.get("value", step.value),
                description=f"[fallback] {step.description}",
            )
            logger.info(f"Trying fallback for step {step.step_id}")
            return self.execute(fallback_step)
        return False, "No fallback available"

    def _get_element_position(self, target: str) -> Optional[Tuple[int, int]]:
        """Получает координаты элемента через UIDetector."""
        if self._ui_detector:
            el = self._ui_detector.find_element(target)
            if el:
                return el.x, el.y
        return None

    def _focus_ue5(self):
        """Переключает фокус на окно UE5."""
        try:
            import win32gui, win32con
            def callback(hwnd, _):
                title = win32gui.GetWindowText(hwnd)
                if "Unreal Editor" in title or "Unreal Engine" in title:
                    win32gui.SetForegroundWindow(hwnd)
                    return False
            win32gui.EnumWindows(callback, None)
            time.sleep(0.15)
        except Exception as e:
            logger.debug(f"Focus UE5 error: {e}")

    def _do_shortcut(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        import pyautogui
        self._focus_ue5()
        time.sleep(0.1)

        keys = step.value.replace(" ", "").split("+")
        key_map = {
            "Ctrl": "ctrl", "Shift": "shift", "Alt": "alt",
            "Enter": "enter", "Return": "enter", "F5": "f5",
            "F7": "f7", "Escape": "esc", "Esc": "esc",
            "Delete": "delete", "Tab": "tab",
        }
        mapped = [key_map.get(k, k.lower()) for k in keys]

        if len(mapped) == 1:
            pyautogui.press(mapped[0])
        else:
            pyautogui.hotkey(*mapped)

        logger.debug(f"Shortcut: {step.value}")
        time.sleep(0.3)
        return True, None

    def _do_click(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        import pyautogui
        pos = self._get_element_position(step.target)
        if not pos:
            return False, f"Element not found: {step.target}"

        self._focus_ue5()
        pyautogui.moveTo(pos[0], pos[1], duration=0.2)
        pyautogui.click(pos[0], pos[1])
        logger.debug(f"Click: {step.target} at {pos}")
        time.sleep(0.3)
        return True, None

    def _do_right_click(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        import pyautogui
        pos = self._get_element_position(step.target)
        if not pos:
            return False, f"Element not found: {step.target}"

        self._focus_ue5()
        pyautogui.moveTo(pos[0], pos[1], duration=0.2)
        pyautogui.rightClick(pos[0], pos[1])
        logger.debug(f"Right click: {step.target} at {pos}")
        time.sleep(0.4)
        return True, None

    def _do_double_click(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        import pyautogui
        pos = self._get_element_position(step.target)
        if not pos:
            return False, f"Element not found: {step.target}"

        self._focus_ue5()
        pyautogui.doubleClick(pos[0], pos[1])
        time.sleep(0.3)
        return True, None

    def _do_type(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        import pyautogui
        if step.target and step.target != "Global":
            pos = self._get_element_position(step.target)
            if pos:
                pyautogui.click(pos[0], pos[1])
                time.sleep(0.2)

        # Очищаем поле перед вводом
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.typewrite(step.value or "", interval=0.05)
        logger.debug(f"Typed: {step.value!r} into {step.target}")
        time.sleep(0.2)
        return True, None

    def _do_wait(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        ms = int(step.value or 1000)
        logger.debug(f"Waiting {ms}ms")
        time.sleep(ms / 1000.0)
        return True, None

    def _do_drag(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        import pyautogui
        # value формат: "target_x,target_y"
        try:
            src = self._get_element_position(step.target)
            if not src:
                return False, f"Drag source not found: {step.target}"
            tx, ty = map(int, step.value.split(","))
            pyautogui.drag(tx - src[0], ty - src[1], duration=0.5, button="left")
            return True, None
        except Exception as e:
            return False, str(e)
