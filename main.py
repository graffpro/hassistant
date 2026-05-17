"""
UE5 AI Assistant — Entry Point
"""
import sys
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QObject, pyqtSignal

from core.config import config
from core.logger import setup_logger, logger
from core.event_bus import bus, Events


class _Bridge(QObject):
    """Thread-safe bridge: worker threads emit signal → main thread handles it."""
    status_received = pyqtSignal(dict)

_bridge = _Bridge()


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
    from brain.voice_input import VoiceInput
    from brain.blueprint_generator import BlueprintGenerator
    from brain.proactive_assistant import ProactiveAssistant
    from learning.workflow_recorder import WorkflowRecorder
    from unreal.project_scanner import UE5ProjectScanner
    from unreal.git_integration import UE5GitIntegration
    from unreal.plugin_installer import UE5PluginInstaller
    from core.crash_recovery import CrashRecovery
    from core.perf_monitor import PerfMonitor
    from core.updater import AutoUpdater

    logger.info("Initializing modules...")

    # ── Запускаем Ollama автономно (устанавливает если нет) ──
    def _ensure_ollama():
        from core.autonomous_setup import ensure_ollama_running
        import requests as req

        def _status(msg):
            logger.info(msg)

        ok = ensure_ollama_running(status_callback=_status)
        if not ok:
            logger.warning("Ollama not ready — will retry on first LLM call")
            return

        # Прогрев только qwen — llava грузим по требованию, не держим в RAM
        try:
            logger.info("Warming up LLM model...")
            req.post("http://localhost:11434/api/generate",
                     json={"model": "qwen2.5:7b", "prompt": "hi", "stream": False,
                           "keep_alive": "10m"},   # держать 10 мин, потом выгружать
                     timeout=90)
            logger.info("LLM model ready")
        except Exception as e:
            logger.warning(f"Model warmup failed (will load on first use): {e}")

    threading.Thread(target=_ensure_ollama, daemon=True).start()

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
    # Подключаем агент к оркестратору.
    # Теперь полный цикл: задача → память → Epic docs → выполнение → проверка → сохранение
    orchestrator.set_agent(agent)

    # ── Voice Input (Push-to-Talk Alt+V) ────────────────────
    voice = VoiceInput(on_transcribed=lambda text: bus.emit(Events.USER_MESSAGE, text))
    threading.Thread(target=VoiceInput.install_dependencies, daemon=True).start()
    voice.start_ptt()

    # ── Workflow Recorder ────────────────────────────────────
    recorder = WorkflowRecorder(
        llm=llm, memory=memory,
        ui_detector=ui_detector, screen_capture=screen_capture,
    )
    orchestrator.set_recorder(recorder)

    # ── Project Scanner ──────────────────────────────────────
    scanner = UE5ProjectScanner()
    scanner.start()
    orchestrator.set_scanner(scanner)

    # ── Blueprint Generator ───────────────────────────────────
    bp_gen = BlueprintGenerator(llm=llm, orchestrator=orchestrator)
    orchestrator.set_blueprint_generator(bp_gen)

    # ── Git Integration ───────────────────────────────────────
    git = UE5GitIntegration(llm=llm, scanner=scanner)
    threading.Thread(target=git.setup, daemon=True).start()
    orchestrator.set_git(git)

    # ── Plugin Installer ──────────────────────────────────────
    plugin_installer = UE5PluginInstaller(llm=llm, scanner=scanner)
    orchestrator.set_plugin_installer(plugin_installer)

    # ── Proactive Assistant ───────────────────────────────────
    proactive = ProactiveAssistant(
        llm=llm, screen_capture=screen_capture, ui_detector=ui_detector,
        orchestrator=orchestrator, memory=memory, scanner=scanner,
    )
    proactive.start()

    # ── Crash Recovery ────────────────────────────────────────
    crash_recovery = CrashRecovery(
        ui_detector=ui_detector, scanner=scanner,
        memory=memory, orchestrator=orchestrator,
    )
    crash_recovery.start()

    # ── Performance Monitor ───────────────────────────────────
    perf = PerfMonitor()
    perf.start()
    orchestrator.set_perf_monitor(perf)

    # ── Output Log Monitor ───────────────────────────────────
    from unreal.log_monitor import UE5LogMonitor, LogAutoFixer
    auto_fixer = LogAutoFixer(
        llm=llm, memory=memory,
        researcher=web_researcher, orchestrator=orchestrator,
    )
    log_monitor = UE5LogMonitor(on_error=auto_fixer.on_error, poll_interval=2.0)
    log_monitor.start()
    logger.info("Output Log monitor active — watching for UE5 errors")

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

    # Ответ оркестратора → чат через Signal Bridge (единственный надёжный способ)
    def _on_status_main(data: dict):
        """Всегда выполняется в главном UI потоке благодаря QueuedConnection."""
        status  = data.get("status", "idle")
        message = data.get("message", "")
        icon.set_state(status)
        tray.set_state(status)
        # В чат — все значимые сообщения агента + финальные ответы
        agent_statuses = ("researching", "executing", "learning", "verifying", "planning")
        if status in ("idle", "error") and message:
            popup.add_message(message, is_user=False)
        elif status in agent_statuses and message:
            popup.add_message(message, is_user=False)
        elif status == "thinking" and message:
            popup.add_message(message, is_user=False)

    _bridge.status_received.connect(_on_status_main)

    def on_status(data: dict):
        """Вызывается из любого потока — безопасно эмитит сигнал."""
        _bridge.status_received.emit(data)

    bus.subscribe(Events.STATUS_UPDATE, on_status)

    # Трей → действия
    tray.show_chat.connect(popup.toggle)
    tray.show_main.connect(lambda: (get_full_window().show(), get_full_window().raise_()))
    tray.quit_app.connect(lambda: (orchestrator.shutdown(), log_monitor.stop(), app.quit()))

    # ── Глобальные горячие клавиши ───────────────────────────
    def _setup_hotkeys():
        try:
            import keyboard as kb
            # Alt+Space → открыть/закрыть чат
            kb.add_hotkey("alt+space", lambda: QTimer.singleShot(0, popup.toggle))
            # Alt+R → начать/остановить запись workflow
            def _toggle_record():
                if recorder.is_recording():
                    bus.emit(Events.USER_MESSAGE, "стоп запись")
                else:
                    bus.emit(Events.USER_MESSAGE, "начни запись")
            kb.add_hotkey("alt+r", _toggle_record)
            logger.info("Global hotkeys: Alt+Space (chat), Alt+R (record), Alt+V (voice)")
        except ImportError:
            logger.warning("keyboard not installed — global hotkeys disabled")
        except Exception as e:
            logger.warning(f"Hotkeys setup failed: {e}")

    threading.Thread(target=_setup_hotkeys, daemon=True).start()

    # ── Показываем иконку ────────────────────────────────────
    icon.show()
    tray.notify("UE5 AI Assistant",
                "Ассистент запущен!\nAlt+Space — чат | Alt+V — голос | Alt+R — запись")

    # ── Авто-обновление (в фоне, через 10 сек, тихо) ────────
    def check_updates():
        try:
            def _on_available(version, notes):
                QTimer.singleShot(0, lambda v=version, n=notes: tray.notify(
                    f"Update available: {v}",
                    f"{n[:80]}" if n else "Restart to install"
                ))
            updater = AutoUpdater(on_status=lambda m: None,   # silent
                                  on_update_available=_on_available)
            updater.check_and_update(silent=True)
        except Exception as e:
            logger.debug(f"Update check failed (non-critical): {e}")

    QTimer.singleShot(10000, lambda: threading.Thread(
        target=check_updates, daemon=True
    ).start())

    logger.info("UE5 Assistant ready ✓")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
