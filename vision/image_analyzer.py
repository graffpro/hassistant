"""
ImageAnalyzer — анализирует изображения через LLaVA (локальная vision модель).
Понимает сцены: комнаты, террейны, архитектуру — и переводит в UE5 задачи.
"""
import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from core.config import config
from core.logger import logger


@dataclass
class SceneElement:
    """Один элемент сцены, обнаруженный на изображении."""
    category: str           # "floor", "wall", "terrain", "furniture", "light", "window"
    description: str        # "деревянный паркетный пол"
    ue5_asset_type: str     # "StaticMesh" | "Material" | "Landscape" | "Light"
    ue5_suggestion: str     # "используй Quixel Bridge для деревянного пола"
    priority: int = 1       # 1=высокий, 2=средний, 3=низкий


@dataclass
class SceneAnalysis:
    """Полный анализ сцены."""
    raw_description: str                          # Текстовое описание от LLaVA
    scene_type: str                               # "interior" | "exterior" | "terrain" | "mixed"
    elements: list[SceneElement] = field(default_factory=list)
    ue5_tasks: list[str] = field(default_factory=list)   # Список задач для UE5
    style: str = ""                               # "modern", "medieval", "sci-fi", "realistic"
    complexity: str = "medium"                    # "simple" | "medium" | "complex"
    source_path: str = ""


VISION_SYSTEM_PROMPT = """Ты — эксперт по Unreal Engine 5 и 3D-дизайну.
Анализируй изображение и определи:

1. Тип сцены (интерьер/экстерьер/терраин/смешанный)
2. Все видимые элементы (пол, стены, мебель, освещение, терраин, вода и т.д.)
3. Стиль (современный, средневековый, sci-fi, реалистичный)
4. Сложность воспроизведения в UE5

Верни ТОЛЬКО JSON:
{
  "scene_type": "interior|exterior|terrain|mixed",
  "style": "modern|medieval|sci-fi|realistic|stylized",
  "complexity": "simple|medium|complex",
  "description": "краткое описание сцены",
  "elements": [
    {
      "category": "floor|wall|ceiling|terrain|furniture|light|window|door|vegetation|water|sky|prop",
      "description": "подробное описание элемента",
      "ue5_asset_type": "StaticMesh|Material|Landscape|Light|NiagaraSystem|Blueprint",
      "ue5_suggestion": "конкретная рекомендация для UE5",
      "priority": 1
    }
  ],
  "ue5_tasks": [
    "Создать новый Level",
    "Добавить Landscape для терраина",
    "Создать материал деревянного пола",
    "..."
  ]
}"""


class ImageAnalyzer:
    """
    Анализирует изображения через LLaVA (vision LLM в Ollama).
    Fallback: текстовое описание через обычный LLM.
    """

    VISION_MODELS = ["llava:13b", "llava:7b", "llava-phi3", "moondream"]

    def __init__(self, llm_client):
        self.llm = llm_client
        self._vision_model = self._detect_vision_model()

    def _detect_vision_model(self) -> Optional[str]:
        """Находит доступную vision модель в Ollama."""
        try:
            resp = requests.get(f"{config.llm.host}/api/tags", timeout=3)
            if resp.ok:
                available = [m["name"] for m in resp.json().get("models", [])]
                for candidate in self.VISION_MODELS:
                    for model in available:
                        if candidate.split(":")[0] in model:
                            logger.info(f"Vision model found: {model}")
                            return model
        except Exception:
            pass
        logger.warning("No vision model found. Install: ollama pull llava:7b")
        return None

    def analyze_image(self, image_path: str) -> SceneAnalysis:
        """Анализирует изображение из файла."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        logger.info(f"Analyzing image: {path.name}")

        # Конвертируем в base64
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        analysis = self._analyze_with_vision(img_b64, path.name)
        analysis.source_path = str(path)
        return analysis

    def analyze_from_bytes(self, image_bytes: bytes, filename: str = "image") -> SceneAnalysis:
        """Анализирует изображение из байтов."""
        img_b64 = base64.b64encode(image_bytes).decode()
        return self._analyze_with_vision(img_b64, filename)

    def _analyze_with_vision(self, img_b64: str, filename: str) -> SceneAnalysis:
        """Отправляет изображение в LLaVA и получает анализ сцены."""

        if self._vision_model:
            result = self._call_llava(img_b64)
        else:
            # Fallback: просим LLM описать что было бы на изображении
            result = self._text_fallback(filename)

        return self._parse_analysis(result)

    def _call_llava(self, img_b64: str) -> str:
        """Вызывает LLaVA через Ollama API."""
        try:
            payload = {
                "model": self._vision_model,
                "prompt": "Analyze this image for Unreal Engine 5 scene recreation. " + VISION_SYSTEM_PROMPT,
                "images": [img_b64],
                "stream": False,
            }
            resp = requests.post(
                f"{config.llm.host}/api/generate",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            logger.error(f"LLaVA error: {e}")
            return ""

    def _text_fallback(self, filename: str) -> str:
        """Fallback если нет vision модели."""
        logger.warning("Using text-only fallback (no vision model)")
        response = self.llm.complete(
            prompt=f"Файл называется '{filename}'. Предположи что это за сцена и создай план для UE5.",
            system=VISION_SYSTEM_PROMPT,
        )
        return response.content if response.success else ""

    def _parse_analysis(self, llm_output: str) -> SceneAnalysis:
        """Парсит JSON ответ от LLaVA."""
        try:
            match = re.search(r'\{.*\}', llm_output, re.DOTALL)
            if match:
                data = json.loads(match.group())
                elements = [
                    SceneElement(
                        category=e.get("category", "prop"),
                        description=e.get("description", ""),
                        ue5_asset_type=e.get("ue5_asset_type", "StaticMesh"),
                        ue5_suggestion=e.get("ue5_suggestion", ""),
                        priority=int(e.get("priority", 2)),
                    )
                    for e in data.get("elements", [])
                ]
                return SceneAnalysis(
                    raw_description=data.get("description", ""),
                    scene_type=data.get("scene_type", "interior"),
                    style=data.get("style", "realistic"),
                    complexity=data.get("complexity", "medium"),
                    elements=sorted(elements, key=lambda x: x.priority),
                    ue5_tasks=data.get("ue5_tasks", []),
                )
        except Exception as e:
            logger.error(f"Analysis parse error: {e}")

        # Минимальный fallback
        return SceneAnalysis(
            raw_description=llm_output[:500] if llm_output else "Не удалось проанализировать",
            scene_type="interior",
            ue5_tasks=["Создать новый Level", "Добавить базовые меши", "Настроить освещение"],
        )

    def suggest_ue5_workflow(self, analysis: SceneAnalysis) -> list[str]:
        """
        Генерирует упорядоченный список UE5 задач на основе анализа.
        Приоритет: сначала структура, потом детали.
        """
        tasks = []

        # Всегда начинаем с уровня
        tasks.append("Создать новый Level (File > New Level > Basic)")

        # Терраин/экстерьер
        if analysis.scene_type in ("exterior", "terrain", "mixed"):
            tasks.append("Создать Landscape (терраин) через Landscape Mode")
            tasks.append("Применить материал терраина (трава, земля, камень)")
            tasks.append("Добавить растительность через Foliage Mode")

        # Интерьер
        if analysis.scene_type in ("interior", "mixed"):
            floor = next((e for e in analysis.elements if e.category == "floor"), None)
            if floor:
                tasks.append(f"Создать материал пола: {floor.description}")
                tasks.append("Добавить Static Mesh плоскости для пола")

            wall = next((e for e in analysis.elements if e.category == "wall"), None)
            if wall:
                tasks.append(f"Создать материал стен: {wall.description}")
                tasks.append("Добавить Static Mesh стен (4 стены + потолок)")

        # Освещение (всегда)
        tasks.append("Настроить DirectionalLight (основной свет)")
        tasks.append("Настроить SkyLight (атмосферное освещение)")
        tasks.append("Добавить Atmospheric Fog / Sky Atmosphere")

        # Дополнительные элементы
        for el in analysis.elements:
            if el.category == "furniture":
                tasks.append(f"Найти/создать меш: {el.description} (Quixel Bridge или Marketplace)")
            elif el.category == "water":
                tasks.append("Добавить Water Body (Fluid Simulation) или Water Plane")
            elif el.category == "window":
                tasks.append("Добавить окна с прозрачным материалом")

        # Финал
        tasks.append("Настроить Post Process Volume (цвета, глубина резкости)")
        tasks.append("Сохранить всё (Ctrl+Shift+S)")

        return tasks
