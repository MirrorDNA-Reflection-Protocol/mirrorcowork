"""
Event-driven filesystem watcher for MirrorCowork.

Uses watchdog for filesystem events instead of polling.
Watches for:
- Handoff completions (handoff.json changes)
- Task completions (completion files in completions/)
- Queue changes (external task submissions)

This is the event-driven heart of MirrorCowork.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


class HandoffWatcher(FileSystemEventHandler):
    """
    Watches for handoff.json changes.

    When handoff.json is modified, triggers registered callbacks.
    This enables event-driven coordination between clients.
    """

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.handoff_path = state_dir / "handoff.json"
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._last_content: str | None = None

    def add_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for handoff changes"""
        self._callbacks.append(callback)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events"""
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.name == "handoff.json":
            self._handle_handoff_change()

    def _handle_handoff_change(self) -> None:
        """Process handoff.json change"""
        try:
            content = self.handoff_path.read_text()

            # Avoid duplicate triggers
            if content == self._last_content:
                return
            self._last_content = content

            data = json.loads(content)

            # Trigger callbacks
            for callback in self._callbacks:
                try:
                    callback(data)
                except Exception:
                    pass  # Don't let one callback break others

        except (json.JSONDecodeError, OSError):
            pass


class CompletionWatcher(FileSystemEventHandler):
    """
    Watches for task completion signals.

    Monitors the completions/ directory for new files that signal
    task completion from external agents (AG, etc).
    """

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.completions_dir = state_dir / "completions"
        self._callbacks: list[Callable[[str, dict[str, Any]], None]] = []

    def add_callback(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Register a callback for completion events"""
        self._callbacks.append(callback)

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle new file creation in completions/"""
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.parent == self.completions_dir and path.suffix == ".json":
            self._handle_completion(path)

    def _handle_completion(self, path: Path) -> None:
        """Process a completion file"""
        try:
            data = json.loads(path.read_text())
            task_id = data.get("task_id", path.stem)

            for callback in self._callbacks:
                try:
                    callback(task_id, data)
                except Exception:
                    pass

        except (json.JSONDecodeError, OSError):
            pass


class EventCoordinator:
    """
    Coordinates all filesystem event watchers.

    This is the main entry point for event-driven operation.
    Start this once and it will handle all filesystem events.
    """

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or Path.home() / ".mirrordna"
        self._observer: Observer | None = None
        self._running = False

        # Watchers
        self.handoff_watcher = HandoffWatcher(self.state_dir)
        self.completion_watcher = CompletionWatcher(self.state_dir)

    def on_handoff(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a handoff change callback"""
        self.handoff_watcher.add_callback(callback)

    def on_completion(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Register a task completion callback"""
        self.completion_watcher.add_callback(callback)

    def start(self) -> None:
        """Start watching for events"""
        if self._running:
            return

        self._observer = Observer()

        # Watch state directory for handoff changes
        self._observer.schedule(
            self.handoff_watcher,
            str(self.state_dir),
            recursive=False,
        )

        # Watch completions directory
        completions_dir = self.state_dir / "completions"
        completions_dir.mkdir(parents=True, exist_ok=True)
        self._observer.schedule(
            self.completion_watcher,
            str(completions_dir),
            recursive=False,
        )

        self._observer.start()
        self._running = True

    def stop(self) -> None:
        """Stop watching for events"""
        if self._observer and self._running:
            self._observer.stop()
            self._observer.join()
            self._running = False

    async def run_async(self) -> None:
        """Run the event loop asynchronously"""
        self.start()
        try:
            while self._running:
                await asyncio.sleep(0.1)  # Yield to event loop
        finally:
            self.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


def create_completion_signal(
    state_dir: Path,
    task_id: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> Path:
    """
    Create a completion signal file.

    External agents can call this to signal task completion,
    which will be picked up by the EventCoordinator.
    """
    from datetime import datetime

    completions_dir = state_dir / "completions"
    completions_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{task_id}.json"

    data = {
        "task_id": task_id,
        "completed_at": datetime.now().isoformat(),
        "result": result,
        "error": error,
    }

    path = completions_dir / filename
    path.write_text(json.dumps(data, indent=2))

    return path
