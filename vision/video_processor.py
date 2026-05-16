"""
VideoProcessor — скачивает YouTube видео и извлекает из него UE5 шаги.
Использует yt-dlp + Whisper (транскрипция) + LLaVA (ключевые кадры).
"""
import os
import re
import json
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

from core.logger import logger
from core.config import config


@dataclass
class VideoStep:
    """Один шаг, извлечённый из видео."""
    timestamp: float        # секунда в видео
    description: str        # что делает человек
    action_type: str        # click | type | shortcut | navigate
    target: str             # UI элемент
    value: Optional[str]    # текст/клавиша
    confidence: float = 0.7


@dataclass
class VideoAnalysis:
    """Полный анализ обучающего видео."""
    title: str
    url: str
    duration_sec: int
    transcript: str                              # полная транскрипция аудио
    steps: list[VideoStep] = field(default_factory=list)
    summary: str = ""
    ue5_tasks: list[str] = field(default_factory=list)
    source: str = "youtube"


class VideoProcessor:
    """
    Обрабатывает YouTube видео по UE5:
    1. Скачивает через yt-dlp
    2. Транскрибирует аудио через Whisper
    3. Извлекает ключевые кадры через OpenCV
    4. Анализирует кадры через LLaVA
    5. Строит workflow из извлечённых шагов
    """

    def __init__(self, llm_client, image_analyzer):
        self.llm = llm_client
        self.image_analyzer = image_analyzer
        self._check_deps()

    def _check_deps(self):
        try:
            import yt_dlp
            self._yt_dlp_available = True
        except ImportError:
            self._yt_dlp_available = False
            logger.warning("yt-dlp not installed. Run: pip install yt-dlp")

        try:
            import whisper
            self._whisper_available = True
        except ImportError:
            self._whisper_available = False
            logger.warning("whisper not installed. Run: pip install openai-whisper")

    def process_youtube(self, url: str,
                        progress_callback: Optional[Callable[[str], None]] = None) -> VideoAnalysis:
        """
        Полная обработка YouTube видео.
        progress_callback(message) — для обновления UI.
        """
        def progress(msg: str):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        if not self._yt_dlp_available:
            raise RuntimeError("yt-dlp не установлен. Запусти: pip install yt-dlp")

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Скачиваем видео
            progress("📥 Скачиваю видео...")
            video_path, title, duration = self._download_video(url, tmpdir)
            progress(f"✅ Скачано: {title} ({duration}с)")

            analysis = VideoAnalysis(title=title, url=url, duration_sec=duration, transcript="")

            # 2. Транскрипция аудио
            progress("🎤 Транскрибирую аудио через Whisper...")
            transcript = self._transcribe_audio(video_path)
            analysis.transcript = transcript
            progress(f"✅ Транскрипция: {len(transcript)} символов")

            # 3. Извлечение ключевых кадров
            progress("🖼️ Извлекаю ключевые кадры...")
            frames = self._extract_key_frames(video_path, max_frames=12)
            progress(f"✅ Извлечено {len(frames)} ключевых кадров")

            # 4. Анализ кадров через LLaVA (если доступна)
            if self.image_analyzer._vision_model and frames:
                progress("🔍 Анализирую кадры через Vision AI...")
                frame_descriptions = self._analyze_frames(frames, progress)
            else:
                frame_descriptions = []

            # 5. Извлечение шагов через LLM
            progress("🧠 Извлекаю UE5 шаги из контента...")
            steps, tasks = self._extract_steps(transcript, frame_descriptions, title)
            analysis.steps = steps
            analysis.ue5_tasks = tasks

            # 6. Генерируем summary
            analysis.summary = self._generate_summary(transcript, tasks)
            progress(f"✅ Готово! Извлечено {len(steps)} шагов, {len(tasks)} задач UE5")

        return analysis

    def _download_video(self, url: str, output_dir: str):
        """Скачивает видео через yt-dlp."""
        import yt_dlp

        output_path = os.path.join(output_dir, "video.%(ext)s")
        ydl_opts = {
            "format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "outtmpl": output_path,
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "Unknown")
            duration = int(info.get("duration", 0))
            filename = ydl.prepare_filename(info)
            # yt-dlp может изменить расширение
            for ext in ["mp4", "webm", "mkv", "mov"]:
                candidate = os.path.join(output_dir, f"video.{ext}")
                if os.path.exists(candidate):
                    return candidate, title, duration
            return filename, title, duration

    def _transcribe_audio(self, video_path: str) -> str:
        """Транскрибирует аудио из видео через Whisper."""
        if not self._whisper_available:
            return ""
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(video_path, language=None)  # auto-detect
            return result.get("text", "")
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ""

    def _extract_key_frames(self, video_path: str, max_frames: int = 12) -> list[bytes]:
        """Извлекает равномерно распределённые ключевые кадры."""
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total / fps if fps > 0 else 0

            frames = []
            interval = max(1, total // max_frames)

            for i in range(0, total, interval):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if ret:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    frames.append(buf.tobytes())
                if len(frames) >= max_frames:
                    break

            cap.release()
            return frames
        except Exception as e:
            logger.error(f"Frame extraction error: {e}")
            return []

    def _analyze_frames(self, frames: list[bytes],
                        progress: Callable) -> list[str]:
        """Анализирует кадры через LLaVA."""
        descriptions = []
        for i, frame_bytes in enumerate(frames):
            try:
                progress(f"🔍 Анализирую кадр {i+1}/{len(frames)}...")
                analysis = self.image_analyzer.analyze_from_bytes(frame_bytes, f"frame_{i}")
                if analysis.raw_description:
                    descriptions.append(f"[Кадр {i+1}]: {analysis.raw_description}")
            except Exception as e:
                logger.debug(f"Frame {i} analysis failed: {e}")
        return descriptions

    def _extract_steps(self, transcript: str, frame_descriptions: list[str],
                       title: str) -> tuple[list[VideoStep], list[str]]:
        """Извлекает шаги и задачи UE5 из транскрипции и описаний кадров."""

        context = f"Название видео: {title}\n\n"
        if transcript:
            context += f"Транскрипция:\n{transcript[:3000]}\n\n"
        if frame_descriptions:
            context += f"Визуальный контент:\n" + "\n".join(frame_descriptions[:8])

        system = """Ты эксперт по Unreal Engine 5.
Извлеки из контента учебного видео по UE5 конкретные шаги для воспроизведения.

Верни JSON:
{
  "summary": "краткое описание что делают в видео",
  "ue5_tasks": [
    "Задача 1 для UE5",
    "Задача 2 для UE5",
    ...
  ],
  "steps": [
    {
      "timestamp": 0,
      "description": "что делается",
      "action_type": "click|type|shortcut|navigate|menu",
      "target": "UI элемент UE5",
      "value": "текст или клавиша или null",
      "confidence": 0.8
    }
  ]
}"""

        response = self.llm.complete(prompt=context, system=system)
        if not response.success:
            return [], ["Создать новый Level", "Следовать туториалу"]

        try:
            match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                steps = [
                    VideoStep(
                        timestamp=s.get("timestamp", 0),
                        description=s.get("description", ""),
                        action_type=s.get("action_type", "click"),
                        target=s.get("target", ""),
                        value=s.get("value"),
                        confidence=float(s.get("confidence", 0.7)),
                    )
                    for s in data.get("steps", [])
                ]
                return steps, data.get("ue5_tasks", [])
        except Exception as e:
            logger.error(f"Steps parse error: {e}")

        return [], []

    def _generate_summary(self, transcript: str, tasks: list[str]) -> str:
        if not transcript and not tasks:
            return "Нет данных"
        task_list = "\n".join(f"- {t}" for t in tasks[:5])
        return f"Задачи из видео:\n{task_list}"
