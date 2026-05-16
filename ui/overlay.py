"""
AssistantOverlay — главное плавающее окно ассистента.
Всегда поверх всех окон. Содержит иконку, чат и статус.
"""
import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSizeGrip, QApplication, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import (
    Qt, QPoint, QPropertyAnimation, QEasingCurve,
    QSize, pyqtSignal, QTimer
)
from PyQt6.QtGui import (
    QIcon, QPixmap, QColor, QPainter, QPainterPath,
    QFont, QCursor, QMouseEvent
)

from core.config import config
from core.event_bus import bus, Events
from core.logger import logger
from ui.chat_widget import ChatWidget
from ui.status_bar import StatusBar
from ui.voice_input import VoiceInputButton
from ui.autonomous_panel import AutonomousPanel


class FloatingIcon(QLabel):
    """
    Маленькая иконка ассистента — всегда видна на экране.
    По клику разворачивает/сворачивает панель чата.
    """
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(config.ui.icon_size, config.ui.icon_size)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._pulse)
        self._pulse_state = 0
        self._is_thinking = False
        self._setup_icon()

    def _setup_icon(self):
        self.setStyleSheet("""
            QLabel {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                    fx:0.5, fy:0.5,
                    stop:0 #7C3AED, stop:1 #4F46E5);
                border-radius: 28px;
                border: 2px solid rgba(255,255,255,0.2);
            }
        """)
        # Shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(124, 58, 237, 160))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        self.setText("🤖")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(22)
        self.setFont(font)

    def set_thinking(self, thinking: bool):
        self._is_thinking = thinking
        if thinking:
            self._pulse_timer.start(600)
        else:
            self._pulse_timer.stop()
            self._pulse_state = 0
            self._update_icon_color("#7C3AED", "#4F46E5")

    def _pulse(self):
        self._pulse_state = 1 - self._pulse_state
        if self._pulse_state:
            self._update_icon_color("#A855F7", "#7C3AED")
        else:
            self._update_icon_color("#7C3AED", "#4F46E5")

    def _update_icon_color(self, c1: str, c2: str):
        self.setStyleSheet(f"""
            QLabel {{
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                    fx:0.5, fy:0.5,
                    stop:0 {c1}, stop:1 {c2});
                border-radius: 28px;
                border: 2px solid rgba(255,255,255,0.2);
            }}
        """)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class AssistantOverlay(QWidget):
    """
    Главное окно ассистента.
    - Всегда поверх всех окон
    - Перетаскивается мышью
    - Сворачивается в иконку
    - Содержит чат, голосовой ввод и статус
    """

    def __init__(self, orchestrator, agent=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.agent = agent
        self._drag_pos = QPoint()
        self._is_expanded = False

        self._setup_window()
        self._setup_ui()
        self._connect_events()
        self._position_window()

        logger.info("AssistantOverlay initialized")

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool               # не показывать в таскбаре
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(config.ui.opacity)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # --- Expanded Panel (чат) ---
        self.panel = QWidget()
        self.panel.setFixedWidth(config.ui.overlay_width)
        self.panel.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 12, 30, 0.96);
                border-radius: 16px;
                border: 1px solid rgba(124, 58, 237, 0.4);
            }
        """)
        panel_shadow = QGraphicsDropShadowEffect()
        panel_shadow.setBlurRadius(40)
        panel_shadow.setColor(QColor(0, 0, 0, 180))
        panel_shadow.setOffset(0, 8)
        self.panel.setGraphicsEffect(panel_shadow)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header
        header = self._build_header()
        panel_layout.addWidget(header)

        # Status bar
        self.status_bar = StatusBar()
        panel_layout.addWidget(self.status_bar)

        # Chat
        self.chat = ChatWidget()
        self.chat.message_sent.connect(self._on_user_message)
        panel_layout.addWidget(self.chat)

        # Voice + input row
        bottom_row = self._build_bottom_row()
        panel_layout.addWidget(bottom_row)

        # Tab switcher (Chat / Autonomous)
        tab_row = self._build_tab_row()
        panel_layout.insertWidget(1, tab_row)

        # Autonomous panel (скрыта по умолчанию)
        self.auto_panel = AutonomousPanel()
        self.auto_panel.start_image.connect(self._on_agent_image)
        self.auto_panel.start_youtube.connect(self._on_agent_youtube)
        self.auto_panel.start_goal.connect(self._on_agent_goal)
        self.auto_panel.stop_agent.connect(self._on_agent_stop)
        self.auto_panel.hide()
        panel_layout.insertWidget(3, self.auto_panel)

        self.panel.hide()
        main_layout.addWidget(self.panel)

        # --- Floating Icon ---
        icon_row = QHBoxLayout()
        icon_row.setContentsMargins(0, 0, 0, 0)

        self.icon = FloatingIcon()
        self.icon.clicked.connect(self._toggle_panel)
        icon_row.addStretch()
        icon_row.addWidget(self.icon)

        icon_container = QWidget()
        icon_container.setLayout(icon_row)
        icon_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        main_layout.addWidget(icon_container)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("""
            QWidget {
                background-color: rgba(124, 58, 237, 0.15);
                border-radius: 16px 16px 0px 0px;
                border-bottom: 1px solid rgba(124, 58, 237, 0.3);
            }
        """)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 0, 14, 0)

        title = QLabel("🤖  UE5 Assistant")
        title.setStyleSheet("color: #E2D9F3; font-size: 14px; font-weight: 600; background: transparent; border: none;")
        layout.addWidget(title)
        layout.addStretch()

        # Minimize button
        btn_min = QPushButton("─")
        btn_min.setFixedSize(28, 28)
        btn_min.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_min.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: #A78BFA;
                border-radius: 14px;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(124,58,237,0.4); }
        """)
        btn_min.clicked.connect(self._toggle_panel)
        layout.addWidget(btn_min)

        return header

    def _build_bottom_row(self) -> QWidget:
        row = QWidget()
        row.setFixedHeight(60)
        row.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Voice input button
        self.voice_btn = VoiceInputButton()
        self.voice_btn.transcription_ready.connect(self._on_voice_transcription)
        layout.addWidget(self.voice_btn)

        # Quick action buttons
        for label, cmd in [("📁 Папка", "создай новую папку"), ("🔷 Blueprint", "создай новый Blueprint")]:
            btn = QPushButton(label)
            btn.setFixedHeight(36)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(124,58,237,0.2);
                    color: #C4B5FD;
                    border-radius: 8px;
                    border: 1px solid rgba(124,58,237,0.4);
                    font-size: 12px;
                    padding: 0 10px;
                }
                QPushButton:hover { background: rgba(124,58,237,0.4); }
            """)
            btn.clicked.connect(lambda checked, c=cmd: self._on_user_message(c))
            layout.addWidget(btn)

        return row

    def _build_tab_row(self) -> QWidget:
        row = QWidget()
        row.setFixedHeight(36)
        row.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(6)

        self._tab_chat = QPushButton("💬 Чат")
        self._tab_auto = QPushButton("🤖 Авто")

        for btn, active in [(self._tab_chat, True), (self._tab_auto, False)]:
            btn.setFixedHeight(26)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self._update_tab_style(btn, active)
            layout.addWidget(btn)

        layout.addStretch()
        self._tab_chat.clicked.connect(lambda: self._switch_tab("chat"))
        self._tab_auto.clicked.connect(lambda: self._switch_tab("auto"))
        return row

    def _update_tab_style(self, btn: QPushButton, active: bool):
        if active:
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(124,58,237,0.5);
                    color: white;
                    border-radius: 8px;
                    border: 1px solid rgba(124,58,237,0.8);
                    font-size: 12px;
                    padding: 0 12px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.05);
                    color: #6B7280;
                    border-radius: 8px;
                    border: 1px solid rgba(255,255,255,0.1);
                    font-size: 12px;
                    padding: 0 12px;
                }
                QPushButton:hover { background: rgba(124,58,237,0.2); color: #A78BFA; }
            """)

    def _switch_tab(self, tab: str):
        if tab == "chat":
            self.chat.show()
            self.auto_panel.hide()
            self._update_tab_style(self._tab_chat, True)
            self._update_tab_style(self._tab_auto, False)
        else:
            self.chat.hide()
            self.auto_panel.show()
            self._update_tab_style(self._tab_chat, False)
            self._update_tab_style(self._tab_auto, True)

    def _on_agent_image(self, path: str):
        if self.agent:
            self.chat.add_message(f"🖼️ Анализирую изображение: {path}", is_user=False)
            self.icon.set_thinking(True)
            self.agent.run_from_image(path)

    def _on_agent_youtube(self, url: str):
        if self.agent:
            self.chat.add_message(f"▶️ Учусь из видео: {url}", is_user=False)
            self.icon.set_thinking(True)
            self.agent.run_from_youtube(url)

    def _on_agent_goal(self, goal: str):
        if self.agent:
            self.chat.add_message(f"🎯 Автономная цель: {goal}", is_user=False)
            self.icon.set_thinking(True)
            self.agent.run_goal(goal)

    def _on_agent_stop(self):
        if self.agent:
            self.agent.stop()
            self.chat.add_message("⏹ Агент остановлен", is_user=False)
            self.icon.set_thinking(False)

    def _connect_events(self):
        bus.subscribe(Events.STATUS_UPDATE, self._on_status_update)
        bus.subscribe(Events.ACTION_SUCCESS, lambda _: self.icon.set_thinking(False))
        bus.subscribe(Events.ACTION_FAILURE, lambda _: self.icon.set_thinking(False))

    def _position_window(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - config.ui.overlay_width - 20
        y = screen.height() - 80
        self.move(x, y)
        self.adjustSize()

    def _toggle_panel(self):
        self._is_expanded = not self._is_expanded
        if self._is_expanded:
            self.panel.show()
            # Animate slide up
            self._animate_panel(show=True)
            # Reposition
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.width() - config.ui.overlay_width - 20
            y = screen.height() - config.ui.overlay_height - 80
            self.move(x, y)
        else:
            self._animate_panel(show=False)
        self.adjustSize()

    def _animate_panel(self, show: bool):
        anim = QPropertyAnimation(self.panel, b"maximumHeight")
        anim.setDuration(250)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if show:
            self.panel.setMaximumHeight(0)
            anim.setStartValue(0)
            anim.setEndValue(config.ui.overlay_height)
        else:
            anim.setStartValue(self.panel.height())
            anim.setEndValue(0)
            anim.finished.connect(self.panel.hide)
        anim.start()
        self._current_anim = anim  # keep ref

    def _on_user_message(self, text: str):
        if not text.strip():
            return
        self.chat.add_message(text, is_user=True)
        self.icon.set_thinking(True)
        self.status_bar.set_status("thinking", "Анализирую...")
        bus.emit(Events.USER_MESSAGE, text)

    def _on_voice_transcription(self, text: str):
        if text.strip():
            self.chat.set_input_text(text)
            self._on_user_message(text)

    def _on_status_update(self, data: dict):
        status = data.get("status", "idle")
        message = data.get("message", "")
        self.status_bar.set_status(status, message)

        if status in ("idle", "error"):
            self.icon.set_thinking(False)
            if message:
                self.chat.add_message(message, is_user=False)
        elif status == "thinking":
            self.icon.set_thinking(True)

    # --- Drag to move ---
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)
