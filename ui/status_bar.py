"""
StatusBar — живая полоса статуса ассистента.
Показывает: thinking / executing / idle / error
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor


STATUS_STYLES = {
    "idle":      {"color": "#6EE7B7", "icon": "●", "bg": "rgba(6,78,59,0.3)"},
    "thinking":  {"color": "#FCD34D", "icon": "◌", "bg": "rgba(120,53,15,0.3)"},
    "planning":  {"color": "#93C5FD", "icon": "◎", "bg": "rgba(30,58,138,0.3)"},
    "executing": {"color": "#A78BFA", "icon": "◉", "bg": "rgba(76,29,149,0.3)"},
    "error":     {"color": "#FCA5A5", "icon": "✕", "bg": "rgba(127,29,29,0.3)"},
    "learning":  {"color": "#6EE7B7", "icon": "★", "bg": "rgba(6,78,59,0.3)"},
}


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self._current_status = "idle"
        self._blink = False
        self._setup_ui()
        self._blink_timer = QTimer()
        self._blink_timer.timeout.connect(self._do_blink)

    def _setup_ui(self):
        self.setStyleSheet("background: rgba(6,78,59,0.3); border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._dot)

        self._label = QLabel("Готов к работе")
        self._label.setStyleSheet("font-size: 12px; background: transparent;")
        layout.addWidget(self._label)
        layout.addStretch()

        self._update_style("idle")

    def set_status(self, status: str, message: str = ""):
        self._current_status = status
        s = STATUS_STYLES.get(status, STATUS_STYLES["idle"])
        self._update_style(status)
        self._label.setText(message or status.capitalize())

        # Blink dot for active states
        if status in ("thinking", "executing", "planning"):
            self._blink_timer.start(500)
        else:
            self._blink_timer.stop()
            self._dot.setText(s["icon"])

    def _update_style(self, status: str):
        s = STATUS_STYLES.get(status, STATUS_STYLES["idle"])
        self.setStyleSheet(f"background: {s['bg']}; border: none;")
        self._dot.setStyleSheet(f"color: {s['color']}; font-size: 14px; background: transparent;")
        self._label.setStyleSheet(f"color: {s['color']}; font-size: 12px; background: transparent;")
        self._dot.setText(s["icon"])

    def _do_blink(self):
        self._blink = not self._blink
        s = STATUS_STYLES.get(self._current_status, STATUS_STYLES["idle"])
        self._dot.setText(s["icon"] if self._blink else " ")
