"""
Temporal Sovereignty - The Dream Layer

This module implements something not in any spec: the ability for tasks to
understand their own causal history and future implications. Tasks aren't
just work units — they're nodes in a temporal graph of intention.

When you ask "delete this file", the system doesn't just check safety patterns.
It asks: "What tasks led to this file existing? What tasks depend on it?
What does deleting it mean for the causal future of this codebase?"

This is sovereignty over time, not just over execution.
"""

from mirrorcowork.sovereignty.temporal import (
    CausalChain,
    TemporalNode,
    IntentGraph,
    trace_lineage,
    predict_implications,
)
from mirrorcowork.sovereignty.conscience import (
    Conscience,
    EthicalCheck,
    ConscienceMemory,
)
from mirrorcowork.sovereignty.crystallization import (
    IntentCrystal,
    CrystallizationEngine,
    refine_intent,
)

__all__ = [
    "CausalChain",
    "TemporalNode",
    "IntentGraph",
    "trace_lineage",
    "predict_implications",
    "Conscience",
    "EthicalCheck",
    "ConscienceMemory",
    "IntentCrystal",
    "CrystallizationEngine",
    "refine_intent",
]
