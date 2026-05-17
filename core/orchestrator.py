"""
Core Orchestrator — координирует все модули для выполнения команд.
Полный pipeline: голос/текст → намерение → план → безопасность → выполнение → обучение.
"""
import threading
from dataclasses import dataclass
from typing import Optional

from core.logger import logger
from core.event_bus import bus, Events
from unreal.ue5_workflows import BUILTIN_WORKFLOWS, find_templates_by_tags, resolve_template_vars
from brain.task_planner import ActionStep, ActionPlan


@dataclass
class CommandResult:
    success: bool
    message: str
    steps_executed: int = 0
    workflow_saved: bool = False


class Orchestrator:
    """
    Центральный координатор.
    Получает команды → оркестрирует все модули → докладывает результат.
    """

    def __init__(self, memory, llm, intent_parser, task_planner,
                 screen_capture, ui_detector, action_executor,
                 validator, observer):
        self.memory = memory
        self.llm = llm
        self.intent_parser = intent_parser
        self.task_planner = task_planner
        self.screen_capture = screen_capture
        self.ui_detector = ui_detector
        self.action_executor = action_executor
        self.validator = validator
        self.observer = observer

        # Подключаем UIDetector к ActionExecutor
        self.action_executor.set_ui_detector(ui_detector)

        # ContextManager для разговорного контекста
        from brain.context_manager import ContextManager
        self.context = ContextManager()

        # Запускаем фоновый захват экрана
        self.screen_capture.start_continuous()

        # Запускаем пассивное наблюдение
        self.observer.start_observing()

        bus.subscribe(Events.USER_MESSAGE, self._on_user_message)
        bus.subscribe(Events.USER_VOICE, self._on_user_message)
        bus.subscribe(Events.CONFIRMATION_NEEDED, self._on_confirmation_needed)

        logger.info("Orchestrator ready")

    def _on_user_message(self, text: str) -> None:
        """Вызывается при получении текстовой или голосовой команды."""
        self.context.add_user_message(text)
        thread = threading.Thread(
            target=self._process_command,
            args=(text,),
            daemon=True
        )
        thread.start()

    def _process_command(self, text: str) -> CommandResult:
        """Полный pipeline обработки команды."""
        logger.info(f"Command: {text!r}")

        # --- Спецкоманды ---
        special = self._handle_special_commands(text)
        if special is not None:
            return special

        self._emit_status("thinking", "Анализирую задачу...")

        try:
            # 1. Парсинг намерения
            intent = self.intent_parser.parse(text)
            bus.emit(Events.INTENT_PARSED, intent)

            # 2. Нужен ли открытый UE5? Если нет — запускаем автономно
            if not self.ui_detector.is_ue5_open():
                self._emit_status("thinking", "🔍 UE5 не открыт — пытаюсь запустить...")
                from core.autonomous_setup import launch_ue5
                launched = launch_ue5(
                    lambda msg: self._emit_status("thinking", msg)
                )
                if launched:
                    # Ждём пока UE5 загрузится (до 90 секунд)
                    import time as _time
                    for _ in range(18):
                        _time.sleep(5)
                        if self.ui_detector.is_ue5_open():
                            self._emit_status("idle", "✅ UE5 запущен! Выполняю задачу...")
                            break
                    else:
                        self._emit_status("idle", "⏳ UE5 запускается. Повтори команду через минуту.")
                        return CommandResult(success=False, message="UE5 still loading")
                else:
                    return CommandResult(success=False, message="UE5 not available")

            # 3. Ищем шаблон в встроенных workflows (быстро и без LLM)
            builtin = self._try_builtin_workflow(intent)

            # 4. Ищем в памяти (обученные workflows)
            cached = None if builtin else self.memory.find_workflow(intent)

            # 5. Планирование
            self._emit_status("planning", "Планирую шаги...")
            if builtin:
                plan = builtin
            else:
                plan = self.task_planner.plan(intent, cached)

            bus.emit(Events.PLAN_READY, plan)
            logger.info(f"Plan ready: {len(plan.steps)} steps")

            # 6. Проверка безопасности
            risk = self.validator.validate(plan)
            if risk:
                bus.emit(Events.CONFIRMATION_NEEDED, {
                    "plan": plan,
                    "reason": risk,
                    "intent": intent,
                })
                return CommandResult(success=False, message=f"Ожидаю подтверждения: {risk}")

            # 7. Выполнение
            result = self._execute_plan(plan, intent)
            return result

        except Exception as e:
            logger.exception(f"Pipeline error: {e}")
            msg = f"Ошибка: {e}"
            self._emit_status("error", msg)
            return CommandResult(success=False, message=msg)

    def _execute_plan(self, plan: ActionPlan, intent) -> CommandResult:
        """Выполняет план шаг за шагом с валидацией."""
        results = []
        total = len(plan.steps)

        for step in plan.steps:
            self._emit_status("executing", f"Шаг {step.step_id}/{total}: {step.description}")
            bus.emit(Events.ACTION_START, step)

            ok, err = self.action_executor.execute(step)

            if not ok:
                logger.warning(f"Step {step.step_id} failed: {err}. Trying fallback...")
                bus.emit(Events.ACTION_FAILURE, {"step": step, "error": err})

                ok, err = self.action_executor.execute_fallback(step)
                if not ok:
                    msg = f"❌ Шаг {step.step_id} не выполнен: {err}"
                    self._emit_status("error", msg)
                    self.memory.record_failure(intent, err)
                    self.context.add_assistant_message(msg)
                    return CommandResult(success=False, message=msg, steps_executed=step.step_id - 1)

            results.append({"step": step, "success": True})
            bus.emit(Events.ACTION_SUCCESS, step)

        # Сохраняем в память
        self.observer.record_workflow(intent, plan, results)

        msg = f"✅ Готово! Выполнено {total} шагов."
        self._emit_status("idle", msg)
        self.context.add_assistant_message(msg)
        return CommandResult(success=True, message=msg, steps_executed=total, workflow_saved=True)

    def _try_builtin_workflow(self, intent) -> Optional[ActionPlan]:
        """Ищет встроенный workflow шаблон по тегам намерения."""
        tags = [intent.action, intent.object_type.lower()]
        templates = find_templates_by_tags(tags)
        if not templates:
            return None

        template = templates[0]
        variables = {
            "name": intent.object_name or f"New{intent.object_type}",
            "folder": intent.target_folder or "",
            "parent": intent.parent_class or "Actor",
        }
        steps_data = resolve_template_vars(template.steps, variables)
        steps = [
            ActionStep(
                step_id=s["step_id"],
                action_type=s["action_type"],
                target=s["target"],
                value=s.get("value"),
                description=s.get("description", ""),
                timeout_ms=s.get("timeout_ms", 5000),
            )
            for s in steps_data
        ]
        plan = ActionPlan(intent=intent, steps=steps, name=template.name)
        logger.info(f"Builtin workflow: {template.name}")
        return plan

    def _handle_special_commands(self, text: str) -> Optional[CommandResult]:
        """Обрабатывает специальные команды ассистента (не UE5)."""
        t = text.lower().strip()

        if any(w in t for w in ["привет", "hello", "hi", "как дела"]):
            msg = "Привет! Готов работать в Unreal Engine 5. Что нужно сделать?"
            self._emit_status("idle", msg)
            self.context.add_assistant_message(msg)
            return CommandResult(success=True, message=msg)

        if any(w in t for w in ["что умеешь", "помощь", "help", "команды"]):
            msg = ("Я умею:\n"
                   "• Создавать Blueprint, Material, Widget, папки\n"
                   "• Импортировать FBX/текстуры\n"
                   "• Запускать/останавливать PIE\n"
                   "• Сохранять проект\n"
                   "• Компилировать Blueprint\n"
                   "• Учиться на твоих действиях и запоминать workflows")
            self._emit_status("idle", msg)
            self.context.add_assistant_message(msg)
            return CommandResult(success=True, message=msg)

        if any(w in t for w in ["список workflow", "что помнишь", "мои workflow"]):
            workflows = self.memory.list_workflows()
            if workflows:
                names = "\n".join(f"• {w['name']} (×{w['success_count']})" for w in workflows[:10])
                msg = f"Запомненные workflows ({len(workflows)}):\n{names}"
            else:
                msg = "Пока не запомнил ни одного workflow. Выполни несколько задач и я запомню."
            self._emit_status("idle", msg)
            self.context.add_assistant_message(msg)
            return CommandResult(success=True, message=msg)

        return None  # Не спецкоманда — обрабатываем как UE5 задачу

    def _on_confirmation_needed(self, data: dict):
        """Schedule confirmation dialog on the main UI thread (bug fix: was called from worker thread)."""
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._show_confirmation_dialog(data))

    def _show_confirmation_dialog(self, data: dict):
        """Show confirmation dialog — must run in main thread."""
        from safety.confirmation_dialog import ConfirmationDialog
        plan   = data.get("plan")
        reason = data.get("reason", "Dangerous operation")
        intent = data.get("intent")

        action_desc = "\n".join(
            f"{s.step_id}. {s.description}" for s in plan.steps[:5]
        )
        if len(plan.steps) > 5:
            action_desc += f"\n... +{len(plan.steps) - 5} more steps"

        confirmed = ConfirmationDialog.ask(action_desc, reason)
        if confirmed and intent:
            threading.Thread(
                target=self._execute_plan,
                args=(plan, intent),
                daemon=True
            ).start()
        else:
            self._emit_status("idle", "❌ Operation cancelled")

    def _emit_status(self, status: str, message: str):
        bus.emit(Events.STATUS_UPDATE, {"status": status, "message": message})

    def shutdown(self):
        """Останавливает все фоновые процессы."""
        self.screen_capture.stop_continuous()
        self.observer.stop_observing()
        logger.info("Orchestrator shutdown")
