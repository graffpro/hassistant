"""
VoiceInput — офлайн распознавание речи через faster-whisper.

Режимы:
  Push-to-Talk : зажми Alt+V → говори → отпусти → команда идёт в чат
  VAD-режим    : автодетекция голоса (если установлен webrtcvad)

Полностью офлайн — Whisper работает локально без интернета.
"""
import io
import time
import threading
import tempfile
import os
from typing import Optional, Callable

from core.logger import logger
from core.event_bus import bus, Events


class VoiceInput:
    """
    Слушает микрофон, транскрибирует речь через Whisper,
    отправляет текст в event bus как USER_MESSAGE.
    """

    WHISPER_MODEL   = "base"      # tiny/base/small — баланс скорость/качество
    SAMPLE_RATE     = 16000
    PTT_HOTKEY      = "<alt>+v"   # Push-to-Talk: Alt+V
    MAX_RECORD_SEC  = 30          # максимум 30 сек записи

    def __init__(self, on_transcribed: Optional[Callable[[str], None]] = None):
        self.on_transcribed = on_transcribed
        self._whisper = None          # загружается лениво
        self._running = False
        self._recording = False
        self._frames: list[bytes] = []
        self._lock = threading.Lock()
        self._ptt_thread: Optional[threading.Thread] = None
        self._available = False
        self._status_cb: Optional[Callable] = None

        self._check_dependencies()

    def set_status_callback(self, cb: Callable[[str, str], None]):
        """cb(status, message) для обновления UI."""
        self._status_cb = cb

    def _check_dependencies(self):
        """Проверяет наличие нужных библиотек."""
        try:
            import sounddevice  # noqa
            self._available = True
        except ImportError:
            logger.warning("sounddevice not installed — voice input disabled")
            self._available = False

    def _load_whisper(self) -> bool:
        """Ленивая загрузка Whisper модели."""
        if self._whisper is not None:
            return True
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading Whisper model '{self.WHISPER_MODEL}'...")
            self._whisper = WhisperModel(
                self.WHISPER_MODEL,
                device="cpu",
                compute_type="int8",   # быстрее на CPU
            )
            logger.info("Whisper ready ✓")
            return True
        except ImportError:
            # Пробуем обычный openai-whisper
            try:
                import whisper
                logger.info(f"Loading OpenAI Whisper '{self.WHISPER_MODEL}'...")
                self._whisper = whisper.load_model(self.WHISPER_MODEL)
                self._use_openai_whisper = True
                logger.info("Whisper (OpenAI) ready ✓")
                return True
            except ImportError:
                logger.warning("Neither faster-whisper nor openai-whisper installed")
                return False
        except Exception as e:
            logger.error(f"Whisper load error: {e}")
            return False

    # ─────────────────────────────────────────────────────────
    # PUSH-TO-TALK
    # ─────────────────────────────────────────────────────────

    def start_ptt(self):
        """Запускает Push-to-Talk режим (Alt+V)."""
        if not self._available:
            logger.warning("Voice input not available — install sounddevice")
            return
        self._running = True
        self._ptt_thread = threading.Thread(target=self._ptt_loop, daemon=True)
        self._ptt_thread.start()
        logger.info(f"Push-to-Talk started — hold {self.PTT_HOTKEY} to speak")

    def stop(self):
        self._running = False
        self._recording = False

    def _ptt_loop(self):
        """Слушает нажатие Alt+V для Push-to-Talk."""
        try:
            from pynput import keyboard

            ptt_active = threading.Event()

            def on_press(key):
                try:
                    if (hasattr(key, 'char') and key.char == 'v' or
                            str(key) == "'v'"):
                        # Проверяем что Alt зажат
                        pass
                except Exception:
                    pass

            # Используем hotkey listener
            with keyboard.GlobalHotKeys({
                self.PTT_HOTKEY: lambda: self._on_ptt_press(ptt_active),
            }) as h:
                while self._running:
                    time.sleep(0.1)

        except ImportError:
            logger.warning("pynput not installed — using keyboard polling fallback")
            self._ptt_loop_polling()
        except Exception as e:
            logger.error(f"PTT loop error: {e}")

    def _ptt_loop_polling(self):
        """Fallback: опрос состояния Alt+V через keyboard модуль."""
        try:
            import keyboard as kb
            logger.info("PTT: using keyboard polling (hold Alt+V to speak)")
            was_pressed = False
            while self._running:
                pressed = kb.is_pressed("alt+v")
                if pressed and not was_pressed:
                    self._start_recording()
                elif not pressed and was_pressed:
                    self._stop_and_transcribe()
                was_pressed = pressed
                time.sleep(0.05)
        except ImportError:
            logger.warning("keyboard not installed — PTT unavailable. "
                           "Install: pip install keyboard")

    def _on_ptt_press(self, ptt_active: threading.Event):
        """Переключает запись при нажатии PTT."""
        if not self._recording:
            self._start_recording()
        else:
            self._stop_and_transcribe()

    # ─────────────────────────────────────────────────────────
    # ЗАПИСЬ АУДИО
    # ─────────────────────────────────────────────────────────

    def _start_recording(self):
        """Начинает запись с микрофона."""
        if self._recording:
            return
        self._recording = True
        with self._lock:
            self._frames = []

        self._emit_status("🎤 Слушаю... (отпусти Alt+V чтобы отправить)")
        threading.Thread(target=self._record_loop, daemon=True).start()

    def _record_loop(self):
        """Записывает аудио пока self._recording == True."""
        try:
            import sounddevice as sd
            import numpy as np

            chunk_size = 1024
            start = time.time()

            with sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=chunk_size,
            ) as stream:
                while self._recording and (time.time() - start) < self.MAX_RECORD_SEC:
                    data, _ = stream.read(chunk_size)
                    with self._lock:
                        self._frames.append(bytes(data))

        except Exception as e:
            logger.error(f"Recording error: {e}")
            self._recording = False

    def _stop_and_transcribe(self):
        """Останавливает запись и транскрибирует."""
        self._recording = False
        self._emit_status("🔄 Распознаю речь...")

        with self._lock:
            frames = list(self._frames)
            self._frames = []

        if not frames:
            self._emit_status("")
            return

        threading.Thread(
            target=self._transcribe,
            args=(frames,),
            daemon=True,
        ).start()

    def _transcribe(self, frames: list[bytes]):
        """Транскрибирует аудио через Whisper."""
        if not self._load_whisper():
            self._emit_status("❌ Whisper не установлен")
            return

        try:
            import numpy as np

            # Склеиваем фреймы в numpy массив
            audio_bytes = b"".join(frames)
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            # Транскрибируем
            if hasattr(self, "_use_openai_whisper") and self._use_openai_whisper:
                result = self._transcribe_openai(audio_np)
            else:
                result = self._transcribe_faster(audio_np)

            if result and len(result.strip()) > 1:
                text = result.strip()
                logger.info(f"Transcribed: {text!r}")
                self._emit_status(f"✅ Распознано: {text}")
                # Отправляем как обычное сообщение
                if self.on_transcribed:
                    self.on_transcribed(text)
                else:
                    bus.emit(Events.USER_VOICE, text)
            else:
                self._emit_status("🔇 Ничего не распознано")

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            self._emit_status("❌ Ошибка распознавания")

    def _transcribe_faster(self, audio_np) -> str:
        """Транскрибирует через faster-whisper."""
        segments, info = self._whisper.transcribe(
            audio_np,
            language="ru",           # русский по умолчанию
            beam_size=3,
            vad_filter=True,         # фильтрует тишину
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        return " ".join(s.text for s in segments).strip()

    def _transcribe_openai(self, audio_np) -> str:
        """Транскрибирует через openai-whisper."""
        import whisper
        result = self._whisper.transcribe(audio_np, language="ru", fp16=False)
        return result.get("text", "").strip()

    def _emit_status(self, message: str):
        if message:
            bus.emit(Events.STATUS_UPDATE, {"status": "thinking", "message": message})
        if self._status_cb:
            self._status_cb("voice", message)

    # ─────────────────────────────────────────────────────────
    # УСТАНОВКА ЗАВИСИМОСТЕЙ
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def install_dependencies():
        """Устанавливает нужные пакеты если их нет."""
        import subprocess, sys
        packages = [
            "faster-whisper",
            "sounddevice",
            "keyboard",
        ]
        for pkg in packages:
            try:
                __import__(pkg.replace("-", "_"))
            except ImportError:
                logger.info(f"Installing {pkg}...")
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                    check=False,
                )
