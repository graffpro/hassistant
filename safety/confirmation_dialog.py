"""
ConfirmationDialog — запрашивает подтверждение у пользователя
перед выполнением опасных операций.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QCursor

from core.event_bus import bus, Events
from core.logger import logger


class ConfirmationDialog(QDialog):
    """
    Диалог подтверждения опасного действия.
    Показывается поверх всех окон.
    """
    confirmed = pyqtSignal(bool)    # True = подтверждено, False = отменено

    def __init__(self, action_description: str, reason: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._setup_ui(action_description, reason)

    def _setup_ui(self, action_desc: str, reason: str):
        self.setMinimumWidth(380)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 10, 40, 0.97);
                border-radius: 14px;
                border: 1px solid rgba(239, 68, 68, 0.6);
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(14)

        # Заголовок
        title = QLabel("⚠️  Требуется подтверждение")
        title.setStyleSheet("color: #FCA5A5; font-size: 15px; font-weight: bold; background: transparent; border: none;")
        card_layout.addWidget(title)

        # Причина
        reason_label = QLabel(reason)
        reason_label.setWordWrap(True)
        reason_label.setStyleSheet("color: #FCD34D; font-size: 13px; background: transparent; border: none;")
        card_layout.addWidget(reason_label)

        # Описание действия
        action_label = QLabel(f"Действие:\n{action_desc}")
        action_label.setWordWrap(True)
        action_label.setStyleSheet("""
            color: #E2D9F3;
            font-size: 12px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px;
            padding: 10px;
        """)
        card_layout.addWidget(action_label)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        cancel_btn = QPushButton("✕  Отмена")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: #A78BFA;
                border-radius: 10px;
                border: 1px solid rgba(124,58,237,0.4);
                font-size: 13px;
            }
            QPushButton:hover { background: rgba(124,58,237,0.3); }
        """)
        cancel_btn.clicked.connect(self._on_cancel)

        confirm_btn = QPushButton("✓  Выполнить")
        confirm_btn.setFixedHeight(40)
        confirm_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        confirm_btn.setStyleSheet("""
            QPushButton {
                background: rgba(220, 38, 38, 0.7);
                color: white;
                border-radius: 10px;
                border: 1px solid rgba(239,68,68,0.6);
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background: rgba(220, 38, 38, 0.9); }
        """)
        confirm_btn.clicked.connect(self._on_confirm)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)
        card_layout.addLayout(btn_row)

        outer.addWidget(card)

    def _on_confirm(self):
        logger.info("User confirmed dangerous action")
        self.confirmed.emit(True)
        self.accept()

    def _on_cancel(self):
        logger.info("User cancelled dangerous action")
        self.confirmed.emit(False)
        self.reject()

    @staticmethod
    def ask(action_description: str, reason: str, parent=None) -> bool:
        """Показывает диалог и возвращает решение пользователя."""
        dialog = ConfirmationDialog(action_description, reason, parent)
        dialog.exec()
        return dialog.result() == QDialog.DialogCode.Accepted
