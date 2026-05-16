"""
ChatWidget — панель чата с историей сообщений и полем ввода.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel,
    QHBoxLayout, QLineEdit, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QCursor, QKeyEvent


class MessageBubble(QFrame):
    """Одно сообщение в чате."""

    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(300)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if is_user:
            bubble.setStyleSheet("""
                QLabel {
                    background-color: #7C3AED;
                    color: #FFFFFF;
                    border-radius: 12px 12px 2px 12px;
                    padding: 8px 12px;
                    font-size: 13px;
                }
            """)
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            bubble.setStyleSheet("""
                QLabel {
                    background-color: rgba(255,255,255,0.08);
                    color: #E2D9F3;
                    border-radius: 12px 12px 12px 2px;
                    padding: 8px 12px;
                    font-size: 13px;
                    border: 1px solid rgba(124,58,237,0.2);
                }
            """)
            layout.addWidget(bubble)
            layout.addStretch()

        self.setStyleSheet("background: transparent; border: none;")


class TypingIndicator(QFrame):
    """Анимированный индикатор 'печатает...'"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        self._label = QLabel("● ● ●")
        self._label.setStyleSheet("""
            QLabel {
                background-color: rgba(255,255,255,0.08);
                color: #A78BFA;
                border-radius: 12px;
                padding: 8px 14px;
                font-size: 11px;
                border: 1px solid rgba(124,58,237,0.2);
            }
        """)
        layout.addWidget(self._label)
        layout.addStretch()
        self.setStyleSheet("background: transparent; border: none;")

        self._dots = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._animate)
        self._timer.start(400)

    def _animate(self):
        self._dots = (self._dots + 1) % 4
        self._label.setText("●" * self._dots + "○" * (3 - self._dots))


class ChatWidget(QWidget):
    message_sent = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._typing_indicator = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Message History ---
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.03);
                width: 4px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(124,58,237,0.5);
                border-radius: 2px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._messages_widget = QWidget()
        self._messages_widget.setStyleSheet("background: transparent;")
        self._messages_layout = QVBoxLayout(self._messages_widget)
        self._messages_layout.setContentsMargins(12, 12, 12, 12)
        self._messages_layout.setSpacing(4)
        self._messages_layout.addStretch()

        self._scroll.setWidget(self._messages_widget)
        self._scroll.setMinimumHeight(320)
        layout.addWidget(self._scroll)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(124,58,237,0.2); border: none; border-top: 1px solid rgba(124,58,237,0.2);")
        layout.addWidget(sep)

        # --- Input Row ---
        input_row = QWidget()
        input_row.setFixedHeight(50)
        input_row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(input_row)
        row_layout.setContentsMargins(12, 6, 12, 6)
        row_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Напиши что нужно сделать...")
        self._input.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,0.07);
                color: #E2D9F3;
                border: 1px solid rgba(124,58,237,0.35);
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(124,58,237,0.8);
                background: rgba(255,255,255,0.1);
            }
        """)
        self._input.returnPressed.connect(self._send)
        row_layout.addWidget(self._input)

        send_btn = QPushButton("→")
        send_btn.setFixedSize(36, 36)
        send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        send_btn.setStyleSheet("""
            QPushButton {
                background: #7C3AED;
                color: white;
                border-radius: 18px;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover { background: #9D5CF6; }
            QPushButton:pressed { background: #5B21B6; }
        """)
        send_btn.clicked.connect(self._send)
        row_layout.addWidget(send_btn)

        layout.addWidget(input_row)

        # Welcome message
        self.add_message("Привет! Я твой ассистент для Unreal Engine 5. Скажи или напиши что нужно сделать.", is_user=False)

    def _send(self):
        text = self._input.text().strip()
        if text:
            self._input.clear()
            self.message_sent.emit(text)

    def add_message(self, text: str, is_user: bool):
        self._remove_typing()
        bubble = MessageBubble(text, is_user)
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def show_typing(self):
        if not self._typing_indicator:
            self._typing_indicator = TypingIndicator()
            self._messages_layout.insertWidget(
                self._messages_layout.count() - 1,
                self._typing_indicator
            )
            QTimer.singleShot(50, self._scroll_to_bottom)

    def _remove_typing(self):
        if self._typing_indicator:
            self._messages_layout.removeWidget(self._typing_indicator)
            self._typing_indicator.deleteLater()
            self._typing_indicator = None

    def set_input_text(self, text: str):
        self._input.setText(text)

    def _scroll_to_bottom(self):
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
