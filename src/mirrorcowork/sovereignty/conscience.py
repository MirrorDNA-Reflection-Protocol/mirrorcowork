"""
The Conscience Layer

This is the ethical nervous system of MirrorCowork.

Most agentic systems have safety rails — patterns to block. But they don't
have MEMORY. They can't say "wait, I did something similar last week and
it caused a production incident."

The Conscience Layer maintains:
1. A memory of past decisions and their outcomes
2. Ethical checks that learn from experience
3. The ability to say "I've seen this pattern before, and it didn't end well"

This isn't just safety — it's WISDOM accumulated over time.

The conscience can:
- Remember when "quick fixes" caused cascading failures
- Recall that deleting "unused" code broke an edge case
- Note that deploying on Fridays correlates with weekend incidents
- Track which types of tasks you later regretted approving

It's not paranoid — it's experienced.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EthicalConcern(str, Enum):
    """Categories of ethical concerns"""

    SAFETY = "safety"              # Could cause harm
    REVERSIBILITY = "reversibility"  # Hard/impossible to undo
    CONSENT = "consent"            # Acting without clear authorization
    SCOPE_CREEP = "scope_creep"    # Going beyond what was asked
    TIMING = "timing"              # Bad timing (Friday deploy, etc.)
    PRECEDENT = "precedent"        # Sets a dangerous precedent
    PATTERN = "pattern"            # Matches a known-bad pattern


class Severity(str, Enum):
    """How serious is the concern?"""

    INFO = "info"          # Just noting it
    CAUTION = "caution"    # Proceed with awareness
    WARNING = "warning"    # Should probably reconsider
    CRITICAL = "critical"  # Should not proceed


class EthicalMemory(BaseModel):
    """
    A memory of a past decision and its outcome.

    The conscience learns from these memories to make better judgments.
    """

    id: str
    created_at: datetime = Field(default_factory=datetime.now)

    # What was the decision?
    task_summary: str
    task_id: str | None = None
    decision: str                   # "approved", "rejected", "escalated"

    # What happened?
    outcome: str | None = None      # "success", "failure", "partial", "regret"
    outcome_notes: str | None = None

    # What did we learn?
    lesson: str | None = None
    patterns_identified: list[str] = Field(default_factory=list)

    # Relevance scoring
    times_recalled: int = 0         # How often has this memory been relevant?
    last_recalled: datetime | None = None

    def mark_recalled(self) -> None:
        """Mark this memory as having been recalled"""
        self.times_recalled += 1
        self.last_recalled = datetime.now()


class EthicalCheck(BaseModel):
    """
    Result of an ethical check on a proposed task.

    Contains concerns, relevant memories, and a recommendation.
    """

    task_description: str
    checked_at: datetime = Field(default_factory=datetime.now)

    # Concerns identified
    concerns: list[dict[str, Any]] = Field(default_factory=list)
    max_severity: Severity = Severity.INFO

    # Relevant memories
    relevant_memories: list[EthicalMemory] = Field(default_factory=list)

    # Recommendation
    recommendation: str = "proceed"  # "proceed", "caution", "reconsider", "block"
    explanation: str | None = None

    # If blocking, what would make it acceptable?
    conditions_to_proceed: list[str] = Field(default_factory=list)

    def add_concern(
        self,
        category: EthicalConcern,
        description: str,
        severity: Severity,
    ) -> None:
        """Add a concern to this check"""
        self.concerns.append({
            "category": category.value,
            "description": description,
            "severity": severity.value,
        })

        # Update max severity
        severity_order = [Severity.INFO, Severity.CAUTION, Severity.WARNING, Severity.CRITICAL]
        if severity_order.index(severity) > severity_order.index(self.max_severity):
            self.max_severity = severity

    def is_blocked(self) -> bool:
        """Check if this task is blocked by ethical concerns"""
        return self.recommendation == "block" or self.max_severity == Severity.CRITICAL


class ConscienceMemory(BaseModel):
    """
    The long-term memory of the conscience.

    Stores memories of past decisions, learned patterns, and wisdom
    accumulated over time.
    """

    memories: list[EthicalMemory] = Field(default_factory=list)

    # Learned patterns (what to watch for)
    bad_patterns: list[dict[str, Any]] = Field(default_factory=list)
    good_patterns: list[dict[str, Any]] = Field(default_factory=list)

    # Time-based learnings
    timing_risks: dict[str, list[str]] = Field(default_factory=dict)  # "friday" -> ["deploy incidents"]

    # Statistics
    total_checks: int = 0
    blocks_issued: int = 0
    regrets_recorded: int = 0

    def remember(
        self,
        task_summary: str,
        decision: str,
        task_id: str | None = None,
    ) -> EthicalMemory:
        """Create a new memory"""
        import uuid

        memory = EthicalMemory(
            id=f"mem_{uuid.uuid4().hex[:12]}",
            task_summary=task_summary,
            task_id=task_id,
            decision=decision,
        )
        self.memories.append(memory)
        return memory

    def record_outcome(
        self,
        memory_id: str,
        outcome: str,
        notes: str | None = None,
        lesson: str | None = None,
    ) -> None:
        """Record the outcome of a past decision"""
        for memory in self.memories:
            if memory.id == memory_id:
                memory.outcome = outcome
                memory.outcome_notes = notes
                memory.lesson = lesson

                # If it was a regret, update stats and learn
                if outcome == "regret":
                    self.regrets_recorded += 1
                    self._learn_from_regret(memory)

                break

    def _learn_from_regret(self, memory: EthicalMemory) -> None:
        """Extract patterns from a regretted decision"""
        # Add to bad patterns
        self.bad_patterns.append({
            "pattern": memory.task_summary,
            "learned_from": memory.id,
            "learned_at": datetime.now().isoformat(),
            "lesson": memory.lesson,
        })

        # Check for timing patterns
        day_of_week = memory.created_at.strftime("%A").lower()
        if day_of_week not in self.timing_risks:
            self.timing_risks[day_of_week] = []
        self.timing_risks[day_of_week].append(memory.task_summary)

    def find_relevant_memories(
        self,
        task_description: str,
        limit: int = 5,
    ) -> list[EthicalMemory]:
        """Find memories relevant to a proposed task"""
        relevant = []
        task_lower = task_description.lower()

        for memory in self.memories:
            # Simple keyword matching (could be enhanced with embeddings)
            memory_lower = memory.task_summary.lower()

            # Check for word overlap
            task_words = set(task_lower.split())
            memory_words = set(memory_lower.split())
            overlap = task_words & memory_words

            # Significant overlap = relevant
            if len(overlap) >= 2:
                memory.mark_recalled()
                relevant.append(memory)

            if len(relevant) >= limit:
                break

        # Sort by outcome severity (regrets first)
        def outcome_priority(m: EthicalMemory) -> int:
            priorities = {"regret": 0, "failure": 1, "partial": 2, "success": 3, None: 4}
            return priorities.get(m.outcome, 4)

        return sorted(relevant, key=outcome_priority)[:limit]

    @classmethod
    def load(cls, path: Path) -> ConscienceMemory:
        """Load conscience memory from disk"""
        if path.exists():
            return cls.model_validate_json(path.read_text())
        return cls()

    def save(self, path: Path) -> None:
        """Persist conscience memory to disk"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))


class Conscience:
    """
    The ethical checker for MirrorCowork.

    Uses accumulated wisdom (memories) plus built-in checks to evaluate
    whether a proposed task should proceed.

    Usage:
        conscience = Conscience()
        check = conscience.evaluate("Deploy to production on Friday afternoon")

        if check.is_blocked():
            print(f"Blocked: {check.explanation}")
        else:
            print(f"Proceed with caution: {check.concerns}")
    """

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or Path.home() / ".mirrordna" / "mirrorcowork"
        self.memory_path = self.state_dir / "conscience_memory.json"
        self.memory = ConscienceMemory.load(self.memory_path)

        # Built-in timing risks
        self._timing_rules = {
            "friday": ["deploy", "release", "migration"],
            "weekend": ["major change", "refactor", "breaking"],
            "end_of_day": ["complex", "risky", "irreversible"],
        }

    def evaluate(self, task_description: str, context: dict[str, Any] | None = None) -> EthicalCheck:
        """
        Evaluate a proposed task for ethical concerns.

        Returns an EthicalCheck with concerns, relevant memories,
        and a recommendation.
        """
        self.memory.total_checks += 1

        check = EthicalCheck(task_description=task_description)

        # Run all checks
        self._check_safety_patterns(check, task_description)
        self._check_reversibility(check, task_description)
        self._check_timing(check, task_description)
        self._check_scope(check, task_description, context)
        self._check_against_memories(check, task_description)

        # Generate recommendation
        check.recommendation = self._generate_recommendation(check)
        check.explanation = self._generate_explanation(check)

        # Save updated memory
        self.memory.save(self.memory_path)

        return check

    def _check_safety_patterns(self, check: EthicalCheck, description: str) -> None:
        """Check for known dangerous patterns"""
        desc_lower = description.lower()

        # Dangerous patterns
        dangerous = [
            ("rm -rf", "Recursive deletion is irreversible"),
            ("drop table", "Database deletion is irreversible"),
            ("force push", "Force push overwrites history"),
            ("--no-verify", "Skipping verification is risky"),
            ("disable.*security", "Disabling security is dangerous"),
        ]

        for pattern, reason in dangerous:
            if pattern in desc_lower:
                check.add_concern(
                    EthicalConcern.SAFETY,
                    reason,
                    Severity.CRITICAL,
                )

    def _check_reversibility(self, check: EthicalCheck, description: str) -> None:
        """Check if the action is reversible"""
        desc_lower = description.lower()

        irreversible_indicators = [
            "delete", "remove", "drop", "destroy", "purge",
            "overwrite", "replace all", "format",
        ]

        for indicator in irreversible_indicators:
            if indicator in desc_lower:
                check.add_concern(
                    EthicalConcern.REVERSIBILITY,
                    f"'{indicator}' operations may be irreversible",
                    Severity.WARNING,
                )
                check.conditions_to_proceed.append("Confirm backup exists")
                break

    def _check_timing(self, check: EthicalCheck, description: str) -> None:
        """Check if timing is risky"""
        now = datetime.now()
        desc_lower = description.lower()

        # Friday check
        if now.weekday() == 4:  # Friday
            for risky_action in self._timing_rules["friday"]:
                if risky_action in desc_lower:
                    check.add_concern(
                        EthicalConcern.TIMING,
                        f"'{risky_action}' on Friday increases weekend incident risk",
                        Severity.WARNING,
                    )
                    check.conditions_to_proceed.append("Consider waiting until Monday")

        # End of day check
        if now.hour >= 17:  # After 5 PM
            for risky_action in self._timing_rules["end_of_day"]:
                if risky_action in desc_lower:
                    check.add_concern(
                        EthicalConcern.TIMING,
                        f"'{risky_action}' operations late in day are risky",
                        Severity.CAUTION,
                    )

        # Check learned timing risks
        day_name = now.strftime("%A").lower()
        if day_name in self.memory.timing_risks:
            for past_issue in self.memory.timing_risks[day_name]:
                if any(word in desc_lower for word in past_issue.lower().split()):
                    check.add_concern(
                        EthicalConcern.PATTERN,
                        f"Similar task caused issues on {day_name} previously",
                        Severity.CAUTION,
                    )

    def _check_scope(
        self,
        check: EthicalCheck,
        description: str,
        context: dict[str, Any] | None,
    ) -> None:
        """Check if the task exceeds expected scope"""
        if not context:
            return

        # Check if task goes beyond stated scope
        if "original_request" in context:
            original = context["original_request"].lower()
            current = description.lower()

            # Simple heuristic: if current is much longer, might be scope creep
            if len(current) > len(original) * 2:
                check.add_concern(
                    EthicalConcern.SCOPE_CREEP,
                    "Task description significantly expanded from original request",
                    Severity.CAUTION,
                )

    def _check_against_memories(self, check: EthicalCheck, description: str) -> None:
        """Check against memories of past decisions"""
        relevant = self.memory.find_relevant_memories(description)
        check.relevant_memories = relevant

        for memory in relevant:
            if memory.outcome == "regret":
                check.add_concern(
                    EthicalConcern.PATTERN,
                    f"Similar task '{memory.task_summary[:50]}...' was later regretted: {memory.lesson or 'no lesson recorded'}",
                    Severity.WARNING,
                )

            elif memory.outcome == "failure":
                check.add_concern(
                    EthicalConcern.PRECEDENT,
                    f"Similar task failed previously: {memory.outcome_notes or 'no details'}",
                    Severity.CAUTION,
                )

        # Check against learned bad patterns
        desc_lower = description.lower()
        for bad in self.memory.bad_patterns:
            pattern_lower = bad["pattern"].lower()
            if any(word in desc_lower for word in pattern_lower.split()):
                check.add_concern(
                    EthicalConcern.PATTERN,
                    f"Matches learned bad pattern: {bad.get('lesson', 'similar task caused issues')}",
                    Severity.WARNING,
                )

    def _generate_recommendation(self, check: EthicalCheck) -> str:
        """Generate a recommendation based on concerns"""
        if check.max_severity == Severity.CRITICAL:
            self.memory.blocks_issued += 1
            return "block"

        warning_count = sum(1 for c in check.concerns if c["severity"] == "warning")
        if warning_count >= 2:
            return "reconsider"

        if check.max_severity == Severity.WARNING:
            return "caution"

        if check.concerns:
            return "caution"

        return "proceed"

    def _generate_explanation(self, check: EthicalCheck) -> str:
        """Generate a human-readable explanation"""
        if not check.concerns:
            return "No ethical concerns identified."

        parts = []

        if check.recommendation == "block":
            parts.append("BLOCKED: Critical safety concerns identified.")
        elif check.recommendation == "reconsider":
            parts.append("Recommend reconsidering this task.")
        elif check.recommendation == "caution":
            parts.append("Proceed with awareness of the following:")

        for concern in check.concerns[:3]:  # Top 3
            parts.append(f"  - [{concern['category'].upper()}] {concern['description']}")

        if check.relevant_memories:
            parts.append(f"\nRelevant past experiences: {len(check.relevant_memories)} memories")

        if check.conditions_to_proceed:
            parts.append("\nConditions to proceed safely:")
            for condition in check.conditions_to_proceed:
                parts.append(f"  - {condition}")

        return "\n".join(parts)

    def remember_decision(
        self,
        task_description: str,
        decision: str,
        task_id: str | None = None,
    ) -> EthicalMemory:
        """Record a decision for future learning"""
        memory = self.memory.remember(task_description, decision, task_id)
        self.memory.save(self.memory_path)
        return memory

    def record_regret(
        self,
        memory_id: str,
        why: str,
    ) -> None:
        """Record that a past decision was regretted"""
        self.memory.record_outcome(
            memory_id,
            outcome="regret",
            lesson=why,
        )
        self.memory.save(self.memory_path)

    def get_wisdom_stats(self) -> dict[str, Any]:
        """Get statistics about accumulated wisdom"""
        return {
            "total_memories": len(self.memory.memories),
            "total_checks": self.memory.total_checks,
            "blocks_issued": self.memory.blocks_issued,
            "regrets_recorded": self.memory.regrets_recorded,
            "bad_patterns_learned": len(self.memory.bad_patterns),
            "good_patterns_learned": len(self.memory.good_patterns),
            "timing_risks": dict(self.memory.timing_risks),
        }
