"""
Intent Crystallization

The problem with natural language task descriptions is they're ambiguous.
"Fix the auth bug" could mean a hundred different things. Traditional systems
just execute whatever interpretation the agent chooses.

Intent Crystallization is different: tasks REFINE THEMSELVES through
iterative reflection until the intent is sharp enough to execute safely.

The process:
1. Raw intent: "Fix the auth bug"
2. First crystallization: "Fix authentication failure in login.py"
3. Second crystallization: "Fix JWT token expiration check at login.py:45"
4. Final crystal: Precise, unambiguous, auditable

Each crystallization stage adds:
- Specificity (what exactly?)
- Constraints (what NOT to do?)
- Success criteria (how do we know it worked?)
- Rollback path (how to undo if wrong?)

The crystal is immutable once formed — any change creates a NEW crystal
with lineage to the original. This preserves the audit trail of how
vague intentions became specific actions.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CrystalClarity(str, Enum):
    """How clear/specific is the intent?"""

    AMORPHOUS = "amorphous"      # Vague, could mean many things
    TRANSLUCENT = "translucent"  # Partially clear, some ambiguity
    CLEAR = "clear"              # Specific but could be clearer
    CRYSTALLINE = "crystalline"  # Sharp, unambiguous, executable


class Constraint(BaseModel):
    """A constraint on how a task should be executed"""

    description: str
    type: str = "soft"  # "soft" = warning, "hard" = blocker
    source: str = "inferred"  # Where this constraint came from


class SuccessCriterion(BaseModel):
    """How we know the task succeeded"""

    description: str
    verifiable: bool = True
    verification_method: str | None = None


class IntentCrystal(BaseModel):
    """
    A crystallized intent — a task that has been refined to executable clarity.

    Crystals are immutable. Refinement creates new crystals with lineage.
    """

    id: str
    created_at: datetime = Field(default_factory=datetime.now)

    # The intent at various stages
    raw_intent: str                          # Original user request
    refined_intent: str | None = None        # After crystallization
    final_intent: str | None = None          # Ready for execution

    # Clarity assessment
    clarity: CrystalClarity = CrystalClarity.AMORPHOUS

    # Refinement details
    specificity_score: float = 0.0           # 0-1, how specific is this?
    ambiguity_flags: list[str] = Field(default_factory=list)  # What's unclear?

    # Constraints discovered during crystallization
    constraints: list[Constraint] = Field(default_factory=list)

    # Success criteria
    success_criteria: list[SuccessCriterion] = Field(default_factory=list)

    # Rollback path
    rollback_steps: list[str] = Field(default_factory=list)

    # Lineage
    parent_crystal_id: str | None = None     # What crystal was this refined from?
    refinement_count: int = 0                # How many times refined?

    # Execution binding
    bound_to_task: str | None = None         # Task ID this crystal drives
    execution_started: bool = False

    def compute_hash(self) -> str:
        """Compute a unique hash of this crystal's final state"""
        content = f"{self.final_intent or self.refined_intent or self.raw_intent}"
        content += f":{','.join(c.description for c in self.constraints)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def is_executable(self) -> bool:
        """Check if this crystal is clear enough to execute"""
        return self.clarity in (CrystalClarity.CLEAR, CrystalClarity.CRYSTALLINE)

    def needs_refinement(self) -> bool:
        """Check if this crystal needs more refinement"""
        return self.clarity in (CrystalClarity.AMORPHOUS, CrystalClarity.TRANSLUCENT)

    def get_execution_intent(self) -> str:
        """Get the intent to use for execution"""
        return self.final_intent or self.refined_intent or self.raw_intent

    def add_constraint(self, description: str, hard: bool = False, source: str = "inferred") -> None:
        """Add a constraint discovered during crystallization"""
        self.constraints.append(Constraint(
            description=description,
            type="hard" if hard else "soft",
            source=source,
        ))

    def add_success_criterion(self, description: str, verification: str | None = None) -> None:
        """Add a success criterion"""
        self.success_criteria.append(SuccessCriterion(
            description=description,
            verifiable=verification is not None,
            verification_method=verification,
        ))


class RefinementStep(BaseModel):
    """A single step in the crystallization process"""

    timestamp: datetime = Field(default_factory=datetime.now)
    before_clarity: CrystalClarity
    after_clarity: CrystalClarity
    refinement_type: str           # "clarification", "constraint", "decomposition"
    details: str
    confidence: float = 0.8        # How confident are we in this refinement?


class CrystallizationEngine:
    """
    Engine that refines vague intents into crystalline, executable tasks.

    The engine uses multiple strategies:
    1. Pattern matching - known task patterns
    2. Context injection - what files/state are relevant?
    3. Constraint discovery - what SHOULDN'T we do?
    4. Success definition - how do we know we're done?
    """

    def __init__(self):
        self.refinement_history: list[RefinementStep] = []
        self._patterns: dict[str, dict[str, Any]] = self._load_patterns()

    def _load_patterns(self) -> dict[str, dict[str, Any]]:
        """Load known task patterns for faster crystallization"""
        return {
            "fix": {
                "questions": ["What file?", "What function?", "What line?", "What's the symptom?"],
                "constraints": ["Don't change unrelated code", "Add test if missing"],
                "success": ["Bug no longer reproducible", "Tests pass"],
            },
            "refactor": {
                "questions": ["What scope?", "What pattern to apply?", "Preserve behavior?"],
                "constraints": ["Must preserve all existing behavior", "Must pass existing tests"],
                "success": ["Code meets new pattern", "All tests pass", "No behavior change"],
            },
            "add": {
                "questions": ["Where to add?", "What interface?", "What dependencies?"],
                "constraints": ["Follow existing patterns", "Add tests"],
                "success": ["Feature works", "Tests added", "Documentation updated"],
            },
            "delete": {
                "questions": ["What exactly?", "Why?", "What depends on it?"],
                "constraints": ["Verify nothing depends on it", "Consider archiving instead"],
                "success": ["Target removed", "No broken dependencies", "Tests pass"],
            },
            "deploy": {
                "questions": ["What environment?", "What version?", "Rollback plan?"],
                "constraints": ["Must have rollback plan", "Must notify stakeholders"],
                "success": ["Deployment successful", "Health checks pass", "No errors in logs"],
            },
        }

    def crystallize(
        self,
        raw_intent: str,
        context: dict[str, Any] | None = None,
        max_iterations: int = 3,
    ) -> IntentCrystal:
        """
        Crystallize a raw intent into an executable crystal.

        This is the main entry point for the crystallization process.
        """
        import uuid

        crystal = IntentCrystal(
            id=f"crystal_{uuid.uuid4().hex[:12]}",
            raw_intent=raw_intent,
        )

        # Initial clarity assessment
        crystal.clarity = self._assess_clarity(raw_intent)
        crystal.specificity_score = self._score_specificity(raw_intent)
        crystal.ambiguity_flags = self._find_ambiguities(raw_intent)

        # Iterative refinement
        for i in range(max_iterations):
            if crystal.is_executable():
                break

            before_clarity = crystal.clarity
            crystal = self._refine_step(crystal, context)

            self.refinement_history.append(RefinementStep(
                before_clarity=before_clarity,
                after_clarity=crystal.clarity,
                refinement_type="auto",
                details=f"Iteration {i+1}",
            ))

        return crystal

    def _assess_clarity(self, intent: str) -> CrystalClarity:
        """Assess how clear an intent is"""
        score = self._score_specificity(intent)

        if score < 0.3:
            return CrystalClarity.AMORPHOUS
        elif score < 0.5:
            return CrystalClarity.TRANSLUCENT
        elif score < 0.8:
            return CrystalClarity.CLEAR
        else:
            return CrystalClarity.CRYSTALLINE

    def _score_specificity(self, intent: str) -> float:
        """Score how specific an intent is (0-1)"""
        score = 0.0
        intent_lower = intent.lower()

        # File references increase specificity
        if ".py" in intent_lower or ".ts" in intent_lower or ".js" in intent_lower:
            score += 0.2

        # Line numbers are very specific
        if "line " in intent_lower or ":" in intent_lower:
            score += 0.2

        # Function/class names
        if "function " in intent_lower or "class " in intent_lower or "def " in intent_lower:
            score += 0.15

        # Concrete verbs
        concrete_verbs = ["add", "remove", "change", "update", "fix", "create", "delete"]
        if any(v in intent_lower for v in concrete_verbs):
            score += 0.1

        # Vague words reduce score
        vague_words = ["somehow", "maybe", "probably", "try to", "if possible", "or something"]
        if any(v in intent_lower for v in vague_words):
            score -= 0.2

        # Length factor (too short is vague)
        words = len(intent.split())
        if words < 5:
            score -= 0.1
        elif words > 10:
            score += 0.1

        return max(0.0, min(1.0, score + 0.3))  # Base score of 0.3

    def _find_ambiguities(self, intent: str) -> list[str]:
        """Find ambiguous parts of an intent"""
        ambiguities = []
        intent_lower = intent.lower()

        # Check for vague references
        if "the bug" in intent_lower and "in " not in intent_lower:
            ambiguities.append("Which bug? (no file/location specified)")

        if "the file" in intent_lower and not any(ext in intent_lower for ext in [".py", ".ts", ".js", ".md"]):
            ambiguities.append("Which file? (no filename specified)")

        if "this" in intent_lower or "that" in intent_lower:
            ambiguities.append("Unclear reference ('this'/'that' without context)")

        # Check for missing action specifics
        action_words = {"fix": "fix what?", "add": "add what/where?", "remove": "remove what?"}
        for action, question in action_words.items():
            if intent_lower.startswith(action) and len(intent.split()) < 4:
                ambiguities.append(question)

        return ambiguities

    def _refine_step(self, crystal: IntentCrystal, context: dict[str, Any] | None) -> IntentCrystal:
        """Perform one refinement step"""
        # Detect task pattern
        pattern_name = self._detect_pattern(crystal.raw_intent)

        if pattern_name and pattern_name in self._patterns:
            pattern = self._patterns[pattern_name]

            # Add constraints from pattern
            for constraint in pattern.get("constraints", []):
                crystal.add_constraint(constraint, source=f"pattern:{pattern_name}")

            # Add success criteria from pattern
            for criterion in pattern.get("success", []):
                crystal.add_success_criterion(criterion)

        # Inject context if available
        if context:
            crystal = self._inject_context(crystal, context)

        # Generate refined intent
        crystal.refined_intent = self._generate_refined_intent(crystal)

        # Re-assess clarity
        crystal.clarity = self._assess_clarity(crystal.refined_intent)
        crystal.specificity_score = self._score_specificity(crystal.refined_intent)
        crystal.refinement_count += 1

        return crystal

    def _detect_pattern(self, intent: str) -> str | None:
        """Detect which task pattern matches"""
        intent_lower = intent.lower()

        for pattern_name in self._patterns:
            if intent_lower.startswith(pattern_name):
                return pattern_name

        return None

    def _inject_context(self, crystal: IntentCrystal, context: dict[str, Any]) -> IntentCrystal:
        """Inject contextual information to increase specificity"""
        # If we have file context, add constraints
        if "files_in_scope" in context:
            files = context["files_in_scope"]
            if len(files) == 1:
                crystal.add_constraint(f"Scope limited to: {files[0]}", source="context")

        # If we have recent changes, reference them
        if "recent_changes" in context:
            crystal.add_constraint("Be aware of recent changes in this area", source="context")

        return crystal

    def _generate_refined_intent(self, crystal: IntentCrystal) -> str:
        """Generate a more refined intent statement"""
        parts = [crystal.raw_intent]

        if crystal.constraints:
            constraint_summary = "; ".join(c.description for c in crystal.constraints[:2])
            parts.append(f"(constraints: {constraint_summary})")

        if crystal.success_criteria:
            criterion = crystal.success_criteria[0].description
            parts.append(f"(success: {criterion})")

        return " ".join(parts)


def refine_intent(
    raw_intent: str,
    context: dict[str, Any] | None = None,
) -> IntentCrystal:
    """
    Convenience function to crystallize an intent.

    Usage:
        crystal = refine_intent("Fix the auth bug")
        if crystal.is_executable():
            execute(crystal.get_execution_intent())
        else:
            ask_for_clarification(crystal.ambiguity_flags)
    """
    engine = CrystallizationEngine()
    return engine.crystallize(raw_intent, context)
