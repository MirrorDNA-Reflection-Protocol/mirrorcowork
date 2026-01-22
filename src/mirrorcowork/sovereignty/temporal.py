"""
Temporal Sovereignty - Causal Chain Tracking

Every task exists in a causal web. This module tracks:
- What led to this task (ancestry)
- What this task enables (descendants)
- What would break if this task fails (dependencies)
- What would become possible if this task succeeds (unlocks)

This isn't just task history — it's a map of intention through time.

Example:
    You create file X in task A.
    You modify file X in task B (depends on A).
    You want to delete file X in task C.

    Temporal sovereignty asks:
    - Task C would orphan task B's modifications
    - Task B's intent was "improve X" — deletion contradicts that intent
    - Should we escalate? Archive instead? Ask what changed?

The system remembers not just WHAT happened, but WHY.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class CausalRelation(str, Enum):
    """How tasks relate causally"""

    ENABLES = "enables"          # A enables B (B can't happen without A)
    DEPENDS = "depends"          # A depends on B (A needs B's output)
    CONTRADICTS = "contradicts"  # A contradicts B (doing A undoes B)
    EXTENDS = "extends"          # A extends B (A builds on B's work)
    SUPERSEDES = "supersedes"    # A supersedes B (A replaces B)
    PARALLEL = "parallel"        # A and B are independent


class TemporalNode(BaseModel):
    """
    A node in the causal graph.

    Each node represents a task at a point in time, with links to
    its causal ancestors and descendants.
    """

    task_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # The crystallized intent (what this task MEANT to do)
    intent_hash: str | None = None
    intent_summary: str | None = None

    # Artifacts this task touched
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)

    # State changes
    state_before: dict[str, Any] = Field(default_factory=dict)
    state_after: dict[str, Any] = Field(default_factory=dict)

    # Causal links
    ancestors: list[str] = Field(default_factory=list)      # Task IDs that led to this
    descendants: list[str] = Field(default_factory=list)    # Task IDs this enables
    relations: dict[str, CausalRelation] = Field(default_factory=dict)  # task_id -> relation

    # Execution outcome
    succeeded: bool | None = None
    outcome_summary: str | None = None

    def compute_intent_hash(self, description: str) -> str:
        """Compute a hash of the intent for matching similar tasks"""
        # Normalize and hash
        normalized = description.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def would_contradict(self, other: TemporalNode) -> bool:
        """Check if this task would contradict another's intent"""
        # Deletion of files created by other
        for f in self.files_deleted:
            if f in other.files_created or f in other.files_modified:
                return True

        # Explicit contradiction relation
        if other.task_id in self.relations:
            return self.relations[other.task_id] == CausalRelation.CONTRADICTS

        return False

    def depends_on(self, other: TemporalNode) -> bool:
        """Check if this task depends on another"""
        # Uses files created/modified by other
        for f in self.files_modified:
            if f in other.files_created:
                return True

        return other.task_id in self.ancestors


class CausalChain(BaseModel):
    """
    A chain of causally linked tasks.

    This represents a "thread" of work — a series of tasks that
    form a coherent narrative of intention.
    """

    chain_id: str
    name: str | None = None
    nodes: list[TemporalNode] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)

    # Chain-level metadata
    root_intent: str | None = None      # The original goal
    current_state: str | None = None    # Where we are now
    blocked_by: list[str] = Field(default_factory=list)  # What's stopping progress

    def add_node(self, node: TemporalNode) -> None:
        """Add a node to the chain"""
        if self.nodes:
            # Link to previous
            node.ancestors.append(self.nodes[-1].task_id)
            self.nodes[-1].descendants.append(node.task_id)
        self.nodes.append(node)

    def get_living_artifacts(self) -> set[str]:
        """Get all files that currently exist (created - deleted)"""
        created = set()
        deleted = set()

        for node in self.nodes:
            created.update(node.files_created)
            deleted.update(node.files_deleted)

        return created - deleted

    def find_contradictions(self, new_node: TemporalNode) -> list[tuple[TemporalNode, str]]:
        """Find nodes that would be contradicted by a new task"""
        contradictions = []

        for node in self.nodes:
            if new_node.would_contradict(node):
                reason = self._explain_contradiction(node, new_node)
                contradictions.append((node, reason))

        return contradictions

    def _explain_contradiction(self, existing: TemporalNode, new: TemporalNode) -> str:
        """Generate a human-readable explanation of why tasks contradict"""
        reasons = []

        for f in new.files_deleted:
            if f in existing.files_created:
                reasons.append(f"deletes '{f}' which was created by task {existing.task_id}")
            elif f in existing.files_modified:
                reasons.append(f"deletes '{f}' which was modified by task {existing.task_id}")

        if existing.intent_summary and new.intent_summary:
            # TODO: Use LLM to detect semantic contradiction
            pass

        return "; ".join(reasons) if reasons else "unknown contradiction"


class IntentGraph(BaseModel):
    """
    The full graph of all causal chains and their interconnections.

    This is the "memory" of what has been done and why.
    """

    chains: dict[str, CausalChain] = Field(default_factory=dict)
    orphan_nodes: list[TemporalNode] = Field(default_factory=list)

    # Cross-chain links
    cross_links: dict[str, list[str]] = Field(default_factory=dict)  # node_id -> [related_node_ids]

    # File -> chain mapping (which chain owns which files)
    file_ownership: dict[str, str] = Field(default_factory=dict)

    def create_chain(self, chain_id: str, root_intent: str) -> CausalChain:
        """Create a new causal chain"""
        chain = CausalChain(chain_id=chain_id, root_intent=root_intent)
        self.chains[chain_id] = chain
        return chain

    def find_chain_for_file(self, filepath: str) -> CausalChain | None:
        """Find which chain owns a file"""
        chain_id = self.file_ownership.get(filepath)
        return self.chains.get(chain_id) if chain_id else None

    def record_task(
        self,
        task_id: str,
        description: str,
        files_created: list[str] | None = None,
        files_modified: list[str] | None = None,
        files_deleted: list[str] | None = None,
        chain_id: str | None = None,
    ) -> TemporalNode:
        """Record a task in the graph"""
        node = TemporalNode(
            task_id=task_id,
            files_created=files_created or [],
            files_modified=files_modified or [],
            files_deleted=files_deleted or [],
        )
        node.intent_hash = node.compute_intent_hash(description)
        node.intent_summary = description

        # Update file ownership
        for f in node.files_created:
            self.file_ownership[f] = chain_id or task_id

        # Add to chain or orphans
        if chain_id and chain_id in self.chains:
            self.chains[chain_id].add_node(node)
        else:
            self.orphan_nodes.append(node)

        return node

    def predict_impact(self, proposed_node: TemporalNode) -> dict[str, Any]:
        """
        Predict the impact of a proposed task across all chains.

        Returns analysis of what would be affected.
        """
        impact = {
            "contradictions": [],
            "orphaned_chains": [],
            "affected_files": [],
            "risk_level": "low",
        }

        # Check each chain for contradictions
        for chain_id, chain in self.chains.items():
            contradictions = chain.find_contradictions(proposed_node)
            if contradictions:
                for node, reason in contradictions:
                    impact["contradictions"].append({
                        "chain": chain_id,
                        "task": node.task_id,
                        "intent": node.intent_summary,
                        "reason": reason,
                    })

        # Check for orphaning
        for f in proposed_node.files_deleted:
            owner_chain = self.file_ownership.get(f)
            if owner_chain and owner_chain in self.chains:
                chain = self.chains[owner_chain]
                living = chain.get_living_artifacts()
                if f in living:
                    impact["affected_files"].append({
                        "file": f,
                        "chain": owner_chain,
                        "chain_intent": chain.root_intent,
                    })

        # Calculate risk level
        if impact["contradictions"]:
            impact["risk_level"] = "high"
        elif impact["affected_files"]:
            impact["risk_level"] = "medium"

        return impact

    @classmethod
    def load(cls, path: Path) -> IntentGraph:
        """Load graph from disk"""
        if path.exists():
            return cls.model_validate_json(path.read_text())
        return cls()

    def save(self, path: Path) -> None:
        """Persist graph to disk"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))


def trace_lineage(graph: IntentGraph, task_id: str) -> list[TemporalNode]:
    """Trace the full lineage of a task back to its root"""
    lineage = []

    # Find the node
    node = None
    for chain in graph.chains.values():
        for n in chain.nodes:
            if n.task_id == task_id:
                node = n
                break

    if not node:
        return lineage

    # Walk ancestors
    current = node
    while current:
        lineage.append(current)
        if current.ancestors:
            # Find first ancestor
            ancestor_id = current.ancestors[0]
            current = None
            for chain in graph.chains.values():
                for n in chain.nodes:
                    if n.task_id == ancestor_id:
                        current = n
                        break
        else:
            current = None

    return list(reversed(lineage))


def predict_implications(
    graph: IntentGraph,
    description: str,
    files_affected: list[str],
) -> dict[str, Any]:
    """
    Predict the implications of a proposed task WITHOUT executing it.

    This is the "pre-flight" check that makes temporal sovereignty work.
    """
    # Create a hypothetical node
    import uuid
    hypothetical = TemporalNode(
        task_id=f"hypothetical_{uuid.uuid4().hex[:8]}",
        intent_summary=description,
    )

    # Parse the description for file operations
    desc_lower = description.lower()
    if "delete" in desc_lower or "remove" in desc_lower:
        hypothetical.files_deleted = files_affected
    elif "create" in desc_lower or "add" in desc_lower:
        hypothetical.files_created = files_affected
    else:
        hypothetical.files_modified = files_affected

    # Get impact prediction
    impact = graph.predict_impact(hypothetical)

    # Add narrative explanation
    if impact["risk_level"] == "high":
        impact["narrative"] = _generate_risk_narrative(impact)

    return impact


def _generate_risk_narrative(impact: dict[str, Any]) -> str:
    """Generate a human-readable explanation of the risk"""
    parts = []

    if impact["contradictions"]:
        parts.append("This task would contradict previous work:")
        for c in impact["contradictions"][:3]:  # Top 3
            parts.append(f"  - Task '{c['task']}' ({c['intent'][:50]}...): {c['reason']}")

    if impact["affected_files"]:
        parts.append("Files from active work chains would be affected:")
        for f in impact["affected_files"][:3]:
            parts.append(f"  - {f['file']} (part of: {f['chain_intent'][:40]}...)")

    return "\n".join(parts)
