"""Event-driven coordination (no polling)"""

from mirrorcowork.events.watcher import (
    EventCoordinator,
    HandoffWatcher,
    CompletionWatcher,
    create_completion_signal,
)

__all__ = [
    "EventCoordinator",
    "HandoffWatcher",
    "CompletionWatcher",
    "create_completion_signal",
]
