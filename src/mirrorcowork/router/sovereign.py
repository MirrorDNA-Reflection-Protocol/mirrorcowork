"""
Sovereign Router - The Full Stack

This integrates all three dream layers:
1. Temporal Sovereignty - causal chain tracking
2. Intent Crystallization - refining vague intents
3. Conscience Layer - ethical memory and checks

The SovereignRouter wraps the ReflectionRouter with these deeper capabilities.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mirrorcowork.router.reflection import (
    ReflectionContext,
    ReflectionPolicy,
    ReflectionResult,
    ReflectionRouter,
)
from mirrorcowork.sovereignty.conscience import Conscience, EthicalCheck
from mirrorcowork.sovereignty.crystallization import (
    CrystallizationEngine,
    IntentCrystal,
)
from mirrorcowork.sovereignty.temporal import (
    IntentGraph,
    TemporalNode,
    predict_implications,
)
from mirrorcowork.state.task import ReflectionOutcome, Task


class SovereignResult(BaseModel):
    """
    Result of sovereign routing - includes all three layers of analysis.
    """

    task_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Basic reflection result
    reflection: ReflectionResult | None = None

    # Crystal (refined intent)
    crystal: IntentCrystal | None = None
    intent_clarity: str | None = None

    # Ethical check
    ethical_check: EthicalCheck | None = None
    conscience_memories: int = 0

    # Temporal analysis
    causal_impact: dict[str, Any] = Field(default_factory=dict)
    would_contradict: list[str] = Field(default_factory=list)

    # Final verdict
    verdict: str = "unknown"       # "proceed", "clarify", "reconsider", "block"
    explanation: str | None = None

    # If clarification needed
    clarification_needed: list[str] = Field(default_factory=list)

    def should_proceed(self) -> bool:
        """Check if the task should proceed"""
        return self.verdict == "proceed"


class SovereignRouter:
    """
    The full sovereign router with all dream layers.

    Usage:
        router = SovereignRouter()
        result = await router.route("Delete the auth module and rewrite from scratch")

        if not result.should_proceed():
            print(f"Blocked: {result.explanation}")
            print(f"Conscience recalls: {result.conscience_memories} relevant memories")
            print(f"Would contradict: {result.would_contradict}")
            if result.clarification_needed:
                print(f"Need clarification on: {result.clarification_needed}")
    """

    def __init__(
        self,
        state_dir: Path | None = None,
        policy: ReflectionPolicy | None = None,
    ):
        self.state_dir = state_dir or Path.home() / ".mirrordna" / "mirrorcowork"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Core components
        self.reflection_router = ReflectionRouter(
            state_dir=state_dir or Path.home() / ".mirrordna",
            policy=policy,
        )
        self.conscience = Conscience(state_dir=self.state_dir)
        self.crystallizer = CrystallizationEngine()

        # Temporal graph
        self.graph_path = self.state_dir / "intent_graph.json"
        self.intent_graph = IntentGraph.load(self.graph_path)

    async def route(
        self,
        description: str,
        source: str = "unknown",
        context: dict[str, Any] | None = None,
        files_affected: list[str] | None = None,
    ) -> SovereignResult:
        """
        Route a task through all three sovereign layers.

        1. Crystallize the intent
        2. Check with conscience
        3. Analyze temporal impact
        4. Run through basic reflection
        5. Generate final verdict
        """
        import uuid

        task_id = f"sov_{uuid.uuid4().hex[:12]}"

        result = SovereignResult(task_id=task_id)

        # 1. Crystallize the intent
        crystal = self.crystallizer.crystallize(description, context)
        result.crystal = crystal
        result.intent_clarity = crystal.clarity.value

        # If intent is too vague, request clarification
        if crystal.needs_refinement():
            result.verdict = "clarify"
            result.clarification_needed = crystal.ambiguity_flags
            result.explanation = f"Intent is {crystal.clarity.value}. Need clarification on: {', '.join(crystal.ambiguity_flags)}"
            return result

        # Use the refined intent going forward
        refined_description = crystal.get_execution_intent()

        # 2. Check with conscience
        ethical_check = self.conscience.evaluate(refined_description, context)
        result.ethical_check = ethical_check
        result.conscience_memories = len(ethical_check.relevant_memories)

        # If blocked by conscience
        if ethical_check.is_blocked():
            result.verdict = "block"
            result.explanation = ethical_check.explanation
            return result

        # 3. Analyze temporal impact
        if files_affected:
            impact = predict_implications(
                self.intent_graph,
                refined_description,
                files_affected,
            )
            result.causal_impact = impact
            result.would_contradict = [
                c["intent"][:50] for c in impact.get("contradictions", [])
            ]

            # If high-risk temporal impact
            if impact.get("risk_level") == "high":
                result.verdict = "reconsider"
                result.explanation = impact.get("narrative", "Would contradict previous work")
                return result

        # 4. Run through basic reflection
        task = Task(
            id=task_id,
            description=refined_description,
            source_client=source,
        )
        reflection_result = await self.reflection_router.submit(task)
        result.reflection = reflection_result

        # Map reflection outcome to verdict
        if reflection_result.outcome == ReflectionOutcome.PROCEED:
            result.verdict = "proceed"
            result.explanation = "All checks passed"
        elif reflection_result.outcome == ReflectionOutcome.REJECT:
            result.verdict = "block"
            result.explanation = reflection_result.notes
        elif reflection_result.outcome == ReflectionOutcome.ESCALATE:
            result.verdict = "reconsider"
            result.explanation = reflection_result.notes
        elif reflection_result.outcome == ReflectionOutcome.DECOMPOSE:
            result.verdict = "clarify"
            result.clarification_needed = ["Task is too complex, needs decomposition"]
            result.explanation = reflection_result.notes
        else:
            result.verdict = "reconsider"
            result.explanation = reflection_result.notes

        # Record in conscience for future learning
        self.conscience.remember_decision(
            refined_description,
            result.verdict,
            task_id=task_id,
        )

        # Record in temporal graph
        if files_affected:
            self.intent_graph.record_task(
                task_id=task_id,
                description=refined_description,
                files_modified=files_affected,
            )
            self.intent_graph.save(self.graph_path)

        return result

    def record_outcome(
        self,
        task_id: str,
        outcome: str,
        was_regret: bool = False,
        lesson: str | None = None,
    ) -> None:
        """
        Record the outcome of a task for conscience learning.

        Call this after execution to help the conscience learn.
        """
        # Find the memory
        for memory in self.conscience.memory.memories:
            if memory.task_id == task_id:
                if was_regret:
                    self.conscience.record_regret(memory.id, lesson or "Unspecified regret")
                else:
                    self.conscience.memory.record_outcome(
                        memory.id,
                        outcome=outcome,
                        notes=lesson,
                    )
                    self.conscience.memory.save(self.conscience.memory_path)
                break

    def get_wisdom(self) -> dict[str, Any]:
        """Get accumulated wisdom statistics"""
        return {
            "conscience": self.conscience.get_wisdom_stats(),
            "temporal_chains": len(self.intent_graph.chains),
            "temporal_nodes": sum(len(c.nodes) for c in self.intent_graph.chains.values()),
            "crystallizer_patterns": len(self.crystallizer._patterns),
        }
