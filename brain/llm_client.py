"""
LLM Client — общается с локальным Ollama.
Поддерживает стриминг, fallback модели и офлайн режим.
"""
import json
import requests
from typing import Generator, Optional
from dataclasses import dataclass

from core.config import config
from core.logger import logger


@dataclass
class LLMResponse:
    content: str
    model: str
    success: bool
    error: Optional[str] = None


class LLMClient:
    """
    Клиент для Ollama API.
    Автоматически переключается на fallback модель при ошибке.
    """

    def __init__(self):
        self.host = config.llm.host
        self.model = config.llm.model
        self.fallback = config.llm.fallback_model
        self._available_models: list[str] = []
        self._check_connection()

    def _check_connection(self) -> bool:
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=3)
            if resp.ok:
                data = resp.json()
                self._available_models = [m["name"] for m in data.get("models", [])]
                logger.info(f"Ollama connected. Models: {self._available_models}")
                return True
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
        return False

    def _get_model(self) -> str:
        """Выбирает лучшую доступную модель."""
        if not self._available_models:
            return self.model
        for candidate in [self.model, self.fallback, "qwen2.5:7b", "llama3:8b", "mistral:7b"]:
            for available in self._available_models:
                if candidate.split(":")[0] in available:
                    return available
        return self._available_models[0] if self._available_models else self.model

    def chat(self, messages: list[dict], temperature: float = None) -> LLMResponse:
        """Синхронный запрос к LLM."""
        model = self._get_model()
        temp = temperature if temperature is not None else config.llm.temperature

        payload = {
            "model": model,
            "messages": messages,
            "options": {"temperature": temp},
            "stream": False,
        }

        try:
            resp = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["message"]["content"]
            logger.debug(f"LLM [{model}] response: {content[:80]}...")
            return LLMResponse(content=content, model=model, success=True)

        except requests.exceptions.ConnectionError:
            err = "Ollama не запущен. Запусти: ollama serve"
            logger.error(err)
            return LLMResponse(content="", model=model, success=False, error=err)
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return LLMResponse(content="", model=model, success=False, error=str(e))

    def chat_stream(self, messages: list[dict]) -> Generator[str, None, None]:
        """Стриминг ответа токен за токеном."""
        model = self._get_model()
        payload = {
            "model": model,
            "messages": messages,
            "options": {"temperature": config.llm.temperature},
            "stream": True,
        }
        try:
            with requests.post(
                f"{self.host}/api/chat",
                json=payload,
                stream=True,
                timeout=120,
            ) as resp:
                for line in resp.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield ""

    def complete(self, prompt: str, system: str = "") -> LLMResponse:
        """Простой completion — один промпт."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)
