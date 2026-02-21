"""Main MCP Hypervisor.

Provides a single governance layer that can host many nested MCP servers
under one capability matrix and firewall policy.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from pydantic import ValidationError

from mirrorcowork.state.task import AgentCapability


class NestedMcpServer(BaseModel):
    """Config for one nested MCP server behind the hypervisor."""

    id: str
    enabled: bool = True
    tier: str = "T1"
    command: str
    args: list[str] = Field(default_factory=list)
    allow_clients: list[str] = Field(default_factory=list)
    allow_capabilities: list[AgentCapability] = Field(default_factory=list)
    allow_tools: list[str] = Field(default_factory=list)
    local_only: bool = True
    network_allowlist: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class MainMcpConfig(BaseModel):
    """Top-level config for the Main MCP Hypervisor."""

    version: str = "v1"
    default_deny: bool = True
    kill_switch: bool = False
    emergency_allow_capabilities: list[AgentCapability] = Field(
        default_factory=lambda: [AgentCapability.CODE_READ, AgentCapability.FILE_READ]
    )
    agent_capability_matrix: dict[str, list[AgentCapability]] = Field(default_factory=dict)
    servers: dict[str, NestedMcpServer] = Field(default_factory=dict)


class AccessRequest(BaseModel):
    """One policy check request."""

    agent: str
    server_id: str
    capability: AgentCapability
    tool: str | None = None
    uri: str | None = None
    skill: str | None = None


class AccessDecision(BaseModel):
    """Policy decision for a request."""

    allowed: bool
    reason: str
    matched_rules: list[str] = Field(default_factory=list)


def _is_local_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return True
    if parsed.scheme in {"http", "https"}:
        return parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    return False


def _host(uri: str) -> str | None:
    return urlparse(uri).hostname


def _host_allowed(hostname: str, allowlist: list[str]) -> bool:
    for allowed in allowlist:
        if hostname == allowed or hostname.endswith(f".{allowed}"):
            return True
    return False


def default_main_mcp_config() -> MainMcpConfig:
    """Sane default: local-first, default-deny, explicit allowlists."""

    matrix = {
        "claude_code": [
            AgentCapability.CODE_WRITE,
            AgentCapability.CODE_READ,
            AgentCapability.FILE_WRITE,
            AgentCapability.FILE_READ,
            AgentCapability.GIT_COMMIT,
            AgentCapability.GIT_PUSH,
            AgentCapability.SHELL_EXEC,
            AgentCapability.MCP_CALL,
            AgentCapability.WEB_FETCH,
        ],
        "codex": [
            AgentCapability.CODE_WRITE,
            AgentCapability.CODE_READ,
            AgentCapability.FILE_WRITE,
            AgentCapability.FILE_READ,
            AgentCapability.GIT_COMMIT,
            AgentCapability.SHELL_EXEC,
            AgentCapability.MCP_CALL,
            AgentCapability.WEB_FETCH,
        ],
        "antigravity": [
            AgentCapability.CODE_WRITE,
            AgentCapability.CODE_READ,
            AgentCapability.FILE_WRITE,
            AgentCapability.FILE_READ,
            AgentCapability.GIT_COMMIT,
            AgentCapability.SHELL_EXEC,
            AgentCapability.WEB_FETCH,
            AgentCapability.MCP_CALL,
        ],
        "claude_desktop": [
            AgentCapability.CODE_READ,
            AgentCapability.FILE_READ,
            AgentCapability.WEB_FETCH,
            AgentCapability.HUMAN_INTERACT,
            AgentCapability.MCP_CALL,
        ],
    }

    servers = {
        "mirrordna_memory": NestedMcpServer(
            id="mirrordna_memory",
            tier="T1",
            command="node",
            args=["/Users/mirror-admin/repos/mirrordna-mcp/src/mcp-server.js"],
            allow_clients=["claude_code", "codex", "antigravity", "claude_desktop"],
            allow_capabilities=[
                AgentCapability.MCP_CALL,
                AgentCapability.FILE_READ,
                AgentCapability.CODE_READ,
            ],
            allow_tools=[
                "mirror_read_recent",
                "mirror_recall",
                "mirror_queue_task",
            ],
            local_only=True,
            skills=["memory", "handoff"],
        ),
        "beacon_pipeline": NestedMcpServer(
            id="beacon_pipeline",
            tier="T1",
            command="bash",
            args=["/Users/mirror-admin/repos/truth-first-beacon/scripts/publish.sh"],
            allow_clients=["claude_code", "codex"],
            allow_capabilities=[
                AgentCapability.SHELL_EXEC,
                AgentCapability.FILE_WRITE,
                AgentCapability.GIT_COMMIT,
            ],
            local_only=True,
            skills=["publish", "verification"],
        ),
        "google_dev_knowledge": NestedMcpServer(
            id="google_dev_knowledge",
            enabled=False,
            tier="T2",
            command="mcp-proxy",
            args=["google-dev-knowledge"],
            allow_clients=["claude_code", "codex", "antigravity", "claude_desktop"],
            allow_capabilities=[AgentCapability.WEB_FETCH, AgentCapability.MCP_CALL],
            allow_tools=["knowledge_search", "knowledge_get"],
            local_only=False,
            network_allowlist=[
                "developers.google.com",
                "modelcontextprotocol.io",
                "docs.anthropic.com",
                "platform.openai.com",
            ],
            skills=["docs", "research"],
        ),
    }

    return MainMcpConfig(
        version="v1",
        default_deny=True,
        kill_switch=False,
        agent_capability_matrix=matrix,
        servers=servers,
    )


def config_path(state_dir: Path) -> Path:
    """Canonical config location for the hypervisor."""

    return state_dir / "mirrorcowork" / "main_mcp.json"


def load_or_create_config(path: Path, force_reset: bool = False) -> MainMcpConfig:
    """Load existing config or create a default one."""

    if path.exists() and not force_reset:
        raw = path.read_text()
        if raw.strip():
            try:
                return MainMcpConfig.model_validate_json(raw)
            except ValidationError:
                # Recover from partial/corrupt writes by regenerating defaults.
                pass

    config = default_main_mcp_config()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.model_dump(mode="json"), indent=2))
    return config


class MainMcpHypervisor:
    """Policy engine for nested MCP servers."""

    def __init__(self, config: MainMcpConfig):
        self.config = config

    def check(self, request: AccessRequest) -> AccessDecision:
        rules: list[str] = []

        if self.config.kill_switch:
            if request.capability not in self.config.emergency_allow_capabilities:
                return AccessDecision(
                    allowed=False,
                    reason="Global kill switch is active",
                    matched_rules=["kill_switch"],
                )
            rules.append("kill_switch_emergency_allow")

        server = self.config.servers.get(request.server_id)
        if server is None:
            return AccessDecision(
                allowed=False,
                reason=f"Unknown nested MCP server: {request.server_id}",
                matched_rules=["server_exists"],
            )
        if not server.enabled:
            return AccessDecision(
                allowed=False,
                reason=f"Nested MCP server is disabled: {request.server_id}",
                matched_rules=["server_enabled"],
            )
        rules.append("server_exists")
        rules.append("server_enabled")

        agent_caps = self.config.agent_capability_matrix.get(request.agent, [])
        if request.capability not in agent_caps:
            return AccessDecision(
                allowed=False,
                reason=f"Capability '{request.capability.value}' not permitted for agent '{request.agent}'",
                matched_rules=rules + ["agent_capability_matrix"],
            )
        rules.append("agent_capability_matrix")

        if server.allow_clients and request.agent not in server.allow_clients:
            return AccessDecision(
                allowed=False,
                reason=f"Agent '{request.agent}' is not allowed on server '{server.id}'",
                matched_rules=rules + ["server_allow_clients"],
            )
        rules.append("server_allow_clients")

        if server.allow_capabilities and request.capability not in server.allow_capabilities:
            return AccessDecision(
                allowed=False,
                reason=f"Capability '{request.capability.value}' not allowed on server '{server.id}'",
                matched_rules=rules + ["server_allow_capabilities"],
            )
        rules.append("server_allow_capabilities")

        if request.tool and server.allow_tools and request.tool not in server.allow_tools:
            return AccessDecision(
                allowed=False,
                reason=f"Tool '{request.tool}' is not allowlisted for server '{server.id}'",
                matched_rules=rules + ["server_tool_allowlist"],
            )
        rules.append("server_tool_allowlist")

        if request.skill and server.skills and request.skill not in server.skills:
            return AccessDecision(
                allowed=False,
                reason=f"Skill '{request.skill}' not permitted for server '{server.id}'",
                matched_rules=rules + ["server_skill_allowlist"],
            )
        rules.append("server_skill_allowlist")

        if request.uri:
            if server.local_only and not _is_local_uri(request.uri):
                return AccessDecision(
                    allowed=False,
                    reason=f"Server '{server.id}' is local-only; external URI denied",
                    matched_rules=rules + ["local_only"],
                )
            rules.append("local_only")

            if server.network_allowlist:
                hostname = _host(request.uri)
                if not hostname:
                    return AccessDecision(
                        allowed=False,
                        reason=f"Could not parse host from URI '{request.uri}'",
                        matched_rules=rules + ["network_allowlist"],
                    )
                if not _host_allowed(hostname, server.network_allowlist):
                    return AccessDecision(
                        allowed=False,
                        reason=f"Host '{hostname}' not in network allowlist for '{server.id}'",
                        matched_rules=rules + ["network_allowlist"],
                    )
                rules.append("network_allowlist")

        return AccessDecision(
            allowed=True,
            reason="Allowed by Main MCP hypervisor policy",
            matched_rules=rules,
        )
