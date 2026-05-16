"""
TrayManager — иконка в системном трее + контекстное меню.
"""
import sys
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QRadialGradient
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QObject

from core.logger import logger


def make_tray_icon(color: str = "#7C3AED") -> QIcon:
    """Генерирует иконку трея программно."""
    size = 64
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = size // 2 - 2

    grad = QRadialGradient(size // 2, size // 2, r)
    grad.setColorAt(0.0, QColor("#A855F7"))
    grad.setColorAt(1.0, QColor(color))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, r * 2, r * 2)
    p.end()

    return QIcon(px)


class TrayManager(QObject):
    show_main   = pyqtSignal()
    show_chat   = pyqtSignal()
    quit_app    = pyqtSignal()
    open_settings = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(make_tray_icon())
        self._tray.setToolTip("UE5 AI Assistant")
        self._build_menu()
        self._tray.activated.connect(self._on_activated)
        self._tray.show()
        logger.info("System tray icon created")

    def _build_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: #0F0C1E;
                color: #E2D9F3;
                border: 1px solid rgba(124,58,237,0.4);
                border-radius: 8px;
                padding: 4px;
                font-size: 13px;
            }
            QMenu::item { padding: 6px 20px 6px 12px; border-radius: 4px; }
            QMenu::item:selected { background: rgba(124,58,237,0.3); }
            QMenu::separator { background: rgba(124,58,237,0.2); height: 1px; margin: 4px 8px; }
        """)

        a_chat = menu.addAction("💬  Открыть чат")
        a_chat.triggered.connect(self.show_chat)

        a_main = menu.addAction("🖥️  Полное окно")
        a_main.triggered.connect(self.show_main)

        menu.addSeparator()

        a_settings = menu.addAction("⚙️  Настройки")
        a_settings.triggered.connect(self.open_settings)

        menu.addSeparator()

        a_quit = menu.addAction("✕  Выйти")
        a_quit.triggered.connect(self.quit_app)

        self._tray.setContextMenu(menu)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_chat.emit()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_main.emit()

    def set_state(self, state: str):
        colors = {
            "idle":      "#7C3AED",
            "thinking":  "#A855F7",
            "executing": "#4F46E5",
            "error":     "#DC2626",
            "learning":  "#059669",
        }
        self._tray.setIcon(make_tray_icon(colors.get(state, "#7C3AED")))

    def notify(self, title: str, message: str):
        """Показывает уведомление из трея."""
        self._tray.showMessage(title, message,
                               QSystemTrayIcon.MessageIcon.Information, 3000)
