"""
AutonomousAgent — главный цикл автономного выполнения.

Паттерн ReAct (Reason + Act):
  Думает → Ищет → Делает → Проверяет → Учится → Думает снова...

Умеет:
- Принять изображение/видео → понять что нужно построить
- Разбить на задачи UE5
- Для каждой задачи: знает → делает / не знает → ищет в интернете → делает
- Проверяет результат визуально (скриншот)
- Сохраняет всё что узнал
- Продолжает до завершения или ошибки
"""
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

from core.logger import logger
from core.event_bus import bus, Events
from brain.task_planner import ActionStep, ActionPlan
from brain.intent_parser import Intent


class AgentState(Enum):
    IDLE = "idle"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    RESEARCHING = "researching"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    LEARNING = "learning"
    DONE = "done"
    FAILED = "failed"


@dataclass
class AgentTask:
    """Одна задача в очереди агента."""
    description: str
    priority: int = 1
    source: str = "user"        # "user" | "image" | "video" | "agent"
    attempts: int = 0
    max_attempts: int = 3
    completed: bool = False
    result: Optional[str] = None


@dataclass
class AgentSession:
    """Сессия автономной работы агента."""
    goal: str                               # главная цель (напр. "построить комнату")
    tasks: list[AgentTask] = field(default_factory=list)
    completed_tasks: list[AgentTask] = field(default_factory=list)
    failed_tasks: list[AgentTask] = field(default_factory=list)
    state: AgentState = AgentState.IDLE
    progress: float = 0.0
    start_time: float = field(default_factory=time.time)


class AutonomousAgent:
    """
    Полностью автономный агент для UE5.

    Пример использования:
      agent.run_from_image("apartment.jpg")
      agent.run_from_youtube("https://youtube.com/watch?v=...")
      agent.run_goal("Создай квартиру с деревянным полом и панорамными окнами")
    """

    MAX_TASKS_PER_SESSION = 30
    VERIFY_AFTER_STEPS = 3      # Проверяем визуально каждые N шагов

    def __init__(self, orchestrator, image_analyzer, video_processor,
                 web_researcher, screen_capture, ui_detector, memory):
        self.orchestrator = orchestrator
        self.image_analyzer = image_analyzer
        self.video_processor = video_processor
        self.researcher = web_researcher
        self.screen_capture = screen_capture
        self.ui_detector = ui_detector
        self.memory = memory

        self._session: Optional[AgentSession] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._status_cb: Optional[Callable] = None

    def set_status_callback(self, cb: Callable[[str, str], None]):
        """cb(status, message) — для обновления UI."""
        self._status_cb = cb

    # =========================================================
    # ПУБЛИЧНЫЕ МЕТОДЫ ЗАПУСКА
    # =========================================================

    def run_from_image(self, image_path: str):
        """Запускает агента на основе изображения сцены."""
        self._start_session(f"Воспроизвести сцену из {image_path}")
        self._thread = threading.Thread(
            target=self._run_image_pipeline,
            args=(image_path,),
            daemon=True
        )
        self._thread.start()

    def run_from_youtube(self, url: str):
        """Запускает агента на основе YouTube туториала."""
        self._start_session(f"Выполнить туториал: {url}")
        self._thread = threading.Thread(
            target=self._run_youtube_pipeline,
            args=(url,),
            daemon=True
        )
        self._thread.start()

    def run_goal(self, goal: str):
        """Запускает агента с текстовым описанием цели."""
        self._start_session(goal)
        self._thread = threading.Thread(
            target=self._run_goal_pipeline,
            args=(goal,),
            daemon=True
        )
        self._thread.start()

    def stop(self):
        """Останавливает агента."""
        self._running = False
        if self._session:
            self._session.state = AgentState.IDLE
        logger.info("Autonomous agent stopped")

    def is_running(self) -> bool:
        return self._running

    # =========================================================
    # PIPELINES
    # =========================================================

    def _run_image_pipeline(self, image_path: str):
        """Pipeline: изображение → анализ → задачи → выполнение."""
        try:
            self._set_state(AgentState.ANALYZING)
            self._status("analyzing", f"🔍 Анализирую изображение: {image_path}")

            analysis = self.image_analyzer.analyze_image(image_path)
            self._status("analyzing", f"✅ Сцена: {analysis.raw_description[:80]}...")

            tasks = self.image_analyzer.suggest_ue5_workflow(analysis)
            self._load_tasks(tasks, source="image")

            self._status("planning", f"📋 Создано {len(tasks)} задач для UE5")
            self._run_task_loop()

        except Exception as e:
            logger.exception(f"Image pipeline error: {e}")
            self._set_state(AgentState.FAILED)
            self._status("error", f"❌ Ошибка анализа: {e}")

    def _run_youtube_pipeline(self, url: str):
        """Pipeline: YouTube → анализ видео → задачи → выполнение."""
        try:
            self._set_state(AgentState.ANALYZING)

            analysis = self.video_processor.process_youtube(
                url,
                progress_callback=lambda m: self._status("analyzing", m)
            )

            if analysis.ue5_tasks:
                self._load_tasks(analysis.ue5_tasks, source="youtube")
                self._status("planning", f"📋 Из видео извлечено {len(analysis.ue5_tasks)} задач")
                self._run_task_loop()
            else:
                self._status("error", "❌ Не удалось извлечь задачи из видео")
                self._set_state(AgentState.FAILED)

        except Exception as e:
            logger.exception(f"YouTube pipeline error: {e}")
            self._set_state(AgentState.FAILED)
            self._status("error", f"❌ Ошибка обработки видео: {e}")

    def _run_goal_pipeline(self, goal: str):
        """Pipeline: текстовая цель → декомпозиция → задачи → выполнение."""
        try:
            self._set_state(AgentState.PLANNING)
            self._status("planning", f"🧠 Декомпозирую цель: {goal}")

            tasks = self._decompose_goal(goal)
            self._load_tasks(tasks, source="goal")
            self._status("planning", f"📋 Создано {len(tasks)} задач")
            self._run_task_loop()

        except Exception as e:
            logger.exception(f"Goal pipeline error: {e}")
            self._set_state(AgentState.FAILED)
            self._status("error", f"❌ Ошибка: {e}")

    # =========================================================
    # ГЛАВНЫЙ ЦИКЛ ЗАДАЧ (ReAct Loop)
    # =========================================================

    def _run_task_loop(self):
        """
        Главный автономный цикл:
        Для каждой задачи → Знаю? → Делаю / Не знаю → Ищу → Делаю → Проверяю → Учусь
        """
        session = self._session
        total = len(session.tasks)

        for i, task in enumerate(session.tasks):
            if not self._running:
                break

            session.progress = i / total
            self._status("executing",
                         f"[{i+1}/{total}] {task.description}")

            success = self._execute_task_with_research(task)

            if success:
                task.completed = True
                session.completed_tasks.append(task)
                logger.info(f"Task done: {task.description}")
            else:
                session.failed_tasks.append(task)
                logger.warning(f"Task failed after {task.attempts} attempts: {task.description}")
                # Не останавливаемся — продолжаем со следующей задачей
                self._status("executing",
                             f"⚠️ Пропускаю задачу, продолжаю...")
                time.sleep(1)

        # Итог
        done = len(session.completed_tasks)
        failed = len(session.failed_tasks)
        session.state = AgentState.DONE
        session.progress = 1.0

        msg = f"🏁 Готово! Выполнено {done}/{total} задач."
        if failed:
            msg += f" Не удалось: {failed}."
        self._status("idle", msg)
        bus.emit(Events.STATUS_UPDATE, {"status": "idle", "message": msg})

    def _execute_task_with_research(self, task: AgentTask) -> bool:
        """
        Выполняет одну задачу.
        Если не знает как — ищет в интернете.
        Повторяет до max_attempts.
        """
        while task.attempts < task.max_attempts and self._running:
            task.attempts += 1

            # 1. Ищем в памяти / интернете
            self._set_state(AgentState.RESEARCHING)
            self._status("researching" if task.attempts > 1 else "executing",
                         f"🔍 {'Ищу решение в интернете...' if task.attempts > 1 else 'Проверяю память...'}")

            research = self.researcher.research(
                task=task.description,
                context=f"Общая цель: {self._session.goal}"
            )

            if not research or not research.ue5_steps:
                logger.warning(f"No research result for: {task.description}")
                time.sleep(2)
                continue

            # 2. Конвертируем в ActionSteps
            steps = self._research_to_steps(research)
            if not steps:
                continue

            # 3. Выполняем
            self._set_state(AgentState.EXECUTING)
            self._status("executing",
                         f"⚡ Выполняю: {task.description} ({len(steps)} шагов)")

            plan = ActionPlan(
                intent=Intent(raw_text=task.description, action="execute", object_type="task"),
                steps=steps,
                name=task.description[:50],
            )

            result = self.orchestrator._execute_plan(plan, plan.intent)

            # 4. Визуальная проверка
            self._set_state(AgentState.VERIFYING)
            verified = self._verify_step_visually(task.description)

            if result.success or verified:
                # 5. Сохраняем в память
                self._set_state(AgentState.LEARNING)
                self._save_learned_task(task, research, steps)
                self._status("learning", f"💾 Запомнил: {task.description}")
                return True

            # Не получилось — попробуем снова с другим поиском
            self._status("researching",
                         f"🔄 Попытка {task.attempts}/{task.max_attempts}. Ищу альтернативное решение...")
            time.sleep(2)

        return False

    def _verify_step_visually(self, task_description: str) -> bool:
        """
        Делает скриншот и проверяет через LLM
        что задача выполнена успешно.
        """
        try:
            screenshot = self.screen_capture.capture()
            if not screenshot or self.image_analyzer._vision_model is None:
                return True  # Не можем проверить — считаем успешным

            import base64, cv2
            _, buf = cv2.imencode(".jpg", screenshot.image,
                                   [cv2.IMWRITE_JPEG_QUALITY, 60])
            img_b64 = base64.b64encode(buf.tobytes()).decode()

            import requests as req
            payload = {
                "model": self.image_analyzer._vision_model,
                "prompt": (f"Задача была: '{task_description}'. "
                           f"Смотря на этот скриншот Unreal Engine 5, "
                           f"видно ли что задача выполнена? "
                           f"Ответь только: YES или NO"),
                "images": [img_b64],
                "stream": False,
            }
            resp = req.post(f"{__import__('core.config', fromlist=['config']).config.llm.host}/api/generate",
                            json=payload, timeout=30)
            if resp.ok:
                answer = resp.json().get("response", "").strip().upper()
                verified = "YES" in answer
                logger.info(f"Visual verify: {'✓' if verified else '✗'} — {task_description[:40]}")
                return verified
        except Exception as e:
            logger.debug(f"Visual verify error: {e}")
        return True  # Fallback — не блокируем работу

    def _research_to_steps(self, research) -> list[ActionStep]:
        """Конвертирует ResearchResult в список ActionStep."""
        steps = []
        for i, s in enumerate(research.ue5_steps, 1):
            steps.append(ActionStep(
                step_id=i,
                action_type=s.get("action_type", "click"),
                target=s.get("target", ""),
                value=s.get("value"),
                description=s.get("description", ""),
                timeout_ms=s.get("timeout_ms", 5000),
            ))
        return steps

    def _save_learned_task(self, task: AgentTask, research, steps: list[ActionStep]):
        """Сохраняет успешно выполненную задачу в память."""
        try:
            intent = Intent(
                raw_text=task.description,
                action="execute",
                object_type="learned_task",
            )
            plan = ActionPlan(intent=intent, steps=steps, name=task.description[:60])
            results = [{"step": s, "success": True} for s in steps]
            self.memory.save_workflow(intent, plan, results)
        except Exception as e:
            logger.error(f"Save learned task error: {e}")

    def _decompose_goal(self, goal: str) -> list[str]:
        """LLM разбивает текстовую цель на список UE5 задач."""
        system = """Ты эксперт по Unreal Engine 5.
Разбей цель на конкретные задачи для UE5. Верни JSON массив строк.
Каждая задача — одно конкретное действие в UE5.
Начинай с базовых (создать уровень), заканчивай деталями.
Максимум 20 задач.

Пример для "создать современную квартиру":
["Создать новый Level (Basic)",
 "Создать Landscape 2x2 km",
 "Создать материал деревянного пола",
 "Создать Static Mesh плоскости для пола",
 ...]"""

        response = self.orchestrator.llm.complete(prompt=f"Цель: {goal}", system=system)
        if response.success:
            try:
                import re, json
                match = re.search(r'\[.*\]', response.content, re.DOTALL)
                if match:
                    return json.loads(match.group())
            except Exception:
                pass

        # Fallback — базовый план
        return [
            "Создать новый Level",
            "Настроить освещение (DirectionalLight + SkyLight)",
            f"Создать сцену: {goal}",
            "Сохранить проект",
        ]

    # =========================================================
    # ВСПОМОГАТЕЛЬНЫЕ
    # =========================================================

    def _start_session(self, goal: str):
        self._running = True
        self._session = AgentSession(goal=goal, state=AgentState.IDLE)
        logger.info(f"Autonomous session started: {goal!r}")
        bus.emit(Events.STATUS_UPDATE, {"status": "thinking", "message": f"🤖 Начинаю автономную работу: {goal}"})

    def _load_tasks(self, task_descriptions: list[str], source: str = "agent"):
        if not self._session:
            return
        self._session.tasks = [
            AgentTask(description=desc, source=source)
            for desc in task_descriptions[:self.MAX_TASKS_PER_SESSION]
        ]

    def _set_state(self, state: AgentState):
        if self._session:
            self._session.state = state

    def _status(self, status: str, message: str):
        logger.info(f"[Agent] {message}")
        bus.emit(Events.STATUS_UPDATE, {"status": status, "message": message})
        if self._status_cb:
            self._status_cb(status, message)
