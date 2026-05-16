"""
ActionValidator — проверяет план перед выполнением.
Блокирует опасные операции, требует подтверждения.
"""
from typing import Optional
from brain.task_planner import ActionPlan
from core.config import config
from core.logger import logger


DANGEROUS_TARGETS = {
    "delete", "remove", "destroy", "clear all", "wipe",
    "удали", "очисти", "сбрось"
}

SAFE_ACTIONS = {
    "create", "open", "save", "compile", "run", "search",
    "import", "rename", "move"
}


class ActionValidator:
    def __init__(self):
        self.cfg = config.safety

    def validate(self, plan: ActionPlan) -> Optional[str]:
        """
        Проверяет план. Возвращает причину блокировки или None если безопасно.
        """
        intent = plan.intent

        # Явно опасные действия
        if intent.action == "delete":
            return f"Удаление '{intent.object_name or intent.object_type}' — требуется подтверждение"

        # Проверка ключевых слов в исходной команде
        raw = intent.raw_text.lower()
        for keyword in self.cfg.destructive_keywords:
            if keyword in raw:
                return f"Команда содержит опасное действие: '{keyword}'"

        # Проверка шагов плана
        for step in plan.steps:
            target_lower = step.target.lower()
            for danger in DANGEROUS_TARGETS:
                if danger in target_lower:
                    return f"Шаг {step.step_id} содержит опасное действие: '{step.target}'"

        # Слишком много шагов — предупреждение (не блокировка)
        if len(plan.steps) > 20:
            logger.warning(f"Large plan: {len(plan.steps)} steps")

        return None  # Безопасно

    def is_destructive(self, action: str) -> bool:
        return action.lower() not in SAFE_ACTIONS

    def requires_ue5_open(self, plan: ActionPlan) -> bool:
        """Проверяет нужен ли открытый UE5 для этого плана."""
        ui_actions = {"click", "right_click", "double_click", "type", "shortcut"}
        return any(s.action_type in ui_actions for s in plan.steps)
