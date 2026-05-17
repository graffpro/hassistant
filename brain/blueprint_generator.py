"""
BlueprintGenerator — генерирует Blueprint логику по текстовому описанию.

Как работает:
  Пользователь: "сделай чтобы персонаж прыгал при нажатии пробела"
  →
  1. LLM генерирует пошаговый план Blueprint нод
  2. Бот открывает Blueprint в UE5
  3. Добавляет ноды через UI автоматизацию
  4. Компилирует

Поддерживает:
  - Input events (клавиши, мышь)
  - Физика (jump, impulse)
  - Таймеры
  - Переменные
  - Print String (отладка)
  - Простые условия (Branch)
"""
import re
import json
from typing import Optional
from dataclasses import dataclass

from core.logger import logger
from core.event_bus import bus, Events


@dataclass
class BlueprintNode:
    node_type: str      # "Event", "Function", "Variable", "Branch", "Print"
    name: str           # Имя ноды ("Event BeginPlay", "Jump", "Print String")
    inputs: dict        # входные пины и их значения
    outputs: list[str]  # к каким нодам подключается
    search_term: str    # что вводить в поиск нод UE5


@dataclass
class BlueprintPlan:
    description: str
    blueprint_name: str
    parent_class: str            # "Character", "Actor", "GameMode"...
    nodes: list[BlueprintNode]
    instructions: list[str]      # человекочитаемые инструкции


class BlueprintGenerator:
    """
    Генерирует Blueprint логику через LLM и выполняет её в UE5.
    """

    def __init__(self, llm, orchestrator):
        self.llm = llm
        self.orchestrator = orchestrator

    def generate(self, description: str, bp_name: str = "",
                 parent_class: str = "") -> Optional[BlueprintPlan]:
        """
        Генерирует план Blueprint по описанию.
        Возвращает BlueprintPlan или None при ошибке.
        """
        logger.info(f"Generating Blueprint: {description!r}")
        bus.emit(Events.STATUS_UPDATE, {
            "status": "thinking",
            "message": f"🔵 Генерирую Blueprint: {description[:60]}...",
        })

        plan = self._ask_llm(description, bp_name, parent_class)
        if plan:
            bus.emit(Events.STATUS_UPDATE, {
                "status": "idle",
                "message": (f"✅ Blueprint план готов: '{plan.blueprint_name}'\n"
                            f"📋 {len(plan.nodes)} нод\n"
                            f"Сказать 'создай его' чтобы применить в UE5"),
            })
        return plan

    def generate_and_apply(self, description: str, bp_name: str = "",
                           parent_class: str = "") -> str:
        """Генерирует Blueprint план и сразу применяет его в UE5."""
        plan = self.generate(description, bp_name, parent_class)
        if not plan:
            return "❌ Не удалось сгенерировать Blueprint план"
        return self.apply_plan(plan)

    def apply_plan(self, plan: BlueprintPlan) -> str:
        """Применяет Blueprint план в открытом UE5 редакторе."""
        if not self.orchestrator.ui_detector.is_ue5_open():
            return "❌ UE5 не открыт"

        bus.emit(Events.STATUS_UPDATE, {
            "status": "executing",
            "message": f"⚡ Применяю Blueprint '{plan.blueprint_name}'...",
        })

        from brain.task_planner import ActionStep, ActionPlan
        from brain.intent_parser import Intent

        steps = self._plan_to_steps(plan)
        intent = Intent(
            raw_text=plan.description,
            action="create",
            object_type="blueprint",
            object_name=plan.blueprint_name,
        )
        action_plan = ActionPlan(intent=intent, steps=steps, name=plan.blueprint_name)
        result = self.orchestrator._execute_plan(action_plan, intent)

        if result.success:
            msg = f"✅ Blueprint '{plan.blueprint_name}' создан и скомпилирован!"
        else:
            msg = f"⚠️ Blueprint создан частично. Проверь ноды вручную."
        return msg

    # ─────────────────────────────────────────────────────────
    # LLM ГЕНЕРАЦИЯ
    # ─────────────────────────────────────────────────────────

    def _ask_llm(self, description: str, bp_name: str,
                 parent_class: str) -> Optional[BlueprintPlan]:
        system = """Ты эксперт по Unreal Engine 5 Blueprint.
Пользователь описывает поведение. Сгенерируй план Blueprint нод.

Верни JSON:
{
  "blueprint_name": "BP_MyActor",
  "parent_class": "Character",
  "description": "Что делает этот Blueprint",
  "instructions": ["Шаг 1: ...", "Шаг 2: ..."],
  "nodes": [
    {
      "node_type": "Event",
      "name": "Event BeginPlay",
      "search_term": "Begin Play",
      "inputs": {},
      "outputs": ["Print String"]
    },
    {
      "node_type": "Function",
      "name": "Print String",
      "search_term": "Print String",
      "inputs": {"In String": "Hello!"},
      "outputs": []
    }
  ]
}

Поддерживаемые типы нод:
- Event: Event BeginPlay, Event Tick, Event AnyKey, InputAction Jump
- Function: Print String, Add Impulse, Jump, Set Actor Location, Delay
- Variable: Get/Set переменных
- Branch: условие if/else
- Math: Add, Multiply, Greater Than

Описывай search_term точно как в поиске нод UE5."""

        prompt = (
            f"Описание: {description}\n"
            + (f"Имя Blueprint: {bp_name}\n" if bp_name else "")
            + (f"Родительский класс: {parent_class}\n" if parent_class else "")
        )

        try:
            resp = self.llm.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ])
            content = resp.content if hasattr(resp, "content") else str(resp)
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if not m:
                return None
            data = json.loads(m.group())

            nodes = [
                BlueprintNode(
                    node_type=n.get("node_type", "Function"),
                    name=n.get("name", ""),
                    search_term=n.get("search_term", n.get("name", "")),
                    inputs=n.get("inputs", {}),
                    outputs=n.get("outputs", []),
                )
                for n in data.get("nodes", [])
            ]

            return BlueprintPlan(
                description=data.get("description", description),
                blueprint_name=data.get("blueprint_name", bp_name or "BP_Generated"),
                parent_class=data.get("parent_class", parent_class or "Actor"),
                nodes=nodes,
                instructions=data.get("instructions", []),
            )
        except Exception as e:
            logger.error(f"Blueprint LLM error: {e}")
            return None

    # ─────────────────────────────────────────────────────────
    # КОНВЕРТАЦИЯ В ACTION STEPS
    # ─────────────────────────────────────────────────────────

    def _plan_to_steps(self, plan: BlueprintPlan) -> list:
        """Конвертирует BlueprintPlan в ActionStep список для executor."""
        from brain.task_planner import ActionStep
        steps = []
        sid = 1

        # 1. Создаём Blueprint если не существует
        steps.append(ActionStep(
            step_id=sid, action_type="create_blueprint",
            target=plan.blueprint_name,
            value=plan.parent_class,
            description=f"Создать Blueprint '{plan.blueprint_name}' ({plan.parent_class})",
            timeout_ms=8000,
        ))
        sid += 1

        # 2. Открываем Blueprint редактор
        steps.append(ActionStep(
            step_id=sid, action_type="open_blueprint",
            target=plan.blueprint_name,
            description=f"Открыть Blueprint Editor для '{plan.blueprint_name}'",
            timeout_ms=5000,
        ))
        sid += 1

        # 3. Добавляем ноды
        for node in plan.nodes:
            steps.append(ActionStep(
                step_id=sid, action_type="add_blueprint_node",
                target=node.search_term,
                value=json.dumps(node.inputs) if node.inputs else None,
                description=f"Добавить ноду: {node.name}",
                timeout_ms=5000,
            ))
            sid += 1

        # 4. Компилируем
        steps.append(ActionStep(
            step_id=sid, action_type="shortcut",
            target="compile_blueprint",
            value="ctrl+shift+f7",
            description="Скомпилировать Blueprint",
            timeout_ms=10000,
        ))
        sid += 1

        # 5. Сохраняем
        steps.append(ActionStep(
            step_id=sid, action_type="shortcut",
            target="save",
            value="ctrl+s",
            description="Сохранить Blueprint",
            timeout_ms=3000,
        ))

        return steps
