"""
FloatingIcon — маленькая иконка ассистента всегда на экране.
Клик → открывает мини-чат рядом с иконкой.
Перетаскивается. Анимируется когда думает.
"""
import sys
import threading
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QHBoxLayout,
    QVBoxLayout, QLineEdit, QPushButton, QFrame,
    QGraphicsDropShadowEffect, QMenu, QSystemTrayIcon
)
from PyQt6.QtCore import (
    Qt, QPoint, QTimer, QPropertyAnimation,
    QEasingCurve, QRect, pyqtSignal, QSize
)
from PyQt6.QtGui import (
    QColor, QFont, QCursor, QMouseEvent,
    QPainter, QPainterPath, QBrush, QPen,
    QRadialGradient, QIcon, QPixmap, QAction
)

from core.config import config
from core.event_bus import bus, Events
from core.logger import logger


# ─────────────────────────────────────────────────────────────
# ИКОНКА
# ─────────────────────────────────────────────────────────────

class AssistantIcon(QWidget):
    """
    Маленький круглый виджет — всегда на экране.
    56×56 пикселей. Анимируется при работе.
    """
    clicked      = pyqtSignal()
    right_clicked = pyqtSignal(QPoint)

    SIZE = 56

    def __init__(self):
        super().__init__()
        self._drag_pos   = QPoint()
        self._state      = "idle"      # idle | thinking | executing | error
        self._pulse      = 0.0
        self._pulse_dir  = 1

        self._setup_window()
        self._setup_animation()
        self._position_default()

    def _setup_window(self):
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip("UE5 AI Assistant\nНажми чтобы открыть")

    def _setup_animation(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self._animate)
        self._timer.start(50)  # 20 FPS

    def _position_default(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - self.SIZE - 20,
                  screen.height() - self.SIZE - 20)

    def set_state(self, state: str):
        """idle | thinking | executing | error | learning"""
        self._state = state
        self.update()

    def _animate(self):
        if self._state in ("thinking", "executing", "learning"):
            self._pulse += 0.08 * self._pulse_dir
            if self._pulse >= 1.0:
                self._pulse_dir = -1
            elif self._pulse <= 0.0:
                self._pulse_dir = 1
        else:
            self._pulse = 0.0
            self._pulse_dir = 1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self.SIZE // 2, self.SIZE // 2
        r = (self.SIZE // 2) - 3

        # Пульсирующий ореол
        if self._state in ("thinking", "executing", "learning") and self._pulse > 0:
            STATE_GLOW = {
                "thinking":  QColor(168, 85, 247),
                "executing": QColor(124, 58, 237),
                "learning":  QColor(52, 211, 153),
            }
            glow_color = STATE_GLOW.get(self._state, QColor(124, 58, 237))
            glow_color.setAlpha(int(self._pulse * 120))
            glow_pen = QPen(glow_color, 4)
            p.setPen(glow_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            expand = int(self._pulse * 8)
            p.drawEllipse(cx - r - expand, cy - r - expand,
                          (r + expand) * 2, (r + expand) * 2)

        # Тень
        shadow_color = QColor(0, 0, 0, 80)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(shadow_color))
        p.drawEllipse(cx - r + 2, cy - r + 3, r * 2, r * 2)

        # Основной круг — градиент
        STATE_COLORS = {
            "idle":      (QColor("#7C3AED"), QColor("#4F46E5")),
            "thinking":  (QColor("#A855F7"), QColor("#7C3AED")),
            "executing": (QColor("#6D28D9"), QColor("#4338CA")),
            "error":     (QColor("#DC2626"), QColor("#991B1B")),
            "learning":  (QColor("#059669"), QColor("#047857")),
        }
        c1, c2 = STATE_COLORS.get(self._state, STATE_COLORS["idle"])

        grad = QRadialGradient(cx - r * 0.3, cy - r * 0.3, r * 1.4)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)

        p.setPen(QPen(QColor(255, 255, 255, 40), 1.5))
        p.setBrush(QBrush(grad))
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # Эмодзи
        STATE_ICONS = {
            "idle":      "🤖",
            "thinking":  "🧠",
            "executing": "⚡",
            "error":     "⚠️",
            "learning":  "📚",
        }
        icon = STATE_ICONS.get(self._state, "🤖")
        font = QFont("Segoe UI Emoji", 22)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRect(0, 0, self.SIZE, self.SIZE),
                   Qt.AlignmentFlag.AlignCenter, icon)
        p.end()

    # --- Mouse events ---
    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(e.globalPosition().toPoint())

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            # Если не перетаскивали — открываем чат
            new_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            if (new_pos - self._drag_pos).manhattanLength() < 5:
                self.clicked.emit()

    def mouseMoveEvent(self, e: QMouseEvent):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)


# ─────────────────────────────────────────────────────────────
# МИНИ-ЧАТ ПОПАП
# ─────────────────────────────────────────────────────────────

class MiniChatPopup(QWidget):
    """
    Маленькое окошко рядом с иконкой.
    Поле ввода текста + кнопка отправки + кнопка микрофона.
    Расширяется вниз когда есть ответ.
    """
    message_sent = pyqtSignal(str)

    WIDTH  = 340
    HEIGHT_COMPACT  = 56     # только ввод
    HEIGHT_EXPANDED = 280    # ввод + история

    def __init__(self, icon_widget: AssistantIcon):
        super().__init__()
        self._icon = icon_widget
        self._expanded = False
        self._messages: list[dict] = []
        self._recording = False

        self._setup_window()
        self._setup_ui()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(self.WIDTH)

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._card = QFrame()
        self._card.setStyleSheet("""
            QFrame {
                background: rgba(12, 8, 28, 0.97);
                border-radius: 16px;
                border: 1px solid rgba(124,58,237,0.5);
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 6)
        self._card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # История сообщений (скрыта по умолчанию)
        self._history_frame = QFrame()
        self._history_frame.setMaximumHeight(0)
        self._history_frame.setStyleSheet("background: transparent; border: none;")
        hist_layout = QVBoxLayout(self._history_frame)
        hist_layout.setContentsMargins(12, 10, 12, 6)
        hist_layout.setSpacing(6)

        from PyQt6.QtWidgets import QScrollArea
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 3px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(124,58,237,0.5); border-radius: 1px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self._msg_widget = QWidget()
        self._msg_widget.setStyleSheet("background: transparent;")
        self._msg_layout = QVBoxLayout(self._msg_widget)
        self._msg_layout.setContentsMargins(0, 0, 0, 0)
        self._msg_layout.setSpacing(4)
        self._msg_layout.addStretch()
        self._scroll.setWidget(self._msg_widget)
        hist_layout.addWidget(self._scroll)
        card_layout.addWidget(self._history_frame)

        # Разделитель
        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.HLine)
        self._sep.setStyleSheet("border: none; border-top: 1px solid rgba(124,58,237,0.2); background: transparent;")
        self._sep.hide()
        card_layout.addWidget(self._sep)

        # Строка ввода
        input_row = QWidget()
        input_row.setFixedHeight(self.HEIGHT_COMPACT)
        input_row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(input_row)
        row_layout.setContentsMargins(12, 8, 12, 8)
        row_layout.setSpacing(8)

        # Поле ввода
        self._input = QLineEdit()
        self._input.setPlaceholderText("Напиши или нажми 🎤 ...")
        self._input.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,0.08);
                color: #E2D9F3;
                border: 1px solid rgba(124,58,237,0.4);
                border-radius: 20px;
                padding: 8px 16px;
                font-size: 13px;
                font-family: 'Segoe UI';
            }
            QLineEdit:focus {
                border-color: rgba(168,85,247,0.8);
                background: rgba(255,255,255,0.11);
            }
        """)
        self._input.returnPressed.connect(self._send)
        row_layout.addWidget(self._input)

        # Кнопка микрофона
        self._mic_btn = QPushButton("🎤")
        self._mic_btn.setFixedSize(38, 38)
        self._mic_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._mic_btn.setToolTip("Удержи для записи голоса")
        self._mic_btn.setStyleSheet(self._btn_style("#374151", "#A78BFA"))
        self._mic_btn.pressed.connect(self._mic_press)
        self._mic_btn.released.connect(self._mic_release)
        row_layout.addWidget(self._mic_btn)

        # Кнопка отправки
        self._send_btn = QPushButton("→")
        self._send_btn.setFixedSize(38, 38)
        self._send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._send_btn.setStyleSheet(self._btn_style("#7C3AED", "#FFFFFF"))
        self._send_btn.clicked.connect(self._send)
        row_layout.addWidget(self._send_btn)

        card_layout.addWidget(input_row)
        outer.addWidget(self._card)

        # Typing indicator
        self._typing_label = QLabel("●  ●  ●")
        self._typing_label.setStyleSheet("""
            color: #A78BFA; font-size: 11px;
            background: rgba(124,58,237,0.15);
            border-radius: 10px; padding: 4px 12px;
        """)
        self._typing_label.hide()
        self._typing_timer = QTimer()
        self._typing_timer.timeout.connect(self._animate_typing)
        self._typing_dots = 0

    def _btn_style(self, bg: str, fg: str) -> str:
        return f"""
            QPushButton {{
                background: {bg};
                color: {fg};
                border-radius: 19px;
                border: none;
                font-size: 16px;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
        """

    def show_near_icon(self):
        """Показывает попап рядом с иконкой."""
        icon_pos  = self._icon.pos()
        icon_size = self._icon.size()
        screen    = QApplication.primaryScreen().availableGeometry()

        # Позиция: левее иконки, на уровне низа иконки
        x = icon_pos.x() - self.WIDTH - 10
        y = icon_pos.y() + icon_size.height() - self.HEIGHT_COMPACT

        # Не выходим за экран
        x = max(screen.left() + 8, min(x, screen.right() - self.WIDTH - 8))
        y = max(screen.top() + 8, min(y, screen.bottom() - self.HEIGHT_COMPACT - 8))

        self.move(x, y)
        self.setFixedHeight(self.HEIGHT_COMPACT)
        self.show()
        self.raise_()
        self._input.setFocus()

    def toggle(self):
        if self.isVisible():
            self.hide()
            # Reset state so next open is always compact/fresh
            self._expanded = False
            self._history_frame.setMaximumHeight(0)
            self._sep.hide()
            self.setFixedHeight(self.HEIGHT_COMPACT)
        else:
            self.show_near_icon()

    def add_message(self, text: str, is_user: bool):
        """Добавляет сообщение и разворачивает попап."""
        self._hide_typing()

        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(260)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if is_user:
            bubble.setStyleSheet("""
                background: #7C3AED; color: white;
                border-radius: 12px 12px 2px 12px;
                padding: 7px 12px; font-size: 12px;
            """)
        else:
            bubble.setStyleSheet("""
                background: rgba(255,255,255,0.08); color: #E2D9F3;
                border: 1px solid rgba(124,58,237,0.25);
                border-radius: 12px 12px 12px 2px;
                padding: 7px 12px; font-size: 12px;
            """)

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        if is_user:
            rl.addStretch()
            rl.addWidget(bubble)
        else:
            rl.addWidget(bubble)
            rl.addStretch()

        self._msg_layout.insertWidget(self._msg_layout.count() - 1, row)
        self._expand()
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def show_typing(self):
        self._typing_timer.start(400)
        self._typing_dots = 0

    def _animate_typing(self):
        self._typing_dots = (self._typing_dots + 1) % 4
        dots = "●" * self._typing_dots + "○" * (3 - self._typing_dots)
        # Добавляем анимированный индикатор в чат
        pass

    def _hide_typing(self):
        self._typing_timer.stop()

    def _expand(self):
        """Разворачивает попап чтобы показать историю."""
        if not self._expanded:
            self._expanded = True
            self._history_frame.setMaximumHeight(200)
            self._sep.show()
            self.setFixedHeight(self.HEIGHT_EXPANDED)
            # Перепозиционируем чтобы не вылезти за экран
            screen = QApplication.primaryScreen().availableGeometry()
            y = self.y() - (self.HEIGHT_EXPANDED - self.HEIGHT_COMPACT)
            y = max(screen.top() + 8, y)
            self.move(self.x(), y)

    def _send(self):
        text = self._input.text().strip()
        if text:
            self._input.clear()
            self.add_message(text, is_user=True)
            self.message_sent.emit(text)
            self.show_typing()

    def _mic_press(self):
        self._recording = True
        self._mic_btn.setStyleSheet(self._btn_style("#DC2626", "#FFFFFF"))
        self._mic_btn.setText("⏹")
        self._start_recording()

    def _mic_release(self):
        if self._recording:
            self._recording = False
            self._mic_btn.setStyleSheet(self._btn_style("#374151", "#A78BFA"))
            self._mic_btn.setText("🎤")
            self._stop_recording()

    def _start_recording(self):
        try:
            import sounddevice as sd
            import numpy as np
            self._audio_chunks = []
            self._stream = sd.InputStream(
                samplerate=16000, channels=1, dtype='float32',
                callback=lambda d, f, t, s: self._audio_chunks.append(d.copy())
            )
            self._stream.start()
        except Exception as e:
            logger.warning(f"Mic error: {e}")

    def _stop_recording(self):
        try:
            if hasattr(self, '_stream') and self._stream:
                self._stream.stop()
                self._stream.close()
            threading.Thread(target=self._transcribe, daemon=True).start()
        except Exception as e:
            logger.error(f"Stop recording error: {e}")

    def _transcribe(self):
        try:
            import whisper, numpy as np, soundfile as sf, tempfile, os
            if not self._audio_chunks:
                return
            audio = np.concatenate(self._audio_chunks).flatten()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                sf.write(f.name, audio, 16000)
                tmp = f.name
            model = whisper.load_model("base")
            result = model.transcribe(tmp, language="ru")
            text = result["text"].strip()
            os.unlink(tmp)
            if text:
                # Marshal to main UI thread safely
                QTimer.singleShot(0, lambda t=text: (
                    self._input.setText(t),
                    self._send()
                ))
        except Exception as e:
            logger.error(f"Transcribe error: {e}")

    # Клик вне попапа — закрываем
    def focusOutEvent(self, e):
        pass  # не закрываем автоматически — пользователь сам

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide()
            self._expanded = False
