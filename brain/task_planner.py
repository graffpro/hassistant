"""
TaskPlanner — разбивает намерение на конкретные шаги для UE5.
"""
import json
from dataclasses import dataclass, field
from typing import Optional

from brain.intent_parser import Intent
from core.logger import logger


@dataclass
class ActionStep:
    """Один шаг выполнения."""
    step_id: int
    action_type: str          # click | type | shortcut | wait | right_click | drag
    target: str               # семантическое описание цели ("Content Browser", "Blueprint Name Field")
    value: Optional[str] = None  # текст для ввода / клавиша
    description: str = ""     # человекочитаемое описание
    timeout_ms: int = 5000
    fallback: Optional[dict] = None  # альтернативный метод


@dataclass
class ActionPlan:
    """Полный план выполнения задачи."""
    intent: Intent
    steps: list[ActionStep] = field(default_factory=list)
    name: str = ""
    estimated_duration_ms: int = 0


PLANNER_SYSTEM = """Ты — планировщик задач для Unreal Engine 5.
Получаешь намерение пользователя и возвращаешь ТОЛЬКО JSON массив шагов.

Каждый шаг:
{
  "step_id": 1,
  "action_type": "click|right_click|type|shortcut|wait|double_click|drag",
  "target": "семантическое название UI элемента UE5",
  "value": "текст или клавиша (если нужно) или null",
  "description": "что делает этот шаг по-русски",
  "timeout_ms": 5000
}

Доступные цели (target):
- "Content Browser" — панель контента
- "Content Browser Search Bar" — строка поиска в Content Browser
- "Content Browser Empty Area" — пустая область Content Browser
- "Blueprint Name Input" — поле ввода имени Blueprint
- "Main Menu > File" — меню File
- "Main Menu > Edit" — меню Edit
- "Toolbar Play Button" — кнопка Play на тулбаре
- "World Outliner" — список объектов мира
- "Details Panel" — панель деталей
- "Output Log" — лог вывода
- "Active Dialog OK Button" — кнопка OK в диалоге
- "Active Dialog Cancel Button" — кнопка Cancel
- "Context Menu > New Blueprint Class" — пункт меню
- "Context Menu > New Folder" — создать папку
- "Context Menu > Save All" — сохранить всё

Shortcuts: Ctrl+S (сохранить), Ctrl+Shift+S (сохранить всё), F5 (Play), Ctrl+Z (отмена), Ctrl+B (Content Browser)

Пример для "создай Blueprint Actor PlayerCharacter":
[
  {"step_id":1,"action_type":"shortcut","target":"Global","value":"Ctrl+B","description":"Открыть Content Browser","timeout_ms":2000},
  {"step_id":2,"action_type":"right_click","target":"Content Browser Empty Area","value":null,"description":"Открыть контекстное меню","timeout_ms":3000},
  {"step_id":3,"action_type":"click","target":"Context Menu > New Blueprint Class","value":null,"description":"Выбрать создание Blueprint","timeout_ms":3000},
  {"step_id":4,"action_type":"click","target":"Blueprint Parent Class > Actor","value":null,"description":"Выбрать родительский класс Actor","timeout_ms":4000},
  {"step_id":5,"action_type":"type","target":"Blueprint Name Input","value":"PlayerCharacter","description":"Ввести имя Blueprint","timeout_ms":3000},
  {"step_id":6,"action_type":"shortcut","target":"Global","value":"Enter","description":"Подтвердить создание","timeout_ms":2000},
  {"step_id":7,"action_type":"shortcut","target":"Global","value":"Ctrl+S","description":"Сохранить Blueprint","timeout_ms":3000}
]
"""


class TaskPlanner:
    def __init__(self, llm, memory):
        self.llm = llm
        self.memory = memory

    def plan(self, intent: Intent, cached_workflow: Optional[dict] = None) -> ActionPlan:
        """Создаёт план выполнения для данного намерения."""
        plan = ActionPlan(intent=intent, name=f"{intent.action}_{intent.object_type}")

        # Если есть кэшированный workflow — используем его
        if cached_workflow and cached_workflow.get("steps"):
            logger.info(f"Using cached workflow: {cached_workflow['name']}")
            plan.steps = self._deserialize_steps(cached_workflow["steps"])
            return plan

        # Встроенные шаблоны для частых задач (без LLM)
        builtin = self._get_builtin_plan(intent)
        if builtin:
            plan.steps = builtin
            logger.info(f"Using builtin plan: {len(builtin)} steps")
            return plan

        # LLM планирование
        prompt = f"""Намерение:
- Действие: {intent.action}
- Тип объекта: {intent.object_type}
- Имя: {intent.object_name or 'не указано'}
- Папка: {intent.target_folder or 'текущая'}
- Родительский класс: {intent.parent_class or 'не указан'}
- Оригинальная команда: {intent.raw_text}

Создай пошаговый план для выполнения этой задачи в Unreal Engine 5."""

        response = self.llm.complete(prompt=prompt, system=PLANNER_SYSTEM)
        if response.success:
            steps = self._parse_steps(response.content)
            if steps:
                plan.steps = steps
                logger.info(f"LLM plan: {len(steps)} steps")
                return plan

        # Fallback — универсальный план
        plan.steps = self._generic_plan(intent)
        logger.warning("Using generic fallback plan")
        return plan

    def _get_builtin_plan(self, intent: Intent) -> Optional[list[ActionStep]]:
        """Встроенные планы для самых частых операций."""
        key = (intent.action, intent.object_type)

        if key == ("create", "Blueprint"):
            name = intent.object_name or "NewBlueprint"
            parent = intent.parent_class or "Actor"
            return [
                ActionStep(1, "shortcut", "Global", "Ctrl+B", "Открыть Content Browser"),
                ActionStep(2, "right_click", "Content Browser Empty Area", None, "Контекстное меню"),
                ActionStep(3, "click", "Context Menu > New Blueprint Class", None, "Создать Blueprint"),
                ActionStep(4, "click", f"Blueprint Parent Class > {parent}", None, f"Выбрать {parent}"),
                ActionStep(5, "type", "Blueprint Name Input", name, f"Имя: {name}"),
                ActionStep(6, "shortcut", "Global", "Return", "Подтвердить"),
                ActionStep(7, "shortcut", "Global", "Ctrl+S", "Сохранить"),
            ]

        if key == ("create", "Folder"):
            name = intent.object_name or "NewFolder"
            return [
                ActionStep(1, "shortcut", "Global", "Ctrl+B", "Открыть Content Browser"),
                ActionStep(2, "right_click", "Content Browser Empty Area", None, "Контекстное меню"),
                ActionStep(3, "click", "Context Menu > New Folder", None, "Создать папку"),
                ActionStep(4, "type", "Folder Name Input", name, f"Имя папки: {name}"),
                ActionStep(5, "shortcut", "Global", "Return", "Подтвердить"),
            ]

        if key == ("save", "Project"):
            return [
                ActionStep(1, "shortcut", "Global", "Ctrl+Shift+S", "Сохранить всё"),
                ActionStep(2, "click", "Active Dialog OK Button", None, "Подтвердить сохранение"),
            ]

        if intent.action == "run":
            return [
                ActionStep(1, "shortcut", "Global", "F5", "Запустить PIE (Play In Editor)"),
            ]

        if intent.action == "compile":
            return [
                ActionStep(1, "shortcut", "Global", "F7", "Скомпилировать Blueprint"),
                ActionStep(2, "wait", "Global", "2000", "Ожидание компиляции"),
            ]

        return None

    def _parse_steps(self, llm_output: str) -> list[ActionStep]:
        """Парсит JSON шаги из ответа LLM."""
        import re, json
        try:
            match = re.search(r'\[.*\]', llm_output, re.DOTALL)
            if match:
                raw = json.loads(match.group())
                return [
                    ActionStep(
                        step_id=s.get("step_id", i + 1),
                        action_type=s.get("action_type", "click"),
                        target=s.get("target", ""),
                        value=s.get("value"),
                        description=s.get("description", ""),
                        timeout_ms=s.get("timeout_ms", 5000),
                    )
                    for i, s in enumerate(raw)
                ]
        except Exception as e:
            logger.error(f"Step parse error: {e}")
        return []

    def _deserialize_steps(self, steps_data) -> list[ActionStep]:
        if isinstance(steps_data, str):
            import json
            steps_data = json.loads(steps_data)
        return [ActionStep(**s) for s in steps_data]

    def _generic_plan(self, intent: Intent) -> list[ActionStep]:
        """Самый базовый fallback план."""
        return [
            ActionStep(1, "shortcut", "Global", "Ctrl+B", "Открыть Content Browser"),
            ActionStep(2, "wait", "Global", "1000", f"Подготовка к: {intent.action} {intent.object_type}"),
        ]
