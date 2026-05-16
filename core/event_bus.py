"""
Internal pub/sub event bus for inter-module communication.
"""
from collections import defaultdict
from typing import Callable, Any
from core.logger import logger


class EventBus:
    """Simple synchronous event bus."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable) -> None:
        self._handlers[event].append(handler)
        logger.debug(f"EventBus: subscribed {handler.__name__} to '{event}'")

    def unsubscribe(self, event: str, handler: Callable) -> None:
        self._handlers[event] = [h for h in self._handlers[event] if h != handler]

    def emit(self, event: str, data: Any = None) -> None:
        logger.debug(f"EventBus: emit '{event}' data={type(data).__name__}")
        for handler in self._handlers.get(event, []):
            try:
                handler(data)
            except Exception as e:
                logger.error(f"EventBus handler error [{event}]: {e}")


# Global singleton
bus = EventBus()

# Event name constants
class Events:
    USER_MESSAGE = "user.message"          # User sent text command
    USER_VOICE = "user.voice"              # User spoke a command
    INTENT_PARSED = "intent.parsed"        # Brain parsed intent
    PLAN_READY = "plan.ready"              # Task plan ready
    ACTION_START = "action.start"          # Action starting
    ACTION_SUCCESS = "action.success"      # Action completed
    ACTION_FAILURE = "action.failure"      # Action failed
    WORKFLOW_LEARNED = "workflow.learned"  # New workflow detected
    STATUS_UPDATE = "status.update"        # UI status update
    CONFIRMATION_NEEDED = "safety.confirm" # Need user confirmation
    SCREENSHOT_TAKEN = "vision.screenshot" # New screenshot available
    UE5_DETECTED = "vision.ue5_detected"  # UE5 window detected
