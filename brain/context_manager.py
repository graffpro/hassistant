"""
ContextManager — хранит контекст текущей беседы.
Даёт LLM память о предыдущих сообщениях в сессии.
"""
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from core.logger import logger


@dataclass
class Message:
    role: str       # "user" | "assistant" | "system"
    content: str


class ContextManager:
    """
    Скользящее окно контекста разговора.
    Не хранится между сессиями (для этого есть MemoryManager).
    """

    SYSTEM_PROMPT = """Ты — автономный AI-ассистент для Unreal Engine 5.
Ты понимаешь и выполняешь задачи в UE5: создание ассетов, Blueprint, материалов, работу с Content Browser, World Outliner и т.д.
Отвечай кратко и по делу. Если выполняешь задачу — опиши что делаешь.
Если не понял задачу — уточни. Говори на русском языке.

Контекст UE5:
- Content Browser: менеджер всех ассетов проекта
- Blueprint: визуальный скриптинг (логика игры)
- World Outliner: список всех объектов на уровне
- Details Panel: свойства выбранного объекта
- PIE (Play In Editor): режим тестирования игры"""

    def __init__(self, max_messages: int = 20):
        self._messages: deque[Message] = deque(maxlen=max_messages)
        self._ue5_context: dict = {}   # текущий контекст UE5 (открытый проект и т.д.)

    def add_user_message(self, text: str):
        self._messages.append(Message(role="user", content=text))

    def add_assistant_message(self, text: str):
        self._messages.append(Message(role="assistant", content=text))

    def update_ue5_context(self, key: str, value):
        """Обновляет контекст UE5 (напр. текущий открытый Blueprint)."""
        self._ue5_context[key] = value
        logger.debug(f"UE5 context: {key}={value}")

    def get_messages_for_llm(self) -> list[dict]:
        """Формирует список сообщений для LLM API."""
        result = [{"role": "system", "content": self._build_system_prompt()}]
        result.extend({"role": m.role, "content": m.content} for m in self._messages)
        return result

    def _build_system_prompt(self) -> str:
        prompt = self.SYSTEM_PROMPT
        if self._ue5_context:
            ctx_lines = "\n".join(f"- {k}: {v}" for k, v in self._ue5_context.items())
            prompt += f"\n\nТекущий контекст UE5:\n{ctx_lines}"
        return prompt

    def get_last_user_message(self) -> Optional[str]:
        for msg in reversed(list(self._messages)):
            if msg.role == "user":
                return msg.content
        return None

    def clear(self):
        self._messages.clear()
        logger.debug("Context cleared")

    def summary(self) -> str:
        """Краткое резюме контекста для логов."""
        return f"{len(self._messages)} messages in context"
