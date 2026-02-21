from pathlib import Path

from mirrorcowork.mcp.hypervisor import (
    AccessRequest,
    MainMcpHypervisor,
    config_path,
    load_or_create_config,
)
from mirrorcowork.state.task import AgentCapability


def _load(tmp_path: Path):
    state_dir = tmp_path / "state"
    path = config_path(state_dir)
    cfg = load_or_create_config(path)
    return state_dir, path, cfg


def test_default_config_created(tmp_path: Path):
    state_dir, path, cfg = _load(tmp_path)
    assert path.exists()
    assert state_dir.exists()
    assert "mirrordna_memory" in cfg.servers
    assert "codex" in cfg.agent_capability_matrix


def test_unknown_server_denied(tmp_path: Path):
    _, _, cfg = _load(tmp_path)
    hv = MainMcpHypervisor(cfg)
    d = hv.check(
        AccessRequest(
            agent="codex",
            server_id="nope",
            capability=AgentCapability.MCP_CALL,
        )
    )
    assert d.allowed is False
    assert "Unknown nested MCP server" in d.reason


def test_capability_matrix_denies(tmp_path: Path):
    _, _, cfg = _load(tmp_path)
    hv = MainMcpHypervisor(cfg)
    d = hv.check(
        AccessRequest(
            agent="claude_desktop",
            server_id="mirrordna_memory",
            capability=AgentCapability.SHELL_EXEC,
        )
    )
    assert d.allowed is False
    assert "not permitted for agent" in d.reason


def test_local_only_denies_external_uri(tmp_path: Path):
    _, _, cfg = _load(tmp_path)
    hv = MainMcpHypervisor(cfg)
    d = hv.check(
        AccessRequest(
            agent="codex",
            server_id="mirrordna_memory",
            capability=AgentCapability.MCP_CALL,
            tool="mirror_read_recent",
            uri="https://example.com/data",
        )
    )
    assert d.allowed is False
    assert "local-only" in d.reason


def test_network_allowlist_allows_expected_host(tmp_path: Path):
    _, _, cfg = _load(tmp_path)
    cfg.servers["google_dev_knowledge"].enabled = True
    hv = MainMcpHypervisor(cfg)

    d = hv.check(
        AccessRequest(
            agent="codex",
            server_id="google_dev_knowledge",
            capability=AgentCapability.WEB_FETCH,
            tool="knowledge_search",
            uri="https://developers.google.com/docs",
            skill="docs",
        )
    )
    assert d.allowed is True


def test_network_allowlist_denies_unknown_host(tmp_path: Path):
    _, _, cfg = _load(tmp_path)
    cfg.servers["google_dev_knowledge"].enabled = True
    hv = MainMcpHypervisor(cfg)

    d = hv.check(
        AccessRequest(
            agent="codex",
            server_id="google_dev_knowledge",
            capability=AgentCapability.WEB_FETCH,
            tool="knowledge_search",
            uri="https://evil.example.com",
            skill="docs",
        )
    )
    assert d.allowed is False
    assert "not in network allowlist" in d.reason


def test_empty_config_recovers_to_defaults(tmp_path: Path):
    state_dir = tmp_path / "state"
    path = config_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")

    cfg = load_or_create_config(path)
    assert "mirrordna_memory" in cfg.servers
