"""
MirrorBrain MCP Bridge

Integrates with the existing MirrorBrain MCP server to pull context
for reflection decisions. This is NOT a replacement for MirrorBrain,
but a bridge that lets ReflectionRouter use its state.

The bridge reads from MirrorBrain's existing filesystem state rather
than making MCP calls directly, keeping this layer independent of
the MCP transport mechanism.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MirrorBrainState(BaseModel):
    """Snapshot of MirrorBrain state"""

    timestamp: str | None = None
    last_client: str | None = None
    last_action: str | None = None
    pending_items: list[str] = Field(default_factory=list)
    context_notes: str | None = None
    services_status: dict[str, Any] = Field(default_factory=dict)
    git_status: dict[str, Any] = Field(default_factory=dict)
    alerts: list[dict[str, Any]] = Field(default_factory=list)


class MirrorBrainBridge:
    """
    Bridge to MirrorBrain state.

    Reads from ~/.mirrordna/ filesystem state to provide context
    for the ReflectionRouter. Does NOT poll — called on-demand
    during reflection phase.
    """

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or Path.home() / ".mirrordna"

    def _read_json(self, path: Path) -> dict[str, Any]:
        """Safely read a JSON file"""
        try:
            if path.exists():
                return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
        return {}

    async def get_system_state(self) -> dict[str, Any]:
        """Get current system state from MirrorBrain files"""
        state = {}

        # Read current_state.json
        current = self._read_json(self.state_dir / "current_state.json")
        if current:
            state["current_state"] = current

        # Read handoff.json
        handoff = self._read_json(self.state_dir / "handoff.json")
        if handoff:
            state["handoff"] = handoff

        # Read services.json
        services = self._read_json(self.state_dir / "services.json")
        if services:
            state["services"] = services

        return state

    async def get_git_status(self) -> dict[str, Any]:
        """Get git status across repos"""
        return self._read_json(self.state_dir / "git_status.json")

    async def get_alerts(self) -> list[dict[str, Any]]:
        """Get current system alerts"""
        alerts_data = self._read_json(self.state_dir / "alerts.json")
        if isinstance(alerts_data, list):
            return alerts_data
        if isinstance(alerts_data, dict) and "alerts" in alerts_data:
            return alerts_data["alerts"]
        return []

    async def get_open_loops(self) -> list[dict[str, Any]]:
        """Get open loops from inbox"""
        inbox_dir = self.state_dir / "inbox"
        loops = []

        if inbox_dir.exists():
            for f in inbox_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                    loops.append(data)
                except (json.JSONDecodeError, OSError):
                    pass

        return loops

    async def get_handoff(self) -> dict[str, Any]:
        """Get current handoff state"""
        return self._read_json(self.state_dir / "handoff.json")

    async def write_handoff(
        self,
        summary: str,
        pending_items: list[str] | None = None,
        context_notes: str | None = None,
        next_client: str | None = None,
    ) -> bool:
        """
        Write a handoff for the next client.

        This integrates with the existing MirrorDNA handoff protocol.
        """
        from datetime import datetime

        handoff = {
            "timestamp": datetime.now().isoformat(),
            "last_client": "mirrorcowork",
            "last_action": summary,
            "pending_items": pending_items or [],
            "context_notes": context_notes,
        }

        if next_client:
            handoff["next_client"] = next_client

        try:
            handoff_path = self.state_dir / "handoff.json"
            handoff_path.write_text(json.dumps(handoff, indent=2))
            return True
        except OSError:
            return False

    def get_full_snapshot(self) -> MirrorBrainState:
        """Get a complete snapshot of MirrorBrain state (sync version)"""
        state = MirrorBrainState()

        # Handoff
        handoff = self._read_json(self.state_dir / "handoff.json")
        if handoff:
            state.timestamp = handoff.get("timestamp")
            state.last_client = handoff.get("last_client")
            state.last_action = handoff.get("last_action")
            state.pending_items = handoff.get("pending_items", [])
            state.context_notes = handoff.get("context_notes")

        # Services
        state.services_status = self._read_json(self.state_dir / "services.json")

        # Git
        state.git_status = self._read_json(self.state_dir / "git_status.json")

        # Alerts
        alerts_data = self._read_json(self.state_dir / "alerts.json")
        if isinstance(alerts_data, list):
            state.alerts = alerts_data
        elif isinstance(alerts_data, dict) and "alerts" in alerts_data:
            state.alerts = alerts_data["alerts"]

        return state


def create_context_provider(state_dir: Path | None = None):
    """
    Create a context provider function for the ReflectionRouter.

    Usage:
        router = ReflectionRouter()
        router.add_context_provider(create_context_provider())
    """
    bridge = MirrorBrainBridge(state_dir)

    def provider() -> dict[str, Any]:
        snapshot = bridge.get_full_snapshot()
        return {
            "system_state": {
                "last_client": snapshot.last_client,
                "last_action": snapshot.last_action,
                "pending_items": snapshot.pending_items,
                "services": snapshot.services_status,
            },
            "git_status": snapshot.git_status,
            "alerts": snapshot.alerts,
        }

    return provider
