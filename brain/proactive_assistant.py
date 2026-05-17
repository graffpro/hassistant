"""
ProactiveAssistant — бот сам наблюдает за экраном и предлагает следующий шаг.

Не ждёт команды — анализирует контекст и говорит первым:
  - Открыт Blueprint с ошибкой → "Вижу ошибку компиляции, исправить?"
  - Content Browser пустой → "Проект новый, создать базовую структуру папок?"
  - UE5 долго не сохранялся → "Прошло 20 мин без сохранения, сохранить?"
  - Много предупреждений в логе → "Вижу 15 варнингов, разобраться?"
  - Открыт Material без текстур → "Material пустой, добавить базовые текстуры?"

Частота: проверка каждые 30 сек, предложение не чаще раза в 5 мин.
"""
import time
import threading
from dataclasses import dataclass
from typing import Optional, Callable

from core.logger import logger
from core.event_bus import bus, Events


@dataclass
class Suggestion:
    message: str          # Что предложить пользователю
    action: str           # Что выполнить если согласится
    context: str          # Почему предлагаем
    priority: int = 1     # 1=низкий, 2=средний, 3=высокий


class ProactiveAssistant:
    """
    Следит за состоянием UE5 и проактивно предлагает помощь.
    Молчит если пользователь активно работает — не мешает.
    """

    CHECK_INTERVAL   = 30.0    # проверка каждые 30 сек
    SUGGEST_COOLDOWN = 300.0   # предложение не чаще раза в 5 мин
    IDLE_THRESHOLD   = 60.0    # считаем что пользователь "ждёт" после 60 сек тишины

    def __init__(self, llm, screen_capture, ui_detector,
                 orchestrator, memory, scanner=None):
        self.llm = llm
        self.screen_capture = screen_capture
        self.ui_detector = ui_detector
        self.orchestrator = orchestrator
        self.memory = memory
        self.scanner = scanner

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_suggestion: float = 0
        self._last_user_activity: float = time.time()
        self._last_save_time: float = time.time()
        self._suggestion_callback: Optional[Callable] = None
        self._enabled = True

        # Подписываемся на активность пользователя
        bus.subscribe(Events.USER_MESSAGE, self._on_user_activity)
        bus.subscribe(Events.USER_VOICE,   self._on_user_activity)

    def set_suggestion_callback(self, cb: Callable[[Suggestion], None]):
        """cb вызывается когда есть предложение для пользователя."""
        self._suggestion_callback = cb

    def enable(self, enabled: bool = True):
        self._enabled = enabled

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Proactive assistant started")

    def stop(self):
        self._running = False

    def on_save(self):
        """Вызывается когда проект сохранён."""
        self._last_save_time = time.time()

    # ─────────────────────────────────────────────────────────

    def _on_user_activity(self, _):
        self._last_user_activity = time.time()

    def _loop(self):
        while self._running:
            try:
                if self._enabled:
                    self._check_and_suggest()
            except Exception as e:
                logger.debug(f"Proactive check error: {e}")
            time.sleep(self.CHECK_INTERVAL)

    def _check_and_suggest(self):
        """Проверяет контекст и формирует предложение если нужно."""
        now = time.time()

        # Не мешаем если пользователь активен или уже предлагали недавно
        idle_secs = now - self._last_user_activity
        if idle_secs < self.IDLE_THRESHOLD:
            return
        if now - self._last_suggestion < self.SUGGEST_COOLDOWN:
            return
        if not self.ui_detector.is_ue5_open():
            return

        suggestion = self._analyze_context()
        if suggestion:
            self._last_suggestion = now
            self._emit_suggestion(suggestion)

    def _analyze_context(self) -> Optional[Suggestion]:
        """Анализирует текущее состояние UE5 и формирует предложение."""

        # 1. Давно не сохранялись?
        mins_no_save = (time.time() - self._last_save_time) / 60
        if mins_no_save > 20:
            return Suggestion(
                message=f"⚠️ Прошло {int(mins_no_save)} минут без сохранения. Сохранить проект?",
                action="сохрани",
                context="no_save",
                priority=2,
            )

        # 2. Анализируем скриншот через LLaVA
        screenshot = self.screen_capture.get_latest()
        if not screenshot:
            return None

        context = self._analyze_screenshot(screenshot)
        if not context:
            return None

        # 3. Формируем предложение по контексту
        return self._context_to_suggestion(context)

    def _analyze_screenshot(self, screenshot) -> Optional[dict]:
        """Анализирует скриншот через LLM и определяет контекст UE5."""
        try:
            import base64, cv2, requests as req
            from core.config import config

            _, buf = cv2.imencode(".jpg", screenshot.image,
                                   [cv2.IMWRITE_JPEG_QUALITY, 50])
            img_b64 = base64.b64encode(buf.tobytes()).decode()

            # Пробуем llava если доступен
            payload = {
                "model": "llava:7b",
                "prompt": (
                    "Смотри на этот скриншот Unreal Engine 5. "
                    "Ответь только JSON:\n"
                    '{"panel": "blueprint_editor|content_browser|level_editor|material_editor|output_log|other", '
                    '"has_errors": true/false, '
                    '"is_empty": true/false, '
                    '"suggestion": "короткое предложение что можно сделать или null"}'
                ),
                "images": [img_b64],
                "stream": False,
            }
            resp = req.post(f"{config.llm.host}/api/generate",
                            json=payload, timeout=15)
            if resp.ok:
                import re, json
                text = resp.json().get("response", "")
                m = re.search(r'\{.*\}', text, re.DOTALL)
                if m:
                    return json.loads(m.group())
        except Exception as e:
            logger.debug(f"Screenshot analysis error: {e}")
        return None

    def _context_to_suggestion(self, ctx: dict) -> Optional[Suggestion]:
        """Конвертирует контекст скриншота в предложение."""
        panel   = ctx.get("panel", "other")
        errors  = ctx.get("has_errors", False)
        empty   = ctx.get("is_empty", False)
        llm_sug = ctx.get("suggestion")

        if errors:
            if panel == "blueprint_editor":
                return Suggestion(
                    message="🔴 Вижу ошибку в Blueprint. Попробовать исправить?",
                    action="скомпилируй",
                    context="bp_error",
                    priority=3,
                )
            if panel == "output_log":
                return Suggestion(
                    message="⚠️ В Output Log есть ошибки. Разобраться с ними?",
                    action="покажи ошибки лога",
                    context="log_errors",
                    priority=2,
                )

        if empty and panel == "content_browser":
            return Suggestion(
                message="📂 Content Browser пустой. Создать базовую структуру папок?",
                action="создай папки Blueprints Materials Meshes Textures UI",
                context="empty_project",
                priority=1,
            )

        if panel == "material_editor" and empty:
            return Suggestion(
                message="🟢 Material редактор пустой. Добавить базовые ноды?",
                action="добавь базовые ноды в материал",
                context="empty_material",
                priority=1,
            )

        # Используем подсказку от LLM если есть
        if llm_sug and len(llm_sug) > 10:
            return Suggestion(
                message=f"💡 {llm_sug}",
                action=llm_sug,
                context="llm_suggestion",
                priority=1,
            )

        return None

    def _emit_suggestion(self, suggestion: Suggestion):
        """Отправляет предложение в чат."""
        logger.info(f"Proactive suggestion: {suggestion.message}")

        # Добавляем кнопки "Да" / "Нет" через сообщение
        full_msg = (
            f"{suggestion.message}\n"
            f"_(Напиши 'да' чтобы выполнить)_"
        )
        bus.emit(Events.STATUS_UPDATE, {
            "status": "idle",
            "message": full_msg,
        })

        # Сохраняем действие для ответа "да"
        self._pending_action = suggestion.action

        if self._suggestion_callback:
            self._suggestion_callback(suggestion)
