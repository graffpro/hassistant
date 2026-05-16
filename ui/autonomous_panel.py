"""
AutonomousPanel — панель управления автономным режимом.
Позволяет передать изображение, YouTube ссылку или текстовую цель.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QProgressBar,
    QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QCursor, QDragEnterEvent, QDropEvent

from core.logger import logger


class TaskProgressItem(QFrame):
    """Один элемент в списке задач агента."""

    def __init__(self, task_desc: str, status: str = "pending", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        STATUS_ICONS = {
            "pending":   ("○", "#6B7280"),
            "running":   ("◉", "#A78BFA"),
            "done":      ("✓", "#6EE7B7"),
            "failed":    ("✕", "#FCA5A5"),
            "skipped":   ("→", "#FCD34D"),
        }
        icon, color = STATUS_ICONS.get(status, ("○", "#6B7280"))

        icon_label = QLabel(icon)
        icon_label.setFixedWidth(16)
        icon_label.setStyleSheet(f"color: {color}; font-size: 13px; background: transparent;")
        layout.addWidget(icon_label)

        text = QLabel(task_desc[:55] + ("..." if len(task_desc) > 55 else ""))
        text.setStyleSheet(f"color: {'#E2D9F3' if status != 'pending' else '#6B7280'}; font-size: 12px; background: transparent;")
        layout.addWidget(text)
        layout.addStretch()


class AutonomousPanel(QWidget):
    """Панель автономного режима."""

    start_image = pyqtSignal(str)      # путь к изображению
    start_youtube = pyqtSignal(str)    # YouTube URL
    start_goal = pyqtSignal(str)       # текстовая цель
    stop_agent = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._is_running = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Заголовок
        header = QLabel("🤖  Автономный режим")
        header.setStyleSheet("color: #C4B5FD; font-size: 14px; font-weight: bold; background: transparent;")
        layout.addWidget(header)

        desc = QLabel("Дай изображение, видео или опиши цель — агент сделает всё сам")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #6B7280; font-size: 11px; background: transparent;")
        layout.addWidget(desc)

        # Drop zone для изображений
        self._drop_zone = self._build_drop_zone()
        layout.addWidget(self._drop_zone)

        # YouTube URL
        yt_row = QHBoxLayout()
        self._yt_input = QLineEdit()
        self._yt_input.setPlaceholderText("YouTube URL (туториал по UE5)...")
        self._yt_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,0.07);
                color: #E2D9F3;
                border: 1px solid rgba(124,58,237,0.35);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: rgba(124,58,237,0.8); }
        """)
        yt_row.addWidget(self._yt_input)

        yt_btn = self._make_btn("▶", "#DC2626", width=32)
        yt_btn.setToolTip("Учиться из YouTube видео")
        yt_btn.clicked.connect(self._on_youtube)
        yt_row.addWidget(yt_btn)
        layout.addLayout(yt_row)

        # Текстовая цель
        goal_row = QHBoxLayout()
        self._goal_input = QLineEdit()
        self._goal_input.setPlaceholderText("Цель: создай комнату, квартиру, терраин...")
        self._goal_input.setStyleSheet(self._yt_input.styleSheet())
        self._goal_input.returnPressed.connect(self._on_goal)
        goal_row.addWidget(self._goal_input)

        goal_btn = self._make_btn("→", "#7C3AED", width=32)
        goal_btn.setToolTip("Автономно выполнить цель")
        goal_btn.clicked.connect(self._on_goal)
        goal_row.addWidget(goal_btn)
        layout.addLayout(goal_row)

        # Прогресс
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.hide()
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.06);
                border-radius: 4px;
                border: none;
                height: 6px;
                text-align: center;
                color: transparent;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7C3AED, stop:1 #A855F7);
                border-radius: 4px;
            }
        """)
        layout.addWidget(self._progress_bar)

        # Список задач
        self._tasks_label = QLabel("Задачи агента:")
        self._tasks_label.setStyleSheet("color: #A78BFA; font-size: 11px; background: transparent;")
        self._tasks_label.hide()
        layout.addWidget(self._tasks_label)

        self._tasks_scroll = QScrollArea()
        self._tasks_scroll.setMaximumHeight(160)
        self._tasks_scroll.setWidgetResizable(True)
        self._tasks_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._tasks_scroll.setStyleSheet("background: transparent; border: none;")
        self._tasks_scroll.hide()

        self._tasks_widget = QWidget()
        self._tasks_widget.setStyleSheet("background: transparent;")
        self._tasks_layout = QVBoxLayout(self._tasks_widget)
        self._tasks_layout.setContentsMargins(0, 0, 0, 0)
        self._tasks_layout.setSpacing(2)
        self._tasks_layout.addStretch()
        self._tasks_scroll.setWidget(self._tasks_widget)
        layout.addWidget(self._tasks_scroll)

        # Стоп кнопка
        self._stop_btn = self._make_btn("⏹ Остановить агента", "#DC2626")
        self._stop_btn.hide()
        self._stop_btn.clicked.connect(self._on_stop)
        layout.addWidget(self._stop_btn)

        layout.addStretch()

    def _build_drop_zone(self) -> QFrame:
        zone = QFrame()
        zone.setFixedHeight(80)
        zone.setStyleSheet("""
            QFrame {
                background: rgba(124,58,237,0.06);
                border: 2px dashed rgba(124,58,237,0.35);
                border-radius: 10px;
            }
            QFrame:hover {
                background: rgba(124,58,237,0.12);
                border-color: rgba(124,58,237,0.6);
            }
        """)
        layout = QVBoxLayout(zone)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("🖼️")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 22px; background: transparent; border: none;")
        layout.addWidget(icon)

        text = QLabel("Перетащи изображение или нажми для выбора")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setStyleSheet("color: #6B7280; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(text)

        zone.mousePressEvent = lambda e: self._pick_image()
        return zone

    def _make_btn(self, text: str, color: str, width: int = None) -> QPushButton:
        btn = QPushButton(text)
        if width:
            btn.setFixedWidth(width)
        btn.setFixedHeight(34)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border-radius: 8px;
                border: none;
                font-size: 13px;
                padding: 0 10px;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
            QPushButton:pressed {{ opacity: 0.7; }}
        """)
        return btn

    # --- Обработчики ---

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери изображение сцены",
            "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self._start_running()
            self.start_image.emit(path)

    def _on_youtube(self):
        url = self._yt_input.text().strip()
        if url:
            self._yt_input.clear()
            self._start_running()
            self.start_youtube.emit(url)

    def _on_goal(self):
        goal = self._goal_input.text().strip()
        if goal:
            self._goal_input.clear()
            self._start_running()
            self.start_goal.emit(goal)

    def _on_stop(self):
        self.stop_agent.emit()
        self._stop_running()

    def _start_running(self):
        self._is_running = True
        self._progress_bar.show()
        self._tasks_label.show()
        self._tasks_scroll.show()
        self._stop_btn.show()
        self._progress_bar.setValue(5)

    def _stop_running(self):
        self._is_running = False
        self._stop_btn.hide()
        self._progress_bar.setValue(100)
        QTimer.singleShot(2000, lambda: self._progress_bar.setValue(0))

    def update_progress(self, percent: int, tasks: list[dict] = None):
        """Обновляет прогресс и список задач."""
        self._progress_bar.setValue(percent)
        if tasks:
            # Очищаем и перерисовываем список
            for i in reversed(range(self._tasks_layout.count() - 1)):
                w = self._tasks_layout.itemAt(i).widget()
                if w:
                    w.deleteLater()
            for t in tasks[-8:]:  # Последние 8
                item = TaskProgressItem(t["description"], t.get("status", "pending"))
                self._tasks_layout.insertWidget(self._tasks_layout.count() - 1, item)

    # --- Drag & Drop ---

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):
                self._start_running()
                self.start_image.emit(path)
