"""
ScreenCapture — делает скриншоты экрана с нужным интервалом.
"""
import time
import threading
from dataclasses import dataclass
from typing import Optional
import numpy as np

from core.config import config
from core.event_bus import bus, Events
from core.logger import logger


@dataclass
class Screenshot:
    image: np.ndarray      # BGR numpy array
    timestamp: float
    width: int
    height: int


class ScreenCapture:
    def __init__(self):
        self._latest: Optional[Screenshot] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        try:
            import mss
            self._mss = mss
            self._available = True
        except ImportError:
            logger.warning("mss not installed — screen capture disabled")
            self._available = False

    def capture(self) -> Optional[Screenshot]:
        """Делает один скриншот и возвращает его."""
        if not self._available:
            return None
        try:
            import mss
            import cv2
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Основной монитор
                img = sct.grab(monitor)
                arr = np.frombuffer(img.rgb, dtype=np.uint8)
                arr = arr.reshape((img.height, img.width, 3))
                arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                shot = Screenshot(
                    image=arr,
                    timestamp=time.time(),
                    width=img.width,
                    height=img.height,
                )
                with self._lock:
                    self._latest = shot
                return shot
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return None

    def get_latest(self) -> Optional[Screenshot]:
        with self._lock:
            return self._latest

    def start_continuous(self):
        """Запускает фоновый поток скриншотов."""
        if self._running or not self._available:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Continuous screen capture started")

    def stop_continuous(self):
        self._running = False

    def _loop(self):
        interval = config.vision.capture_interval_ms / 1000.0
        while self._running:
            shot = self.capture()
            if shot:
                bus.emit(Events.SCREENSHOT_TAKEN, shot)
            time.sleep(interval)

    def capture_region(self, x: int, y: int, w: int, h: int) -> Optional[np.ndarray]:
        """Захват конкретной области экрана."""
        if not self._available:
            return None
        try:
            import mss
            import cv2
            with mss.mss() as sct:
                region = {"left": x, "top": y, "width": w, "height": h}
                img = sct.grab(region)
                arr = np.frombuffer(img.rgb, dtype=np.uint8)
                arr = arr.reshape((img.height, img.width, 3))
                return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error(f"Region capture error: {e}")
            return None
