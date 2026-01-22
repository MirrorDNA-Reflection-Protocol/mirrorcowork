"""Task state models for sovereign agentic governance"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class TaskIntent(str, Enum):
    """The semantic intent behind a task - determines routing behavior"""

    EXECUTE = "execute"      # Direct execution by an agent (Claude Code, AG)
    REFLECT = "reflect"      # Needs human or AI reflection before execution
    DELEGATE = "delegate"    # Route to a specific agent/service
    DEFER = "defer"          # Park for later
    ABORT = "abort"          # Cancel without execution
    COMPOUND = "compound"    # Multi-step task requiring decomposition


class ReflectionOutcome(str, Enum):
    """Result of the reflection phase"""

    PROCEED = "proceed"           # Execute as planned
    MODIFY = "modify"             # Execute with modifications
    ESCALATE = "escalate"         # Needs human decision
    REJECT = "reject"             # Should not be executed
    DECOMPOSE = "decompose"       # Break into subtasks
    CLARIFY = "clarify"           # Need more information


class AgentCapability(str, Enum):
    """Capabilities that agents can have - used for routing"""

    CODE_WRITE = "code_write"
    CODE_READ = "code_read"
    FILE_WRITE = "file_write"
    FILE_READ = "file_read"
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    SHELL_EXEC = "shell_exec"
    WEB_FETCH = "web_fetch"
    MCP_CALL = "mcp_call"
    HUMAN_INTERACT = "human_interact"


class Task(BaseModel):
    """
    A sovereign task unit that flows through the reflection router.

    Tasks are the atomic unit of work in MirrorCowork. They carry:
    - The work description
    - Routing metadata
    - Reflection state
    - Lineage information (where it came from, what it spawned)
    """

    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=datetime.now)

    # Content
    description: str
    context: dict[str, Any] = Field(default_factory=dict)

    # Routing
    intent: TaskIntent = TaskIntent.EXECUTE
    source_client: str = "unknown"
    target_agent: str | None = None
    required_capabilities: list[AgentCapability] = Field(default_factory=list)

    # Reflection state
    reflection_outcome: ReflectionOutcome | None = None
    reflection_notes: str | None = None
    reflection_timestamp: datetime | None = None

    # Modifications from reflection
    modified_description: str | None = None
    modifications: dict[str, Any] = Field(default_factory=dict)

    # Lineage
    parent_task_id: str | None = None
    child_task_ids: list[str] = Field(default_factory=list)

    # Execution state
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def mark_reflected(
        self,
        outcome: ReflectionOutcome,
        notes: str | None = None,
        modifications: dict[str, Any] | None = None,
    ) -> None:
        """Record the reflection outcome"""
        self.reflection_outcome = outcome
        self.reflection_notes = notes
        self.reflection_timestamp = datetime.now()
        if modifications:
            self.modifications = modifications
            if "description" in modifications:
                self.modified_description = modifications["description"]

    def get_effective_description(self) -> str:
        """Get the description to use (modified if reflection changed it)"""
        return self.modified_description or self.description

    def should_execute(self) -> bool:
        """Check if the task should proceed to execution"""
        if self.reflection_outcome is None:
            return self.intent == TaskIntent.EXECUTE
        return self.reflection_outcome in (
            ReflectionOutcome.PROCEED,
            ReflectionOutcome.MODIFY,
        )

    def to_handoff_dict(self) -> dict[str, Any]:
        """Convert to format suitable for MirrorDNA handoff"""
        return {
            "task_id": self.id,
            "description": self.get_effective_description(),
            "intent": self.intent.value,
            "source": self.source_client,
            "target": self.target_agent,
            "reflection": {
                "outcome": self.reflection_outcome.value if self.reflection_outcome else None,
                "notes": self.reflection_notes,
            },
            "created": self.created_at.isoformat(),
        }


class TaskQueue(BaseModel):
    """Persistent queue of tasks stored in ~/.mirrordna/"""

    pending: list[Task] = Field(default_factory=list)
    in_reflection: list[Task] = Field(default_factory=list)
    ready: list[Task] = Field(default_factory=list)
    completed: list[Task] = Field(default_factory=list)

    def enqueue(self, task: Task) -> None:
        """Add a task to pending"""
        self.pending.append(task)

    def move_to_reflection(self, task_id: str) -> Task | None:
        """Move a task from pending to in_reflection"""
        for i, task in enumerate(self.pending):
            if task.id == task_id:
                task = self.pending.pop(i)
                self.in_reflection.append(task)
                return task
        return None

    def complete_reflection(self, task_id: str) -> Task | None:
        """Move a reflected task to ready or completed based on outcome"""
        for i, task in enumerate(self.in_reflection):
            if task.id == task_id:
                task = self.in_reflection.pop(i)
                if task.should_execute():
                    self.ready.append(task)
                else:
                    self.completed.append(task)
                return task
        return None

    def get_next_ready(self) -> Task | None:
        """Get the next task ready for execution"""
        if self.ready:
            return self.ready[0]
        return None

    def complete_task(self, task_id: str, result: dict[str, Any] | None = None, error: str | None = None) -> Task | None:
        """Mark a task as completed"""
        for i, task in enumerate(self.ready):
            if task.id == task_id:
                task = self.ready.pop(i)
                task.completed_at = datetime.now()
                task.result = result
                task.error = error
                self.completed.append(task)
                return task
        return None

    @classmethod
    def load(cls, path: Path) -> TaskQueue:
        """Load queue from disk"""
        if path.exists():
            return cls.model_validate_json(path.read_text())
        return cls()

    def save(self, path: Path) -> None:
        """Persist queue to disk"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))
