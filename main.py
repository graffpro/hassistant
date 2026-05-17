"""
UE5 AI Assistant — Entry Point
"""
import sys
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from core.config import config
from core.logger import setup_logger, logger
from core.event_bus import bus, Events


def main():
    setup_logger(debug=config.debug)
    logger.info(f"Starting {config.app_name} v{config.version}")

    app = QApplication(sys.argv)
    app.setApplicationName(config.app_name)
    app.setApplicationVersion(config.version)
    app.setQuitOnLastWindowClosed(False)

    # ── Modules ──────────────────────────────────────────────
    from memory.memory_manager import MemoryManager
    from brain.llm_client import LLMClient
    from brain.intent_parser import IntentParser
    from brain.task_planner import TaskPlanner
    from brain.context_manager import ContextManager
    from vision.screen_capture import ScreenCapture
    from vision.ui_detector import UIDetector
    from vision.image_analyzer import ImageAnalyzer
    from vision.video_processor import VideoProcessor
    from automation.action_executor import ActionExecutor
    from safety.action_validator import ActionValidator
    from learning.observer import WorkflowObserver
    from brain.web_researcher import WebResearcher
    from brain.autonomous_agent import AutonomousAgent
    from core.updater import AutoUpdater

    logger.info("Initializing modules...")

    memory          = MemoryManager()
    llm             = LLMClient()
    intent_parser   = IntentParser(llm)
    task_planner    = TaskPlanner(llm, memory)
    screen_capture  = ScreenCapture()
    ui_detector     = UIDetector()
    action_executor = ActionExecutor()
    validator       = ActionValidator()
    observer        = WorkflowObserver(memory)
    image_analyzer  = ImageAnalyzer(llm)
    video_processor = VideoProcessor(llm, image_analyzer)
    web_researcher  = WebResearcher(llm, memory)

    # Патч памяти
    def find_workflow_by_text(text: str):
        results = memory.vectors.search(text, top_k=1)
        if results and results[0]["score"] >= 0.80:
            return memory.workflows.find_exact(
                results[0]["action"], results[0]["object_type"]
            )
        return None
    memory.find_workflow_by_text = find_workflow_by_text

    from core.orchestrator import Orchestrator
    orchestrator = Orchestrator(
        memory=memory, llm=llm, intent_parser=intent_parser,
        task_planner=task_planner, screen_capture=screen_capture,
        ui_detector=ui_detector, action_executor=action_executor,
        validator=validator, observer=observer,
    )

    agent = AutonomousAgent(
        orchestrator=orchestrator, image_analyzer=image_analyzer,
        video_processor=video_processor, web_researcher=web_researcher,
        screen_capture=screen_capture, ui_detector=ui_detector, memory=memory,
    )

    # ── UI ───────────────────────────────────────────────────
    from ui.floating_icon import AssistantIcon, MiniChatPopup
    from ui.tray_manager import TrayManager
    from ui.overlay import AssistantOverlay

    icon  = AssistantIcon()
    popup = MiniChatPopup(icon)
    tray  = TrayManager()

    # Полное окно (ленивое создание)
    _full_window = [None]
    def get_full_window():
        if _full_window[0] is None:
            _full_window[0] = AssistantOverlay(orchestrator, agent)
        return _full_window[0]

    # ── Соединяем сигналы ────────────────────────────────────

    # Иконка → попап
    icon.clicked.connect(popup.toggle)

    # Правый клик на иконке → меню трея
    def icon_right_click(pos):
        tray._tray.contextMenu().popup(pos)
    icon.right_clicked.connect(icon_right_click)

    # Чат → оркестратор
    def on_message(text: str):
        bus.emit(Events.USER_MESSAGE, text)
    popup.message_sent.connect(on_message)

    # Ответ оркестратора → чат (всегда в главном потоке через QTimer)
    def on_status(data: dict):
        def _update():
            status  = data.get("status", "idle")
            message = data.get("message", "")
            icon.set_state(status)
            tray.set_state(status)
            if status in ("idle", "error") and message:
                popup.add_message(message, is_user=False)
        QTimer.singleShot(0, _update)
    bus.subscribe(Events.STATUS_UPDATE, on_status)

    # Трей → действия
    tray.show_chat.connect(popup.toggle)
    tray.show_main.connect(lambda: (get_full_window().show(), get_full_window().raise_()))
    tray.quit_app.connect(lambda: (orchestrator.shutdown(), app.quit()))

    # ── Показываем иконку ────────────────────────────────────
    icon.show()
    tray.notify("UE5 AI Assistant", "Ассистент запущен. Нажми на иконку чтобы начать.")

    # ── Авто-обновление (в фоне, через 5 сек после старта) ──
    def check_updates():
        def _status(msg):
            # marshal to main thread
            QTimer.singleShot(0, lambda m=msg: bus.emit(
                Events.STATUS_UPDATE, {"status": "idle", "message": m}
            ))

        def _on_available(version, notes):
            # tray.notify must run in main thread
            QTimer.singleShot(0, lambda v=version, n=notes: tray.notify(
                f"Update available: {v}",
                f"{n[:80]}" if n else "Restart to install"
            ))

        updater = AutoUpdater(on_status=_status, on_update_available=_on_available)
        updater.check_and_update(silent=True)

    QTimer.singleShot(5000, lambda: threading.Thread(
        target=check_updates, daemon=True
    ).start())

    logger.info("UE5 Assistant ready ✓")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
