"""
ReflectionRouter - The novel core of MirrorCowork

The ReflectionRouter implements a governance layer that sits between task intake
and execution. Instead of blindly routing tasks to agents, it enforces a
reflection phase where tasks can be:

1. Analyzed for safety constraints
2. Checked against the sovereign state (MirrorBrain)
3. Decomposed into subtasks
4. Modified based on context
5. Rejected or escalated

This is NOT another task queue. It's a governance checkpoint that ensures
sovereign control over what agents actually do.

Architecture:
    Task → ReflectionRouter → [Reflection Phase] → Execution Engine
                                     ↓
                              MirrorBrain MCP
                              (context/state)

Event-driven: Uses filesystem watchers (watchdog) instead of polling.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from mirrorcowork.state.task import (
    AgentCapability,
    ReflectionOutcome,
    Task,
    TaskIntent,
    TaskQueue,
)


class ReflectionPolicy(BaseModel):
    """
    Policy that governs how tasks are reflected upon.

    This is the "constitution" of your sovereign stack — rules that
    determine what gets executed, modified, or rejected.
    """

    # Tasks matching these patterns require human approval
    escalation_patterns: list[str] = Field(default_factory=lambda: [
        "delete",
        "remove",
        "destroy",
        "force push",
        "drop table",
        "rm -rf",
        "production",
        "deploy",
    ])

    # Capabilities that require extra scrutiny
    sensitive_capabilities: list[AgentCapability] = Field(default_factory=lambda: [
        AgentCapability.GIT_PUSH,
        AgentCapability.SHELL_EXEC,
    ])

    # Maximum task complexity before decomposition is required
    max_complexity_score: int = 7

    # Clients allowed to skip reflection for certain intents
    trusted_clients: dict[str, list[TaskIntent]] = Field(default_factory=dict)

    # Auto-reject patterns (safety rails)
    rejection_patterns: list[str] = Field(default_factory=lambda: [
        "sudo rm -rf /",
        "format disk",
        "delete all",
    ])


class ReflectionContext(BaseModel):
    """Context gathered during reflection phase"""

    system_state: dict[str, Any] = Field(default_factory=dict)
    git_status: dict[str, Any] = Field(default_factory=dict)
    open_loops: list[dict[str, Any]] = Field(default_factory=list)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    related_tasks: list[str] = Field(default_factory=list)


class ReflectionResult(BaseModel):
    """Result of reflecting on a task"""

    task_id: str
    outcome: ReflectionOutcome
    notes: str
    modifications: dict[str, Any] = Field(default_factory=dict)
    subtasks: list[Task] = Field(default_factory=list)
    context_used: ReflectionContext | None = None
    reflected_at: datetime = Field(default_factory=datetime.now)


class AgentRegistry(BaseModel):
    """Registry of available execution agents and their capabilities"""

    agents: dict[str, set[AgentCapability]] = Field(default_factory=dict)

    def register(self, name: str, capabilities: list[AgentCapability]) -> None:
        """Register an agent with its capabilities"""
        self.agents[name] = set(capabilities)

    def find_capable(self, required: list[AgentCapability]) -> list[str]:
        """Find agents capable of handling the required capabilities"""
        required_set = set(required)
        return [
            name for name, caps in self.agents.items()
            if required_set.issubset(caps)
        ]

    def get_capabilities(self, name: str) -> set[AgentCapability]:
        """Get capabilities of a specific agent"""
        return self.agents.get(name, set())


class ReflectionRouter:
    """
    The ReflectionRouter is the governance core of MirrorCowork.

    It ensures every task passes through a reflection phase before
    execution, maintaining sovereign control over the agentic stack.

    Usage:
        router = ReflectionRouter(state_dir=Path("~/.mirrordna"))
        router.register_agent("claude_code", [AgentCapability.CODE_WRITE, ...])

        # Submit a task
        task = Task(description="Refactor the auth module")
        result = await router.submit(task)

        # Check what happened
        if result.outcome == ReflectionOutcome.PROCEED:
            # Task is queued for execution
            ...
        elif result.outcome == ReflectionOutcome.ESCALATE:
            # Needs human decision
            ...
    """

    def __init__(
        self,
        state_dir: Path | None = None,
        policy: ReflectionPolicy | None = None,
    ):
        self.state_dir = state_dir or Path.home() / ".mirrordna"
        self.queue_path = self.state_dir / "mirrorcowork" / "queue.json"
        self.policy = policy or ReflectionPolicy()
        self.agents = AgentRegistry()
        self.queue = TaskQueue.load(self.queue_path)

        # Callbacks for extensibility
        self._context_providers: list[Callable[[], dict[str, Any]]] = []
        self._reflection_hooks: list[Callable[[Task, ReflectionContext], None]] = []

        # MirrorBrain bridge (lazy-loaded)
        self._mirrorbrain_bridge: Any = None

    def register_agent(self, name: str, capabilities: list[AgentCapability]) -> None:
        """Register an execution agent"""
        self.agents.register(name, capabilities)

    def add_context_provider(self, provider: Callable[[], dict[str, Any]]) -> None:
        """Add a function that provides context for reflection"""
        self._context_providers.append(provider)

    def add_reflection_hook(self, hook: Callable[[Task, ReflectionContext], None]) -> None:
        """Add a hook that runs during reflection"""
        self._reflection_hooks.append(hook)

    async def submit(self, task: Task) -> ReflectionResult:
        """
        Submit a task through the reflection router.

        This is the main entry point. Tasks flow through:
        1. Initial validation
        2. Context gathering
        3. Policy evaluation
        4. Reflection (may involve LLM or human)
        5. Routing decision
        """
        # Add to queue
        self.queue.enqueue(task)
        self.queue.save(self.queue_path)

        # Move to reflection
        self.queue.move_to_reflection(task.id)

        # Gather context
        context = await self._gather_context(task)

        # Run through reflection
        result = await self._reflect(task, context)

        # Apply result to task
        task.mark_reflected(
            outcome=result.outcome,
            notes=result.notes,
            modifications=result.modifications,
        )

        # Complete reflection phase
        self.queue.complete_reflection(task.id)
        self.queue.save(self.queue_path)

        return result

    async def _gather_context(self, task: Task) -> ReflectionContext:
        """Gather context needed for reflection"""
        context = ReflectionContext()

        # Run registered context providers
        for provider in self._context_providers:
            try:
                ctx = provider()
                if "system_state" in ctx:
                    context.system_state.update(ctx["system_state"])
                if "git_status" in ctx:
                    context.git_status.update(ctx["git_status"])
                if "alerts" in ctx:
                    context.alerts.extend(ctx["alerts"])
            except Exception:
                pass  # Context providers shouldn't block reflection

        # Try MirrorBrain if available
        if self._mirrorbrain_bridge:
            try:
                mb_state = await self._mirrorbrain_bridge.get_system_state()
                context.system_state.update(mb_state)
            except Exception:
                pass

        return context

    async def _reflect(self, task: Task, context: ReflectionContext) -> ReflectionResult:
        """
        Core reflection logic.

        This evaluates the task against policy and context to determine
        the appropriate outcome.
        """
        # Run hooks
        for hook in self._reflection_hooks:
            try:
                hook(task, context)
            except Exception:
                pass

        # Check for auto-reject patterns
        desc_lower = task.description.lower()
        for pattern in self.policy.rejection_patterns:
            if pattern.lower() in desc_lower:
                return ReflectionResult(
                    task_id=task.id,
                    outcome=ReflectionOutcome.REJECT,
                    notes=f"Auto-rejected: matches safety pattern '{pattern}'",
                    context_used=context,
                )

        # Check for escalation patterns
        for pattern in self.policy.escalation_patterns:
            if pattern.lower() in desc_lower:
                return ReflectionResult(
                    task_id=task.id,
                    outcome=ReflectionOutcome.ESCALATE,
                    notes=f"Requires human approval: matches pattern '{pattern}'",
                    context_used=context,
                )

        # Check trusted client bypass
        if task.source_client in self.policy.trusted_clients:
            allowed_intents = self.policy.trusted_clients[task.source_client]
            if task.intent in allowed_intents:
                return ReflectionResult(
                    task_id=task.id,
                    outcome=ReflectionOutcome.PROCEED,
                    notes=f"Trusted client bypass for {task.source_client}",
                    context_used=context,
                )

        # Check capability requirements
        if task.required_capabilities:
            sensitive_required = set(task.required_capabilities) & set(
                self.policy.sensitive_capabilities
            )
            if sensitive_required:
                return ReflectionResult(
                    task_id=task.id,
                    outcome=ReflectionOutcome.ESCALATE,
                    notes=f"Requires sensitive capabilities: {sensitive_required}",
                    context_used=context,
                )

        # Check for alerts that might affect this task
        if context.alerts:
            critical_alerts = [a for a in context.alerts if a.get("level") == "critical"]
            if critical_alerts:
                return ReflectionResult(
                    task_id=task.id,
                    outcome=ReflectionOutcome.ESCALATE,
                    notes=f"System has critical alerts: {len(critical_alerts)} issues",
                    context_used=context,
                )

        # Estimate complexity for potential decomposition
        complexity = self._estimate_complexity(task)
        if complexity > self.policy.max_complexity_score:
            return ReflectionResult(
                task_id=task.id,
                outcome=ReflectionOutcome.DECOMPOSE,
                notes=f"Task complexity ({complexity}) exceeds threshold ({self.policy.max_complexity_score})",
                context_used=context,
            )

        # Default: proceed
        return ReflectionResult(
            task_id=task.id,
            outcome=ReflectionOutcome.PROCEED,
            notes="Passed reflection checks",
            context_used=context,
        )

    def _estimate_complexity(self, task: Task) -> int:
        """
        Estimate task complexity for decomposition decisions.

        Simple heuristic based on:
        - Description length
        - Number of capabilities required
        - Keywords indicating multi-step work
        """
        score = 0

        # Length factor
        words = len(task.description.split())
        if words > 50:
            score += 2
        elif words > 20:
            score += 1

        # Capability factor
        score += len(task.required_capabilities)

        # Multi-step indicators
        multi_step_words = ["and", "then", "after", "before", "finally", "also"]
        for word in multi_step_words:
            if f" {word} " in task.description.lower():
                score += 1

        return score

    def get_next_task(self) -> Task | None:
        """Get the next task ready for execution"""
        return self.queue.get_next_ready()

    def complete_task(
        self,
        task_id: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Task | None:
        """Mark a task as completed"""
        task = self.queue.complete_task(task_id, result, error)
        if task:
            self.queue.save(self.queue_path)
        return task

    def get_queue_status(self) -> dict[str, int]:
        """Get current queue status"""
        return {
            "pending": len(self.queue.pending),
            "in_reflection": len(self.queue.in_reflection),
            "ready": len(self.queue.ready),
            "completed": len(self.queue.completed),
        }

    def export_state(self) -> dict[str, Any]:
        """Export full router state for debugging/handoff"""
        return {
            "queue": self.queue.model_dump(),
            "agents": {k: list(v) for k, v in self.agents.agents.items()},
            "policy": self.policy.model_dump(),
            "queue_status": self.get_queue_status(),
        }


# Convenience function for quick task submission
async def route_task(
    description: str,
    source: str = "cli",
    intent: TaskIntent = TaskIntent.EXECUTE,
    state_dir: Path | None = None,
) -> ReflectionResult:
    """Quick helper to route a single task"""
    router = ReflectionRouter(state_dir=state_dir)
    task = Task(
        description=description,
        source_client=source,
        intent=intent,
    )
    return await router.submit(task)
