"""
VoiceInputButton — кнопка записи голоса.
Записывает аудио → транскрибирует через Whisper локально.
"""
import threading
import tempfile
import os
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QCursor

from core.logger import logger


class VoiceInputButton(QPushButton):
    """
    Кнопка микрофона. При удержании — записывает.
    При отпускании — транскрибирует и отправляет текст.
    """
    transcription_ready = pyqtSignal(str)

    STYLE_IDLE = """
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: #A78BFA;
            border-radius: 18px;
            border: 1px solid rgba(124,58,237,0.4);
            font-size: 18px;
            min-width: 36px;
            min-height: 36px;
            max-width: 36px;
            max-height: 36px;
        }
        QPushButton:hover { background: rgba(124,58,237,0.3); }
    """
    STYLE_RECORDING = """
        QPushButton {
            background: #DC2626;
            color: white;
            border-radius: 18px;
            border: 2px solid #FCA5A5;
            font-size: 18px;
            min-width: 36px;
            min-height: 36px;
            max-width: 36px;
            max-height: 36px;
        }
    """

    def __init__(self, parent=None):
        super().__init__("🎤", parent)
        self.setFixedSize(36, 36)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet(self.STYLE_IDLE)
        self.setToolTip("Удержи для записи голоса")

        self._recording = False
        self._audio_data = []
        self._stream = None
        self._record_thread = None

        # Check if sounddevice is available
        try:
            import sounddevice as sd
            import numpy as np
            self._sd = sd
            self._np = np
            self._available = True
        except ImportError:
            self._available = False
            self.setToolTip("sounddevice не установлен — голос недоступен")
            self.setEnabled(False)
            logger.warning("sounddevice not installed — voice input disabled")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._available:
            self._start_recording()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._recording:
            self._stop_recording()

    def _start_recording(self):
        self._recording = True
        self._audio_data = []
        self.setStyleSheet(self.STYLE_RECORDING)
        self.setText("⏹")
        logger.info("Voice recording started")

        def record():
            with self._sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype='float32',
                callback=self._audio_callback
            ):
                while self._recording:
                    self._sd.sleep(100)

        self._record_thread = threading.Thread(target=record, daemon=True)
        self._record_thread.start()

    def _audio_callback(self, indata, frames, time, status):
        self._audio_data.append(indata.copy())

    def _stop_recording(self):
        self._recording = False
        self.setStyleSheet(self.STYLE_IDLE)
        self.setText("🎤")
        logger.info("Voice recording stopped, transcribing...")

        threading.Thread(target=self._transcribe, daemon=True).start()

    def _transcribe(self):
        try:
            import whisper
            import numpy as np
            import soundfile as sf

            if not self._audio_data:
                return

            audio = np.concatenate(self._audio_data, axis=0).flatten()

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                sf.write(f.name, audio, 16000)
                tmp_path = f.name

            model = whisper.load_model("base")
            result = model.transcribe(tmp_path, language="ru")
            text = result["text"].strip()
            os.unlink(tmp_path)

            logger.info(f"Transcribed: {text!r}")
            if text:
                self.transcription_ready.emit(text)

        except Exception as e:
            logger.error(f"Transcription error: {e}")
