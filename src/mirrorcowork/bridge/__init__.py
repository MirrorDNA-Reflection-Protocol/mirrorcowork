"""Bridge components for MCP and external service integration"""

from mirrorcowork.bridge.mirrorbrain import (
    MirrorBrainBridge,
    MirrorBrainState,
    create_context_provider,
)

__all__ = ["MirrorBrainBridge", "MirrorBrainState", "create_context_provider"]
