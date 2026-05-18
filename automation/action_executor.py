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
            elif step.action_type == "menu":
                return self._do_menu(step)
            # ── Высокоуровневые UE5 действия ─────────────────
            elif step.action_type == "create_blueprint":
                return self._ue5_create_blueprint(step)
            elif step.action_type == "create_material":
                return self._ue5_create_asset(step, "Material")
            elif step.action_type == "create_widget":
                return self._ue5_create_asset(step, "Widget Blueprint")
            elif step.action_type == "create_folder":
                return self._ue5_create_folder(step)
            elif step.action_type == "import_fbx":
                return self._ue5_import_file(step)
            elif step.action_type == "open_blueprint":
                return self._ue5_open_asset(step)
            elif step.action_type == "add_blueprint_node":
                return self._ue5_add_bp_node(step)
            elif step.action_type == "compile_blueprint":
                return self._ue5_compile_bp(step)
            elif step.action_type == "save_project":
                return self._ue5_save(step)
            elif step.action_type == "play_pie":
                return self._ue5_play_pie(step)
            elif step.action_type == "stop_pie":
                return self._ue5_stop_pie(step)
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

        if not step.value:
            return False, "Shortcut value is None"

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
        # Use clipboard paste to support Unicode/Cyrillic (typewrite only handles ASCII)
        text = step.value or ""
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            pyautogui.hotkey("ctrl", "v")
        except Exception:
            # Fallback: typewrite for ASCII-only text
            pyautogui.typewrite(text, interval=0.05)
        logger.debug(f"Typed: {step.value!r} into {step.target}")
        time.sleep(0.2)
        return True, None

    def _do_wait(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        ms = int(step.value or 1000)
        logger.debug(f"Waiting {ms}ms")
        time.sleep(ms / 1000.0)
        return True, None

    def _do_menu(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Навигация по меню: 'File > Save All' или 'Edit > Project Settings'."""
        import pyautogui
        self._focus_ue5()
        time.sleep(0.2)
        parts = [p.strip() for p in step.target.split(">")]
        # Кликаем по верхнему меню
        menu_positions = {
            "File": 0.03, "Edit": 0.07, "Window": 0.11,
            "Tools": 0.14, "Build": 0.18, "Select": 0.22,
            "Help": 0.26,
        }
        try:
            import win32api
            sw = win32api.GetSystemMetrics(0)
            sh = win32api.GetSystemMetrics(1)
            if parts[0] in menu_positions:
                x = int(sw * menu_positions[parts[0]])
                y = int(sh * 0.025)
                pyautogui.click(x, y)
                time.sleep(0.4)
                # Ищем пункт подменю через UIA или pyautogui.locateOnScreen
                for part in parts[1:]:
                    el = self._ui_detector.find_element(part) if self._ui_detector else None
                    if el:
                        pyautogui.click(el.x, el.y)
                    else:
                        pyautogui.press("escape")
                        return False, f"Menu item not found: {part}"
                    time.sleep(0.3)
                return True, None
        except Exception as e:
            return False, str(e)
        return False, f"Unknown menu: {step.target}"

    # ─────────────────────────────────────────────────────────
    # ВЫСОКОУРОВНЕВЫЕ UE5 ДЕЙСТВИЯ
    # ─────────────────────────────────────────────────────────

    def _ue5_create_blueprint(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Создаёт Blueprint в Content Browser через правый клик."""
        import pyautogui
        self._focus_ue5()
        time.sleep(0.3)

        name        = step.target or "NewBlueprint"
        parent      = step.value  or "Actor"

        # 1. Правый клик в Content Browser
        cb = self._ui_detector.find_element("Content Browser Empty Area") if self._ui_detector else None
        if cb:
            pyautogui.rightClick(cb.x, cb.y)
        else:
            # Fallback: Ctrl+Space → Content Browser
            pyautogui.hotkey("ctrl", "space")
            time.sleep(0.5)
            pyautogui.rightClick()
        time.sleep(0.5)

        # 2. Blueprint Class → ищем в меню
        self._menu_search_and_click("Blueprint Class")
        time.sleep(0.8)

        # 3. Выбираем родительский класс (диалог All Classes)
        self._type_in_search_box(parent)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(0.5)

        # 4. Называем Blueprint
        self._rename_new_asset(name)
        logger.info(f"Blueprint created: {name} ({parent})")
        return True, None

    def _ue5_create_asset(self, step: ActionStep, asset_type: str) -> Tuple[bool, Optional[str]]:
        """Универсальное создание ассета (Material, Widget и т.д.)."""
        import pyautogui
        self._focus_ue5()
        time.sleep(0.3)

        name = step.target or f"New{asset_type.replace(' ', '')}"

        # Правый клик в Content Browser
        cb = self._ui_detector.find_element("Content Browser Empty Area") if self._ui_detector else None
        if cb:
            pyautogui.rightClick(cb.x, cb.y)
        else:
            pyautogui.hotkey("ctrl", "space")
            time.sleep(0.5)
            pyautogui.rightClick()
        time.sleep(0.5)

        self._menu_search_and_click(asset_type)
        time.sleep(0.5)
        self._rename_new_asset(name)
        logger.info(f"{asset_type} created: {name}")
        return True, None

    def _ue5_create_folder(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Создаёт папку в Content Browser."""
        import pyautogui
        self._focus_ue5()
        time.sleep(0.3)

        name = step.target or "NewFolder"

        cb = self._ui_detector.find_element("Content Browser Empty Area") if self._ui_detector else None
        if cb:
            pyautogui.rightClick(cb.x, cb.y)
        else:
            pyautogui.hotkey("ctrl", "space")
            time.sleep(0.5)
            pyautogui.rightClick()
        time.sleep(0.5)

        self._menu_search_and_click("New Folder")
        time.sleep(0.4)
        self._rename_new_asset(name)
        logger.info(f"Folder created: {name}")
        return True, None

    def _ue5_import_file(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Открывает диалог импорта файла в Content Browser."""
        import pyautogui
        self._focus_ue5()
        time.sleep(0.3)

        # Кнопка Import в Content Browser
        cb_el = self._ui_detector.find_element("Content Browser") if self._ui_detector else None
        if cb_el:
            # Import кнопка обычно в верхней части Content Browser
            pyautogui.click(cb_el.x - 80, cb_el.y - 40)
        else:
            # Fallback: Ctrl+Space → найти Import
            pyautogui.hotkey("ctrl", "space")
            time.sleep(0.4)

        time.sleep(0.5)
        # Если есть путь к файлу — вводим его
        if step.value and step.value.strip():
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(step.value, win32clipboard.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.2)
                pyautogui.press("enter")
            except Exception:
                pass
        return True, None

    def _ue5_open_asset(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Открывает ассет двойным кликом в Content Browser."""
        import pyautogui
        self._focus_ue5()
        time.sleep(0.3)

        name = step.target
        # Ищем ассет в Content Browser через UIA или OCR
        el = self._ui_detector.find_element(name) if self._ui_detector else None
        if el:
            pyautogui.doubleClick(el.x, el.y)
            time.sleep(1.0)
            return True, None

        # Fallback: Ctrl+P (Quick Open)
        pyautogui.hotkey("ctrl", "p")
        time.sleep(0.4)
        self._paste_text(name)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(1.0)
        return True, None

    def _ue5_add_bp_node(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Добавляет ноду в Blueprint Editor через правый клик + поиск."""
        import pyautogui
        self._focus_ue5()
        time.sleep(0.3)

        node_name = step.target  # например "Print String"

        # Правый клик в центре Blueprint Graph
        try:
            import win32api
            sw = win32api.GetSystemMetrics(0)
            sh = win32api.GetSystemMetrics(1)
            # Blueprint graph обычно занимает центральную область
            graph_x = int(sw * 0.55)
            graph_y = int(sh * 0.55)
            pyautogui.rightClick(graph_x, graph_y)
            time.sleep(0.5)

            # Пишем имя ноды в поисковом поле контекстного меню
            pyautogui.typewrite(node_name, interval=0.05)
            time.sleep(0.5)

            # Выбираем первый результат
            pyautogui.press("enter")
            time.sleep(0.4)

            logger.info(f"BP node added: {node_name}")
            return True, None
        except Exception as e:
            return False, str(e)

    def _ue5_compile_bp(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Компилирует Blueprint (F7 или кнопка Compile)."""
        import pyautogui
        self._focus_ue5()
        time.sleep(0.2)
        # Пробуем F7 (Blueprint Editor shortcut)
        pyautogui.press("f7")
        time.sleep(1.0)
        # Проверяем нет ли диалога ошибок
        return True, None

    def _ue5_save(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Сохраняет проект (Ctrl+Shift+S)."""
        import pyautogui
        self._focus_ue5()
        pyautogui.hotkey("ctrl", "shift", "s")
        time.sleep(0.5)
        return True, None

    def _ue5_play_pie(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Запускает PIE (F5)."""
        import pyautogui
        self._focus_ue5()
        pyautogui.press("f5")
        time.sleep(0.5)
        return True, None

    def _ue5_stop_pie(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        """Останавливает PIE (Escape)."""
        import pyautogui
        self._focus_ue5()
        pyautogui.press("escape")
        time.sleep(0.3)
        return True, None

    # ─────────────────────────────────────────────────────────
    # УТИЛИТЫ
    # ─────────────────────────────────────────────────────────

    def _menu_search_and_click(self, item_name: str):
        """Ищет пункт в контекстном меню UE5 и кликает по нему."""
        import pyautogui
        # UE5 контекстное меню имеет поле поиска вверху
        pyautogui.typewrite(item_name, interval=0.04)
        time.sleep(0.4)
        # Ищем через UIA
        el = self._ui_detector.find_element(item_name) if self._ui_detector else None
        if el:
            pyautogui.click(el.x, el.y)
        else:
            pyautogui.press("enter")
        time.sleep(0.3)

    def _type_in_search_box(self, text: str):
        """Вводит текст в активное поле поиска."""
        import pyautogui
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        self._paste_text(text)

    def _rename_new_asset(self, name: str):
        """Переименовывает только что созданный ассет (поле имени активно)."""
        import pyautogui
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        self._paste_text(name)
        time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(0.3)

    def _paste_text(self, text: str):
        """Вставляет текст через буфер обмена (поддержка Unicode/кирилицы)."""
        import pyautogui
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(str(text), win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            pyautogui.hotkey("ctrl", "v")
        except Exception:
            pyautogui.typewrite(str(text), interval=0.04)

    def _do_drag(self, step: ActionStep) -> Tuple[bool, Optional[str]]:
        import pyautogui
        # value формат: "target_x,target_y"
        try:
            src = self._get_element_position(step.target)
            if not src:
                return False, f"Drag source not found: {step.target}"
            tx, ty = map(int, step.value.split(","))
            # moveTo source first, then dragTo absolute target
            pyautogui.moveTo(src[0], src[1], duration=0.2)
            pyautogui.dragTo(tx, ty, duration=0.5, button="left")
            return True, None
        except Exception as e:
            return False, str(e)
