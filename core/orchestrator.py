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

        # Автономный агент — подключается позже через set_agent()
        self._agent = None

        # Запускаем фоновый захват экрана
        self.screen_capture.start_continuous()

        # Запускаем пассивное наблюдение
        self.observer.start_observing()

        bus.subscribe(Events.USER_MESSAGE, self._on_user_message)
        bus.subscribe(Events.USER_VOICE, self._on_user_message)
        bus.subscribe(Events.CONFIRMATION_NEEDED, self._on_confirmation_needed)

        logger.info("Orchestrator ready")

    def set_agent(self, agent):
        """Подключает автономный агент (вызывается из main.py после создания обоих)."""
        self._agent = agent
        logger.info("Autonomous agent connected to orchestrator")

    def _on_user_message(self, text: str) -> None:
        """Вызывается при получении текстовой или голосовой команды."""
        self.context.add_user_message(text)
        # Сразу показываем что сообщение получено
        self._emit_status("thinking", "")
        thread = threading.Thread(
            target=self._process_command,
            args=(text,),
            daemon=True
        )
        thread.start()

    def _process_command(self, text: str) -> CommandResult:
        """Pipeline: сначала keyword-matching без LLM, потом LLM только для вопросов."""
        logger.info(f"Command: {text!r}")

        # 1. Спецкоманды (привет, помощь и т.д.)
        special = self._handle_special_commands(text)
        if special is not None:
            return special

        # 2. Прямые команды — keyword matching, БЕЗ LLM
        direct = self._handle_direct_commands(text)
        if direct:
            return direct

        # 3. Вопросы о статусе UE5 — без LLM
        ue5_status = self._handle_ue5_status_question(text)
        if ue5_status:
            return ue5_status

        # 4. Очевидно разговорное — LLM для ответа
        if self._is_conversational_quick(text):
            return self._conversational_response(text)

        # 5. Всё остальное — тоже пробуем keyword matching расширенный
        extended = self._handle_extended_commands(text)
        if extended:
            return extended

        # 6. LLM только для КЛАССИФИКАЦИИ (возвращает JSON action, не текст)
        self._emit_status("thinking", "")
        classified = self._classify_intent_with_llm(text)
        action = classified.get("action", "question")
        name   = classified.get("name", "")
        logger.info(f"LLM classified: action={action!r} name={name!r}")

        # 7. Диспетчер: action → выполнение (никогда не генерируем текст на UE5 команду)
        try:
            action_map = {
                "launch_ue5":           lambda: self._handle_direct_commands("запусти уе5"),
                "save_project":         lambda: self._handle_direct_commands("сохрани"),
                "play_pie":             lambda: self._handle_direct_commands("запусти игру"),
                "stop_pie":             lambda: self._do_stop_pie(),
                "compile":              lambda: self._do_compile(),
                "open_content_browser": lambda: self._do_open_cb(),
                "create_blueprint":     lambda: self._quick_action("create_blueprint", name or "NewBlueprint"),
                "create_material":      lambda: self._quick_action("create_material",  name or "NewMaterial"),
                "create_widget":        lambda: self._quick_action("create_widget",     name or "NewWidget"),
                "create_folder":        lambda: self._quick_action("create_folder",     name or "NewFolder"),
                "import_fbx":           lambda: self._quick_action("import_fbx",        ""),
            }
            if action in action_map:
                result = action_map[action]()
                if result:
                    return result
        except Exception as e:
            logger.exception(f"Action dispatch error: {e}")

        # 8. Сложная UE5 задача → автономный агент
        #    (ищет решение, выполняет, проверяет, запоминает)
        if action != "question" and self._agent:
            return self._run_autonomous(text)

        # 9. Разговорный вопрос → короткий ответ
        return self._conversational_response(text)

    def _run_autonomous(self, goal: str) -> CommandResult:
        """
        Запускает автономный агент для сложной задачи:
        память → Epic docs → выполнение → визуальная проверка → сохранение.
        """
        msg = f"🤖 Работаю автономно: {goal[:60]}..."
        self._emit_status("thinking", msg)
        self.context.add_assistant_message(msg)
        # Агент работает в своём потоке, статусы идут через event bus → чат
        self._agent.run_goal(goal)
        return CommandResult(success=True, message=msg)

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

    def _is_conversational_quick(self, text: str) -> bool:
        """Быстрая проверка без LLM — явно разговорные фразы."""
        t = text.lower().strip()
        quick_patterns = [
            "как ты", "как дела", "что делаешь", "ты понял", "понял меня",
            "что происходит", "кто ты", "что ты", "ты умеешь",
            "что умеешь", "привет", "hello", "спасибо", "молодец",
            "окей", "ладно", "хорошо", "понятно", "отлично", "супер",
            "нуу", "нууу", "помощь",
        ]
        for pat in quick_patterns:
            if t.startswith(pat) or f" {pat}" in t or t == pat.strip():
                return True
        return False

    def _handle_direct_commands(self, text: str):
        """
        Прямые команды без LLM — мгновенное выполнение.
        Запуск UE5, сохранение, PIE, папки и т.д.
        """
        t = text.lower().strip()

        # ── ЗАПУСК UE5 ───────────────────────────────────────
        launch_triggers = [
            # латиница
            "запусти ue5", "запусти unreal", "запустить ue5",
            "открой ue5", "открой unreal", "старт ue5",
            "launch ue5", "open ue5", "start ue5",
            # кириллица (УЕ5, УЕ, Анрил, Унреал)
            "запусти уе5", "запусти уе", "запустить уе",
            "открой уе5", "открой уе",
            "запусти анрил", "запусти унреал", "запусти анреал",
            "запусти редактор", "запусти движок",
            "запустить редактор", "запустить движок",
            "мне надо что бы ты запустил", "запусти его",
            "нужно запустить", "нужен ue5", "нужен уе5",
        ]
        if any(t == tr or t.startswith(tr) or tr in t for tr in launch_triggers):
            if self.ui_detector.is_ue5_open():
                msg = "✅ UE5 уже запущен и готов!"
                self._emit_status("idle", msg)
                return CommandResult(success=True, message=msg)
            self._emit_status("thinking", "🔍 Ищу Unreal Engine 5...")
            from core.autonomous_setup import launch_ue5
            result = launch_ue5(lambda m: self._emit_status("thinking", m))
            if result == "launched":
                msg = "⏳ UE5 запускается... подожди 30-60 секунд, потом повтори команду."
            elif result == "launcher_opened":
                msg = ("🚀 Epic Launcher открыт и настроен.\n"
                       "Войди в аккаунт Epic Games — после этого я автоматически\n"
                       "нажму Install UE5 на D:\\Epic Games (~30GB, 30-60 мин).")
            else:
                msg = "📥 Скачиваю Epic Games Launcher... следи за статусом в чате."
            self._emit_status("idle", msg)
            self.context.add_assistant_message(msg)
            return CommandResult(success=True, message=msg)

        # ── СОХРАНИТЬ ПРОЕКТ ─────────────────────────────────
        save_triggers = ["сохрани", "save all", "сохранить всё", "ctrl+s"]
        if any(tr in t for tr in save_triggers) and self.ui_detector.is_ue5_open():
            import pyautogui, time
            pyautogui.hotkey("ctrl", "shift", "s")
            time.sleep(0.5)
            msg = "✅ Проект сохранён (Ctrl+Shift+S)"
            self._emit_status("idle", msg)
            return CommandResult(success=True, message=msg)

        # ── PIE: ЗАПУСК ИГРЫ ─────────────────────────────────
        play_triggers = ["запусти игру", "play", "запусти пие", "старт пие", "запусти пиай", "нажми плей"]
        if any(tr in t for tr in play_triggers) and self.ui_detector.is_ue5_open():
            import pyautogui, time
            pyautogui.press("F5") if "stop" not in t else pyautogui.press("F8")
            msg = "✅ PIE запущен (F5)"
            self._emit_status("idle", msg)
            return CommandResult(success=True, message=msg)

        return None  # не прямая команда

    # ─────────────────────────────────────────────────────────────
    # РАСШИРЕННЫЕ KEYWORD КОМАНДЫ
    # ─────────────────────────────────────────────────────────────

    def _handle_extended_commands(self, text: str):
        """
        Второй слой keyword matching — Blueprint, Material, FBX, папки, compile и т.д.
        Вызывается ДО LLM, чтобы LLM обрабатывал только настоящие вопросы.
        """
        t = text.lower().strip()

        # ── СТОП PIE ────────────────────────────────────────────
        stop_triggers = [
            "останови игру", "стоп пие", "stop pie", "остановить игру",
            "выйди из игры", "стоп игру", "выключи игру", "стоп плей",
        ]
        if any(tr in t for tr in stop_triggers) and self.ui_detector.is_ue5_open():
            return self._do_stop_pie()

        # ── COMPILE ──────────────────────────────────────────────
        compile_triggers = [
            "скомпилируй", "compile", "скомпилировать", "нажми компайл",
            "скомпилируй блюпринт", "compile blueprint",
        ]
        if any(tr in t for tr in compile_triggers) and self.ui_detector.is_ue5_open():
            return self._do_compile()

        # ── CONTENT BROWSER ──────────────────────────────────────
        cb_triggers = [
            "открой контент", "content browser", "контент браузер",
            "открой контент браузер", "покажи контент", "открой браузер ресурсов",
        ]
        if any(tr in t for tr in cb_triggers) and self.ui_detector.is_ue5_open():
            return self._do_open_cb()

        # ── CREATE BLUEPRINT ─────────────────────────────────────
        bp_triggers = [
            "создай blueprint", "создай блюпринт", "новый blueprint",
            "новый блюпринт", "создать blueprint", "создать блюпринт",
            "create blueprint", "создай bp", "новый бп",
        ]
        if any(tr in t for tr in bp_triggers):
            name = self._extract_name(text, bp_triggers) or "NewBlueprint"
            return self._quick_action_checked("create_blueprint", name)

        # ── CREATE MATERIAL ──────────────────────────────────────
        mat_triggers = [
            "создай material", "создай материал", "новый material",
            "новый материал", "создать материал", "create material",
        ]
        if any(tr in t for tr in mat_triggers):
            name = self._extract_name(text, mat_triggers) or "NewMaterial"
            return self._quick_action_checked("create_material", name)

        # ── CREATE WIDGET ────────────────────────────────────────
        wgt_triggers = [
            "создай widget", "создай виджет", "новый widget",
            "новый виджет", "создать виджет", "create widget",
        ]
        if any(tr in t for tr in wgt_triggers):
            name = self._extract_name(text, wgt_triggers) or "NewWidget"
            return self._quick_action_checked("create_widget", name)

        # ── CREATE FOLDER ─────────────────────────────────────────
        folder_triggers = [
            "создай папку", "новая папка", "создать папку",
            "create folder", "новый folder", "сделай папку",
        ]
        if any(tr in t for tr in folder_triggers):
            name = self._extract_name(text, folder_triggers) or "NewFolder"
            return self._quick_action_checked("create_folder", name)

        # ── IMPORT FBX / FILE ────────────────────────────────────
        import_triggers = [
            "импортируй", "import fbx", "импорт fbx", "импортировать",
            "import file", "добавь модель", "добавь fbx", "загрузи модель",
        ]
        if any(tr in t for tr in import_triggers):
            return self._quick_action_checked("import_fbx", "")

        return None

    def _do_stop_pie(self) -> CommandResult:
        import pyautogui
        pyautogui.press("escape")
        msg = "✅ PIE остановлен"
        self._emit_status("idle", msg)
        return CommandResult(success=True, message=msg)

    def _do_compile(self) -> CommandResult:
        import pyautogui
        pyautogui.hotkey("ctrl", "shift", "f7")  # UE5 Compile All
        import time; time.sleep(0.5)
        msg = "✅ Компиляция запущена (Ctrl+Shift+F7)"
        self._emit_status("idle", msg)
        return CommandResult(success=True, message=msg)

    def _do_open_cb(self) -> CommandResult:
        import pyautogui
        pyautogui.hotkey("ctrl", "space")
        msg = "✅ Content Browser открыт"
        self._emit_status("idle", msg)
        return CommandResult(success=True, message=msg)

    def _extract_name(self, text: str, triggers: list) -> str:
        """Извлекает имя объекта из команды, убирая триггерную фразу."""
        t = text.strip()
        t_lower = t.lower()
        for trigger in sorted(triggers, key=len, reverse=True):
            idx = t_lower.find(trigger)
            if idx >= 0:
                after = t[idx + len(trigger):].strip()
                if after:
                    word = after.split()[0]
                    # Убираем знаки препинания
                    word = word.strip(".,!?;:")
                    if len(word) > 1:
                        return word[0].upper() + word[1:]
        return ""

    def _quick_action_checked(self, action_type: str, name: str) -> CommandResult:
        """Выполняет UE5 действие, проверяя сначала что UE5 открыт."""
        if not self.ui_detector.is_ue5_open():
            msg = "❌ UE5 не открыт. Скажи 'запусти UE5' и я запущу его."
            self._emit_status("idle", msg)
            return CommandResult(success=False, message=msg)
        return self._quick_action(action_type, name)

    def _quick_action(self, action_type: str, name: str) -> CommandResult:
        """Выполняет простое UE5 действие напрямую через action_executor."""
        from brain.task_planner import ActionStep
        self._emit_status("thinking", f"⚙️ Выполняю {action_type}...")
        step = ActionStep(
            step_id=1, action_type=action_type, target=name,
            value=None, description=f"{action_type} {name}", timeout_ms=15000,
        )
        ok, err = self.action_executor.execute(step)
        labels = {
            "create_blueprint": f"✅ Blueprint '{name}' создан в Content Browser",
            "create_material":  f"✅ Material '{name}' создан",
            "create_widget":    f"✅ Widget '{name}' создан",
            "create_folder":    f"✅ Папка '{name}' создана",
            "import_fbx":       "✅ Открыт диалог импорта — выбери файл",
        }
        msg = labels.get(action_type, "✅ Готово!") if ok else f"❌ Ошибка: {err}"
        self._emit_status("idle" if ok else "error", msg)
        self.context.add_assistant_message(msg)
        return CommandResult(success=ok, message=msg)

    # ─────────────────────────────────────────────────────────────
    # LLM КАК КЛАССИФИКАТОР (не генератор ответов!)
    # ─────────────────────────────────────────────────────────────

    def _classify_intent_with_llm(self, text: str) -> dict:
        """
        Главный принцип: LLM только определяет ЧТО хочет пользователь.
        Возвращает JSON {action, name} — никогда не генерирует текстовый ответ.
        Именно так работает Claude: понимаю смысл → выполняю действие.
        """
        prompt = (
            f'Пользователь написал: "{text}"\n\n'
            "Определи что он хочет. Верни ТОЛЬКО JSON без объяснений:\n"
            '{"action": "<действие>", "name": "<имя или пусто>"}\n\n'
            "Возможные действия:\n"
            "- launch_ue5           — запустить/открыть Unreal Engine\n"
            "- create_blueprint     — создать Blueprint\n"
            "- create_material      — создать Material\n"
            "- create_widget        — создать Widget\n"
            "- create_folder        — создать папку\n"
            "- import_fbx           — импортировать FBX/файл\n"
            "- save_project         — сохранить проект\n"
            "- play_pie             — запустить игру (Play In Editor)\n"
            "- stop_pie             — остановить игру\n"
            "- compile              — скомпилировать Blueprint\n"
            "- open_content_browser — открыть Content Browser\n"
            "- question             — вопрос или разговор (НЕ команда UE5)\n\n"
            "Верни только JSON. Никаких объяснений."
        )
        default = {"action": "question", "name": ""}
        try:
            resp = self.llm.chat([
                {"role": "system",
                 "content": "Ты классификатор команд для Unreal Engine 5. "
                            "Отвечай только JSON."},
                {"role": "user", "content": prompt},
            ])
            content = resp.content if hasattr(resp, "content") else str(resp)
            import json, re
            m = re.search(r"\{[^}]+\}", content, re.DOTALL)
            if m:
                data = json.loads(m.group())
                if "action" in data:
                    return data
        except Exception as e:
            logger.warning(f"LLM classify error: {e}")
        return default

    def _handle_ue5_status_question(self, text: str):
        """Мгновенный ответ на вопросы о статусе UE5 — без LLM."""
        t = text.lower()
        status_keywords = [
            "запущен", "открыт", "работает", "running", "open",
            "унреал", "unreal", "ue5", "ue 5", "енджин", "engine"
        ]
        question_keywords = ["?", "запущен", "открыт", "работает", "есть"]
        is_status_q = (
            any(k in t for k in status_keywords) and
            any(k in t for k in question_keywords)
        )
        if not is_status_q:
            return None
        if self.ui_detector.is_ue5_open():
            msg = "✅ Да, Unreal Engine 5 запущен и готов к работе."
        else:
            msg = "❌ Unreal Engine 5 сейчас не запущен.\nСкажи 'запусти UE5' и я запущу его."
        self._emit_status("idle", msg)
        self.context.add_assistant_message(msg)
        return CommandResult(success=True, message=msg)

    def _is_conversational(self, text: str, intent) -> bool:
        """True если запрос разговорный, а не UE5 команда."""
        t = text.lower().strip()

        # Явно разговорные паттерны
        conversational_patterns = [
            "что делаешь", "как дела", "ты понял", "понял меня",
            "что происходит", "расскажи", "объясни", "кто ты",
            "что ты", "как ты", "ты умеешь", "что умеешь",
            "what are you", "who are you", "how are you",
            "нуyyy", "нуу", "ладно", "окей", "хорошо",
            "спасибо", "молодец", "отлично", "понятно",
        ]
        for pat in conversational_patterns:
            if pat in t:
                return True

        # Непонятное намерение
        action = str(intent.action).lower() if intent.action else "none"
        obj = str(intent.object_type).lower() if intent.object_type else "none"
        if action in ("none", "unknown", "null") and obj in ("none", "null", "asset", ""):
            return True

        return False

    def _conversational_response(self, text: str) -> CommandResult:
        """Разговорный ответ через LLM когда запрос не является UE5 командой."""
        try:
            self._emit_status("thinking", "💬 Думаю...")
            messages = [
                {"role": "system", "content":
                    "Ты UE5 ассистент. Отвечай коротко, 1-3 предложения, по-русски."},
                {"role": "user", "content": text}
            ]
            resp = self.llm.chat(messages)
            response = resp.content if hasattr(resp, "content") else str(resp)
            msg = response.strip() if response else (
                "Я UE5 ассистент! Скажи что сделать — например:\n"
                "• 'Создай Blueprint GameMode'\n"
                "• 'Открой Content Browser'\n"
                "• 'Запусти игру'"
            )
        except Exception as e:
            logger.warning(f"Conversational LLM error: {e}")
            msg = ("Привет! Я помогаю с Unreal Engine 5.\n"
                   "Скажи что нужно сделать — создать Blueprint, импортировать файл, запустить PIE...")
        self._emit_status("idle", msg)
        self.context.add_assistant_message(msg)
        return CommandResult(success=True, message=msg)

    def _emit_status(self, status: str, message: str):
        bus.emit(Events.STATUS_UPDATE, {"status": status, "message": message})

    def shutdown(self):
        """Останавливает все фоновые процессы."""
        self.screen_capture.stop_continuous()
        self.observer.stop_observing()
        logger.info("Orchestrator shutdown")
