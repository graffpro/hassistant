"""
WebResearcher — ищет в интернете решения для UE5 задач.
Когда ассистент не знает как что-то сделать — ищет сам.
Приоритет: docs.unrealengine.com → YouTube → Google.
"""
import re
import json
import time
import requests
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus

from core.config import config
from core.logger import logger


@dataclass
class ResearchResult:
    """Результат поиска — инструкция по выполнению задачи."""
    query: str
    source_url: str
    source_type: str            # "docs" | "youtube" | "web"
    instructions: list[str]     # Пошаговые инструкции
    ue5_steps: list[dict]       # Готовые шаги для ActionExecutor
    confidence: float = 0.7
    cached: bool = False


class WebResearcher:
    """
    Автономный исследователь — ищет UE5 туториалы и инструкции.
    Кэширует результаты в SQLite чтобы не искать повторно.
    """

    UE5_DOCS_BASE = "https://docs.unrealengine.com/5.3/en-US"
    SEARCH_ENGINES = [
        "https://docs.unrealengine.com/search/?q={query}",
        "https://www.google.com/search?q={query}+Unreal+Engine+5+tutorial",
    ]

    def __init__(self, llm_client, memory_manager):
        self.llm = llm_client
        self.memory = memory_manager
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self._search_cache: dict[str, ResearchResult] = {}

    def research(self, task: str, context: str = "") -> Optional[ResearchResult]:
        """
        Ищет как выполнить UE5 задачу.
        Возвращает ResearchResult с пошаговыми инструкциями.
        """
        cache_key = task.lower().strip()

        # 1. Проверяем кэш в памяти
        if cache_key in self._search_cache:
            logger.info(f"Research cache hit: {task!r}")
            result = self._search_cache[cache_key]
            result.cached = True
            return result

        # 2. Проверяем долгосрочную память (SQLite)
        cached_wf = self.memory.find_workflow_by_text(task)
        if cached_wf:
            logger.info(f"Found in memory: {task!r}")
            return self._workflow_to_research(cached_wf, task)

        if config.offline_mode:
            logger.info("Offline mode — skipping web search")
            return self._generate_from_llm_only(task, context)

        # 3. Ищем в интернете
        logger.info(f"Researching: {task!r}")
        result = self._search_ue5_docs(task)

        if not result:
            result = self._search_web(task)

        if not result:
            result = self._generate_from_llm_only(task, context)

        if result:
            self._search_cache[cache_key] = result

        return result

    def _search_ue5_docs(self, task: str) -> Optional[ResearchResult]:
        """Ищет в официальной документации Unreal Engine."""
        query = self._task_to_search_query(task)
        search_url = f"https://docs.unrealengine.com/search/?q={quote_plus(query)}"

        try:
            resp = self._session.get(search_url, timeout=8)
            if not resp.ok:
                return None

            # Извлекаем первые результаты
            urls = re.findall(
                r'href="(https://docs\.unrealengine\.com[^"]+)"',
                resp.text
            )
            urls = list(dict.fromkeys(urls))[:3]  # уникальные, первые 3

            if not urls:
                return None

            # Читаем первую страницу
            page_url = urls[0]
            page_resp = self._session.get(page_url, timeout=10)
            if not page_resp.ok:
                return None

            # Извлекаем текст страницы
            text = self._extract_text_from_html(page_resp.text)
            if len(text) < 100:
                return None

            # LLM извлекает шаги из документации
            return self._extract_steps_from_text(task, text, page_url, "docs")

        except Exception as e:
            logger.debug(f"Docs search failed: {e}")
            return None

    def _search_web(self, task: str) -> Optional[ResearchResult]:
        """Общий веб-поиск как fallback."""
        query = self._task_to_search_query(task) + " site:unrealengine.com OR site:youtube.com"
        search_url = f"https://www.google.com/search?q={quote_plus(query)}"

        try:
            resp = self._session.get(search_url, timeout=8)
            if not resp.ok:
                return None

            text = self._extract_text_from_html(resp.text)
            return self._extract_steps_from_text(task, text[:2000], search_url, "web")

        except Exception as e:
            logger.debug(f"Web search failed: {e}")
            return None

    def _generate_from_llm_only(self, task: str, context: str = "") -> ResearchResult:
        """Генерирует инструкции только через LLM (офлайн режим или если поиск не дал результата)."""
        logger.info(f"Generating steps via LLM for: {task!r}")

        system = """Ты эксперт по Unreal Engine 5.
Дай пошаговую инструкцию как выполнить задачу в UE5.

Верни JSON:
{
  "instructions": ["Шаг 1: ...", "Шаг 2: ..."],
  "ue5_steps": [
    {"action_type": "click|shortcut|type|right_click", "target": "UI элемент", "value": null, "description": "описание"}
  ]
}"""

        prompt = f"Задача в UE5: {task}"
        if context:
            prompt += f"\nКонтекст: {context}"

        response = self.llm.complete(prompt=prompt, system=system)

        instructions = [f"Выполнить: {task}"]
        ue5_steps = []

        if response.success:
            try:
                match = re.search(r'\{.*\}', response.content, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    instructions = data.get("instructions", instructions)
                    ue5_steps = data.get("ue5_steps", [])
            except Exception:
                pass

        return ResearchResult(
            query=task,
            source_url="local_llm",
            source_type="llm",
            instructions=instructions,
            ue5_steps=ue5_steps,
            confidence=0.6,
        )

    def _extract_steps_from_text(self, task: str, text: str,
                                  url: str, source_type: str) -> Optional[ResearchResult]:
        """LLM извлекает UE5 шаги из найденного текста."""
        system = """Извлеки из текста пошаговые инструкции для выполнения задачи в Unreal Engine 5.

Верни JSON:
{
  "instructions": ["Шаг 1", "Шаг 2", ...],
  "ue5_steps": [
    {"action_type": "click|shortcut|type|right_click|menu", "target": "UI элемент UE5", "value": null, "description": "описание шага"}
  ],
  "confidence": 0.0-1.0
}"""

        prompt = f"Задача: {task}\n\nНайденный текст:\n{text[:2500]}"
        response = self.llm.complete(prompt=prompt, system=system)

        if not response.success:
            return None

        try:
            match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return ResearchResult(
                    query=task,
                    source_url=url,
                    source_type=source_type,
                    instructions=data.get("instructions", []),
                    ue5_steps=data.get("ue5_steps", []),
                    confidence=float(data.get("confidence", 0.7)),
                )
        except Exception as e:
            logger.error(f"Steps extraction error: {e}")
        return None

    def _task_to_search_query(self, task: str) -> str:
        """Превращает задачу в поисковый запрос."""
        # Убираем лишние слова
        query = re.sub(r'\b(создай|добавь|сделай|открой|нажми|выбери)\b', '', task, flags=re.I)
        query = query.strip() + " Unreal Engine 5"
        return query

    def _extract_text_from_html(self, html: str) -> str:
        """Грубое извлечение текста из HTML."""
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _workflow_to_research(self, workflow: dict, task: str) -> ResearchResult:
        """Конвертирует сохранённый workflow в ResearchResult."""
        steps = workflow.get("steps", [])
        instructions = [s.get("description", "") for s in steps if s.get("description")]
        return ResearchResult(
            query=task,
            source_url="local_memory",
            source_type="memory",
            instructions=instructions,
            ue5_steps=steps,
            confidence=0.9,
            cached=True,
        )
