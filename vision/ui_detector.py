"""
UIDetector — определяет элементы интерфейса UE5 на скриншоте.
Использует Windows UI Automation + OCR + CV для надёжного поиска.
"""
import re
from typing import Optional
from dataclasses import dataclass

from core.logger import logger


@dataclass
class UIElement:
    """Найденный элемент интерфейса."""
    semantic_name: str       # "Content Browser", "Blueprint Name Input"
    x: int                   # центр X
    y: int                   # центр Y
    width: int
    height: int
    confidence: float
    source: str              # "uia" | "ocr" | "template"


class UIDetector:
    """
    Определяет UI элементы UE5 тремя методами:
    1. Windows UI Automation (самый надёжный)
    2. OCR (Tesseract) — чтение текста
    3. Template matching (OpenCV) — резервный
    """

    def __init__(self):
        self._uia_available = self._check_uia()
        self._ocr_available = self._check_ocr()
        self._ue5_hwnd: Optional[int] = None

    def _check_uia(self) -> bool:
        try:
            import comtypes.client
            return True
        except ImportError:
            logger.warning("comtypes not available — UIA disabled")
            return False

    def _check_ocr(self) -> bool:
        try:
            import pytesseract
            return True
        except ImportError:
            logger.warning("pytesseract not available — OCR disabled")
            return False

    def find_ue5_window(self) -> Optional[int]:
        """Находит HWND окна Unreal Engine 5."""
        try:
            import win32gui
            def callback(hwnd, result):
                title = win32gui.GetWindowText(hwnd)
                if "Unreal Editor" in title or "Unreal Engine" in title:
                    result.append(hwnd)
            result = []
            win32gui.EnumWindows(callback, result)
            if result:
                self._ue5_hwnd = result[0]
                logger.info(f"UE5 window found: hwnd={self._ue5_hwnd}")
                bus_emit = True
                return self._ue5_hwnd
        except Exception as e:
            logger.error(f"Window search error: {e}")
        return None

    def find_element(self, semantic_name: str, screenshot=None) -> Optional[UIElement]:
        """
        Находит элемент по семантическому имени.
        Пробует UIA → OCR → template matching.
        """
        # 1. Windows UI Automation
        if self._uia_available:
            el = self._find_via_uia(semantic_name)
            if el:
                return el

        # 2. OCR поиск по тексту
        if self._ocr_available and screenshot is not None:
            el = self._find_via_ocr(semantic_name, screenshot)
            if el:
                return el

        # 3. Координаты по известным позициям UE5
        el = self._find_via_known_positions(semantic_name)
        if el:
            return el

        logger.warning(f"Element not found: {semantic_name}")
        return None

    def _find_via_uia(self, semantic_name: str) -> Optional[UIElement]:
        """Поиск через Windows UI Automation."""
        try:
            import comtypes.client
            from comtypes.gen import UIAutomationClient as uia

            automation = comtypes.client.CreateObject(
                "{ff48dba4-60ef-4201-aa87-54103eef594e}",
                interface=uia.IUIAutomation
            )

            # Маппинг семантических имён в UIA условия поиска
            search_terms = {
                "Content Browser": ["Content Browser", "Content"],
                "Blueprint Name Input": ["Name", "Asset Name"],
                "Output Log": ["Output Log"],
                "World Outliner": ["World Outliner", "Outliner"],
                "Details Panel": ["Details"],
                "Active Dialog OK Button": ["OK", "Okay", "Accept"],
                "Active Dialog Cancel Button": ["Cancel", "Close"],
            }

            terms = search_terms.get(semantic_name, [semantic_name.split(" > ")[-1]])

            root = automation.GetRootElement()
            condition_factory = automation

            for term in terms:
                try:
                    cond = automation.CreatePropertyCondition(
                        uia.UIA_NamePropertyId,
                        term
                    )
                    el = root.FindFirst(uia.TreeScope_Descendants, cond)
                    if el:
                        rect = el.CurrentBoundingRectangle
                        cx = (rect.left + rect.right) // 2
                        cy = (rect.top + rect.bottom) // 2
                        return UIElement(
                            semantic_name=semantic_name,
                            x=cx, y=cy,
                            width=rect.right - rect.left,
                            height=rect.bottom - rect.top,
                            confidence=0.95,
                            source="uia"
                        )
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"UIA search failed for {semantic_name}: {e}")
        return None

    def _find_via_ocr(self, semantic_name: str, screenshot) -> Optional[UIElement]:
        """Поиск текста через OCR на скриншоте."""
        try:
            import pytesseract
            import cv2

            img = screenshot.image
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

            search_text = semantic_name.split(" > ")[-1].lower()

            for i, text in enumerate(data["text"]):
                if text and search_text in text.lower() and int(data["conf"][i]) > 60:
                    x = data["left"][i] + data["width"][i] // 2
                    y = data["top"][i] + data["height"][i] // 2
                    return UIElement(
                        semantic_name=semantic_name,
                        x=x, y=y,
                        width=data["width"][i],
                        height=data["height"][i],
                        confidence=0.75,
                        source="ocr"
                    )
        except Exception as e:
            logger.debug(f"OCR search failed: {e}")
        return None

    def _find_via_known_positions(self, semantic_name: str) -> Optional[UIElement]:
        """
        Fallback: известные позиции UE5 UI элементов.
        Относительные координаты (процент от размера экрана).
        """
        import win32api
        sw = win32api.GetSystemMetrics(0)
        sh = win32api.GetSystemMetrics(1)

        # Типичное расположение UE5 панелей (Full HD базис)
        positions = {
            "Content Browser":              (sw * 0.25, sh * 0.75),
            "Content Browser Empty Area":   (sw * 0.35, sh * 0.65),
            "World Outliner":               (sw * 0.88, sh * 0.30),
            "Details Panel":                (sw * 0.88, sh * 0.65),
            "Output Log":                   (sw * 0.50, sh * 0.88),
            "Toolbar Play Button":          (sw * 0.50, sh * 0.04),
            "Active Dialog OK Button":      (sw * 0.52, sh * 0.56),
            "Active Dialog Cancel Button":  (sw * 0.48, sh * 0.56),
        }

        if semantic_name in positions:
            x, y = positions[semantic_name]
            return UIElement(
                semantic_name=semantic_name,
                x=int(x), y=int(y),
                width=100, height=30,
                confidence=0.5,
                source="known_position"
            )
        return None

    def is_ue5_open(self) -> bool:
        """Проверяет, запущен ли UE5."""
        return self.find_ue5_window() is not None
