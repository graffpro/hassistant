"""
IntentParser — понимает смысл команды пользователя.
Извлекает: действие, тип объекта, имя, папку, контекст.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Optional

from core.logger import logger


@dataclass
class Intent:
    """Структурированное намерение пользователя."""
    raw_text: str                        # оригинальная команда
    action: str                          # create | open | delete | move | rename | save | run | import | ...
    object_type: str                     # Blueprint | Material | Actor | Folder | Asset | ...
    object_name: Optional[str] = None    # имя объекта
    target_folder: Optional[str] = None  # папка назначения
    parent_class: Optional[str] = None   # родительский класс (для Blueprint)
    properties: dict = field(default_factory=dict)  # доп. свойства
    confidence: float = 1.0


SYSTEM_PROMPT = """Ты — парсер команд для Unreal Engine 5 AI ассистента.
Пользователь говорит что нужно сделать в UE5, ты разбираешь это на структуру JSON.

Верни ТОЛЬКО валидный JSON (без markdown, без пояснений):
{
  "action": "create|open|delete|move|rename|save|import|run|search|modify|build|compile",
  "object_type": "Blueprint|Material|Actor|StaticMesh|Folder|Level|Widget|Animation|Texture|Sound|ParticleSystem|Asset",
  "object_name": "имя объекта или null",
  "target_folder": "путь/к/папке или null",
  "parent_class": "Actor|Character|Pawn|GameMode|PlayerController или null",
  "properties": {},
  "confidence": 0.0-1.0
}

Примеры:
- "создай Blueprint Actor с именем Player" → {"action":"create","object_type":"Blueprint","object_name":"Player","parent_class":"Actor","target_folder":null,"properties":{},"confidence":0.97}
- "открой материал MI_Rock" → {"action":"open","object_type":"Material","object_name":"MI_Rock","target_folder":null,"parent_class":null,"properties":{},"confidence":0.95}
- "импортируй FBX в папку Meshes" → {"action":"import","object_type":"StaticMesh","object_name":null,"target_folder":"Meshes","parent_class":null,"properties":{"format":"FBX"},"confidence":0.92}
"""


class IntentParser:
    def __init__(self, llm):
        self.llm = llm

    def parse(self, text: str) -> Intent:
        """Парсит команду пользователя через LLM."""
        logger.info(f"Parsing intent: {text!r}")

        # Быстрая проверка по правилам (офлайн fallback)
        quick = self._quick_parse(text)
        if quick and quick.confidence >= 0.9:
            logger.debug(f"Quick parse: {quick.action}/{quick.object_type}")
            return quick

        # LLM парсинг
        response = self.llm.complete(
            prompt=f'Команда пользователя: "{text}"',
            system=SYSTEM_PROMPT,
        )

        if not response.success:
            logger.warning("LLM unavailable, using quick parse")
            return quick or Intent(raw_text=text, action="unknown", object_type="unknown", confidence=0.1)

        intent = self._parse_json(text, response.content)
        logger.info(f"Intent: action={intent.action}, type={intent.object_type}, name={intent.object_name}")
        return intent

    def _parse_json(self, raw_text: str, llm_output: str) -> Intent:
        """Парсит JSON из ответа LLM."""
        try:
            # Извлекаем JSON если он в блоке кода
            match = re.search(r'\{.*\}', llm_output, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return Intent(
                    raw_text=raw_text,
                    action=data.get("action", "unknown"),
                    object_type=data.get("object_type", "Asset"),
                    object_name=data.get("object_name"),
                    target_folder=data.get("target_folder"),
                    parent_class=data.get("parent_class"),
                    properties=data.get("properties", {}),
                    confidence=float(data.get("confidence", 0.8)),
                )
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON parse error: {e} — raw: {llm_output[:100]}")
        return Intent(raw_text=raw_text, action="unknown", object_type="unknown", confidence=0.1)

    def _quick_parse(self, text: str) -> Optional[Intent]:
        """Быстрый rule-based парсер для общих команд."""
        t = text.lower().strip()

        rules = [
            # Создание Blueprint
            (r"создай\s+(blueprint|блюпринт)\s*(?:actor|character|pawn)?\s*(?:с именем|named|по имени)?\s*(\w+)?",
             "create", "Blueprint", "Actor"),
            # Создание папки
            (r"создай\s+папку\s+(\w+)",
             "create", "Folder", None),
            # Открыть
            (r"открой\s+(\w+)",
             "open", "Asset", None),
            # Сохранить всё
            (r"сохрани\s+(всё|все|проект|all)",
             "save", "Project", None),
            # Запустить PIE
            (r"(запусти|play|старт|старт игры)",
             "run", "Level", None),
            # Компиляция
            (r"(компилируй|скомпилируй|build|compile)",
             "compile", "Blueprint", None),
            # Импорт
            (r"(импортируй|import)\s+(\w+)?",
             "import", "Asset", None),
        ]

        for pattern, action, obj_type, parent in rules:
            m = re.search(pattern, t)
            if m:
                name = m.group(m.lastindex) if m.lastindex else None
                return Intent(
                    raw_text=text,
                    action=action,
                    object_type=obj_type,
                    object_name=name,
                    parent_class=parent,
                    confidence=0.88,
                )
        return None
