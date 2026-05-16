"""
MemoryManager — единый интерфейс к памяти ассистента.
Координирует SQLite (workflows, опыт) и ChromaDB (семантический поиск).
"""
from typing import Optional
from brain.intent_parser import Intent
from memory.workflow_store import WorkflowStore
from memory.experience_store import ExperienceStore
from memory.vector_store import VectorStore
from core.logger import logger


class MemoryManager:
    def __init__(self):
        self.workflows = WorkflowStore()
        self.experiences = ExperienceStore()
        self.vectors = VectorStore()
        logger.info("MemoryManager initialized")

    def find_workflow(self, intent: Intent) -> Optional[dict]:
        """
        Ищет подходящий workflow для данного намерения.
        Сначала точный поиск, потом семантический.
        """
        # 1. Точный поиск по action + object_type + name
        exact = self.workflows.find_exact(
            intent.action,
            intent.object_type,
            intent.object_name
        )
        if exact:
            logger.info(f"Exact workflow found: {exact['name']}")
            return exact

        # 2. Семантический поиск через ChromaDB
        if self.vectors.is_available():
            matches = self.vectors.search(intent.raw_text, top_k=3)
            for match in matches:
                if match["score"] >= 0.82:  # порог схожести
                    wf = self.workflows.find_exact(
                        match["action"],
                        match["object_type"]
                    )
                    if wf:
                        logger.info(f"Semantic workflow found: {match['name']} (score={match['score']:.2f})")
                        return wf

        # 3. Поиск только по action
        by_action = self.workflows.find_by_action(intent.action)
        if by_action:
            logger.debug(f"Action-based workflow found: {by_action[0]['name']}")
            return by_action[0]

        return None

    def save_workflow(self, intent: Intent, plan, results: list):
        """Сохраняет успешный workflow в память."""
        name = f"{intent.action}_{intent.object_type}"
        if intent.object_name:
            name += f"_{intent.object_name}"

        # Сериализуем шаги
        steps_data = [
            {
                "step_id": s.step_id,
                "action_type": s.action_type,
                "target": s.target,
                "value": s.value,
                "description": s.description,
                "timeout_ms": s.timeout_ms,
            }
            for s in plan.steps
        ]

        wf_id = self.workflows.save(
            name=name,
            action=intent.action,
            object_type=intent.object_type,
            steps=steps_data,
        )

        # Добавляем в векторный индекс
        self.vectors.add_workflow(
            workflow_id=wf_id,
            name=name,
            action=intent.action,
            object_type=intent.object_type,
            command=intent.raw_text,
        )

        # Записываем в лог опыта
        self.experiences.record(
            action=intent.action,
            object_type=intent.object_type,
            command=intent.raw_text,
            success=True,
            steps=steps_data,
        )

        logger.info(f"Workflow saved to memory: {name} (id={wf_id})")
        return wf_id

    def record_failure(self, intent: Intent, error: str, steps: list = None):
        """Записывает неудачную попытку."""
        self.experiences.record(
            action=intent.action,
            object_type=intent.object_type,
            command=intent.raw_text,
            success=False,
            error=error,
            steps=steps,
        )

    def get_success_rate(self, action: str, object_type: str) -> float:
        return self.experiences.get_success_rate(action, object_type)

    def list_workflows(self) -> list[dict]:
        return self.workflows.get_all()
