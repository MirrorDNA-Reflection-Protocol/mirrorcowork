"""
MirrorCowork CLI

Command-line interface for the sovereign agentic governance layer.
Routes tasks through reflection before execution.

Usage:
    mirrorcowork route "Refactor the auth module"
    mirrorcowork status
    mirrorcowork watch  # Event-driven daemon mode
    mw route "Fix the bug in login"  # Short alias
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mirrorcowork.bridge.mirrorbrain import MirrorBrainBridge, create_context_provider
from mirrorcowork.events.watcher import EventCoordinator
from mirrorcowork.mcp.hypervisor import (
    AccessRequest,
    MainMcpHypervisor,
    config_path as mcp_config_path,
    load_or_create_config,
)
from mirrorcowork.router.reflection import ReflectionRouter
from mirrorcowork.router.sovereign import SovereignRouter
from mirrorcowork.sovereignty.conscience import Conscience
from mirrorcowork.sovereignty.crystallization import refine_intent
from mirrorcowork.state.task import AgentCapability, ReflectionOutcome, Task, TaskIntent

app = typer.Typer(
    name="mirrorcowork",
    help="Sovereign agentic governance layer for multi-agent orchestration",
    no_args_is_help=True,
)
console = Console()

# Default state directory
DEFAULT_STATE_DIR = Path.home() / ".mirrordna"


def get_router(state_dir: Path | None = None) -> ReflectionRouter:
    """Get a configured ReflectionRouter"""
    router = ReflectionRouter(state_dir=state_dir or DEFAULT_STATE_DIR)

    # Add MirrorBrain context provider
    router.add_context_provider(create_context_provider(state_dir))

    # Register known agents
    router.register_agent("claude_code", [
        AgentCapability.CODE_WRITE,
        AgentCapability.CODE_READ,
        AgentCapability.FILE_WRITE,
        AgentCapability.FILE_READ,
        AgentCapability.GIT_COMMIT,
        AgentCapability.GIT_PUSH,
        AgentCapability.SHELL_EXEC,
        AgentCapability.MCP_CALL,
    ])
    router.register_agent("antigravity", [
        AgentCapability.CODE_WRITE,
        AgentCapability.CODE_READ,
        AgentCapability.FILE_WRITE,
        AgentCapability.FILE_READ,
        AgentCapability.GIT_COMMIT,
        AgentCapability.SHELL_EXEC,
        AgentCapability.WEB_FETCH,
    ])
    router.register_agent("codex", [
        AgentCapability.CODE_WRITE,
        AgentCapability.CODE_READ,
        AgentCapability.FILE_WRITE,
        AgentCapability.FILE_READ,
        AgentCapability.GIT_COMMIT,
        AgentCapability.SHELL_EXEC,
        AgentCapability.WEB_FETCH,
        AgentCapability.MCP_CALL,
    ])
    router.register_agent("claude_desktop", [
        AgentCapability.CODE_READ,
        AgentCapability.FILE_READ,
        AgentCapability.WEB_FETCH,
        AgentCapability.HUMAN_INTERACT,
    ])

    return router


@app.command()
def route(
    description: Annotated[str, typer.Argument(help="Task description")],
    source: Annotated[str, typer.Option("--source", "-s", help="Source client")] = "cli",
    intent: Annotated[str, typer.Option("--intent", "-i", help="Task intent")] = "execute",
    target: Annotated[Optional[str], typer.Option("--target", "-t", help="Target agent")] = None,
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """Route a task through reflection"""
    router = get_router(state_dir)

    # Parse intent
    try:
        task_intent = TaskIntent(intent)
    except ValueError:
        console.print(f"[red]Invalid intent: {intent}[/red]")
        console.print(f"Valid intents: {', '.join(i.value for i in TaskIntent)}")
        raise typer.Exit(1)

    # Create task
    task = Task(
        description=description,
        source_client=source,
        intent=task_intent,
        target_agent=target,
    )

    # Route through reflection
    result = asyncio.run(router.submit(task))

    # Display result
    outcome_colors = {
        ReflectionOutcome.PROCEED: "green",
        ReflectionOutcome.MODIFY: "yellow",
        ReflectionOutcome.ESCALATE: "red",
        ReflectionOutcome.REJECT: "red",
        ReflectionOutcome.DECOMPOSE: "blue",
        ReflectionOutcome.CLARIFY: "yellow",
    }

    color = outcome_colors.get(result.outcome, "white")

    console.print(Panel(
        f"[bold]Task ID:[/bold] {result.task_id}\n"
        f"[bold]Outcome:[/bold] [{color}]{result.outcome.value.upper()}[/{color}]\n"
        f"[bold]Notes:[/bold] {result.notes}",
        title="Reflection Result",
        border_style=color,
    ))

    # Show queue status
    status = router.get_queue_status()
    console.print(f"\n[dim]Queue: {status['ready']} ready, {status['pending']} pending[/dim]")


@app.command()
def status(
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Show current router status"""
    router = get_router(state_dir)
    queue_status = router.get_queue_status()

    if json_output:
        console.print(json.dumps(router.export_state(), indent=2, default=str))
        return

    # Queue status table
    table = Table(title="Queue Status")
    table.add_column("State", style="cyan")
    table.add_column("Count", justify="right")

    table.add_row("Pending", str(queue_status["pending"]))
    table.add_row("In Reflection", str(queue_status["in_reflection"]))
    table.add_row("Ready", str(queue_status["ready"]), style="green")
    table.add_row("Completed", str(queue_status["completed"]), style="dim")

    console.print(table)

    # MirrorBrain status
    bridge = MirrorBrainBridge(state_dir or DEFAULT_STATE_DIR)
    snapshot = bridge.get_full_snapshot()

    if snapshot.last_action:
        console.print(Panel(
            f"[bold]Last Client:[/bold] {snapshot.last_client or 'unknown'}\n"
            f"[bold]Last Action:[/bold] {snapshot.last_action}\n"
            f"[bold]Pending Items:[/bold] {len(snapshot.pending_items)}\n"
            f"[bold]Alerts:[/bold] {len(snapshot.alerts)}",
            title="MirrorBrain State",
        ))


@app.command()
def next(
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """Get the next task ready for execution"""
    router = get_router(state_dir)
    task = router.get_next_task()

    if not task:
        console.print("[dim]No tasks ready for execution[/dim]")
        return

    console.print(Panel(
        f"[bold]ID:[/bold] {task.id}\n"
        f"[bold]Description:[/bold] {task.get_effective_description()}\n"
        f"[bold]Source:[/bold] {task.source_client}\n"
        f"[bold]Target:[/bold] {task.target_agent or 'any'}",
        title="Next Task",
        border_style="green",
    ))


@app.command()
def complete(
    task_id: Annotated[str, typer.Argument(help="Task ID to complete")],
    result: Annotated[Optional[str], typer.Option("--result", "-r", help="Result JSON")] = None,
    error: Annotated[Optional[str], typer.Option("--error", "-e", help="Error message")] = None,
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """Mark a task as completed"""
    router = get_router(state_dir)

    result_dict = None
    if result:
        try:
            result_dict = json.loads(result)
        except json.JSONDecodeError:
            result_dict = {"output": result}

    completed = router.complete_task(task_id, result=result_dict, error=error)

    if completed:
        console.print(f"[green]Task {task_id} completed[/green]")
    else:
        console.print(f"[red]Task {task_id} not found in ready queue[/red]")


@app.command()
def watch(
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """
    Run in daemon mode, watching for events.

    This is the event-driven mode that watches for:
    - Handoff changes
    - Task completions
    - Queue updates

    No polling - uses filesystem watchers.
    """
    coordinator = EventCoordinator(state_dir or DEFAULT_STATE_DIR)

    def on_handoff(data):
        console.print(f"[cyan]Handoff update:[/cyan] {data.get('last_action', 'unknown')}")
        if data.get("pending_items"):
            console.print(f"  Pending: {data['pending_items']}")

    def on_completion(task_id, data):
        console.print(f"[green]Task completed:[/green] {task_id}")
        if data.get("error"):
            console.print(f"  [red]Error:[/red] {data['error']}")

    coordinator.on_handoff(on_handoff)
    coordinator.on_completion(on_completion)

    console.print("[bold]MirrorCowork daemon started[/bold]")
    console.print(f"Watching: {state_dir or DEFAULT_STATE_DIR}")
    console.print("Press Ctrl+C to stop\n")

    try:
        with coordinator:
            while True:
                asyncio.get_event_loop().run_until_complete(asyncio.sleep(1))
    except KeyboardInterrupt:
        console.print("\n[dim]Shutting down...[/dim]")


@app.command()
def handoff(
    summary: Annotated[str, typer.Argument(help="Handoff summary")],
    next_client: Annotated[Optional[str], typer.Option("--next", "-n", help="Next client")] = None,
    pending: Annotated[Optional[str], typer.Option("--pending", "-p", help="Pending items (comma-separated)")] = None,
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """Write a handoff for the next client"""
    bridge = MirrorBrainBridge(state_dir or DEFAULT_STATE_DIR)

    pending_items = pending.split(",") if pending else None

    success = asyncio.run(bridge.write_handoff(
        summary=summary,
        pending_items=pending_items,
        next_client=next_client,
    ))

    if success:
        console.print("[green]Handoff written successfully[/green]")
    else:
        console.print("[red]Failed to write handoff[/red]")


@app.command()
def export(
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output file")] = None,
):
    """Export full router state"""
    router = get_router(state_dir)
    state = router.export_state()

    output_json = json.dumps(state, indent=2, default=str)

    if output:
        output.write_text(output_json)
        console.print(f"[green]State exported to {output}[/green]")
    else:
        console.print(output_json)


# === MAIN MCP HYPERVISOR COMMANDS ===
mcp_app = typer.Typer(help="Main MCP hypervisor (nested servers + firewall policy)")
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("init")
def mcp_init(
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
    force_reset: Annotated[bool, typer.Option("--force-reset", help="Overwrite with defaults")] = False,
):
    """Create (or load) the Main MCP hypervisor config."""
    sd = state_dir or DEFAULT_STATE_DIR
    path = mcp_config_path(sd)
    existed = path.exists()
    load_or_create_config(path, force_reset=force_reset)
    status = "reset" if force_reset and existed else "created" if not existed else "loaded"
    console.print(f"[green]Main MCP config {status}:[/green] {path}")


@mcp_app.command("list")
def mcp_list(
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """List nested MCP servers and key policy controls."""
    sd = state_dir or DEFAULT_STATE_DIR
    cfg = load_or_create_config(mcp_config_path(sd))

    table = Table(title="Nested MCP Servers")
    table.add_column("Server")
    table.add_column("Enabled", justify="center")
    table.add_column("Tier")
    table.add_column("Local")
    table.add_column("Clients")
    table.add_column("Capabilities")

    for server in sorted(cfg.servers.values(), key=lambda s: s.id):
        caps = ",".join(cap.value for cap in server.allow_capabilities) or "*"
        clients = ",".join(server.allow_clients) or "*"
        table.add_row(
            server.id,
            "yes" if server.enabled else "no",
            server.tier,
            "yes" if server.local_only else "no",
            clients,
            caps,
        )

    console.print(table)
    console.print(
        f"[dim]Policy: default_deny={cfg.default_deny}, kill_switch={cfg.kill_switch}, "
        f"agents={len(cfg.agent_capability_matrix)}[/dim]"
    )


@mcp_app.command("check")
def mcp_check(
    agent: Annotated[str, typer.Argument(help="Requesting agent id")],
    server_id: Annotated[str, typer.Argument(help="Nested server id")],
    capability: Annotated[str, typer.Argument(help="Capability enum value (e.g. mcp_call)")],
    tool: Annotated[Optional[str], typer.Option("--tool", help="Tool name")] = None,
    uri: Annotated[Optional[str], typer.Option("--uri", help="Target URI for network checks")] = None,
    skill: Annotated[Optional[str], typer.Option("--skill", help="Skill name")] = None,
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """Run a firewall/capability check through the Main MCP hypervisor."""
    sd = state_dir or DEFAULT_STATE_DIR
    cfg = load_or_create_config(mcp_config_path(sd))
    hv = MainMcpHypervisor(cfg)

    try:
        cap = AgentCapability(capability)
    except ValueError:
        console.print(f"[red]Invalid capability:[/red] {capability}")
        console.print("Valid: " + ", ".join(c.value for c in AgentCapability))
        raise typer.Exit(1)

    req = AccessRequest(
        agent=agent,
        server_id=server_id,
        capability=cap,
        tool=tool,
        uri=uri,
        skill=skill,
    )
    decision = hv.check(req)

    color = "green" if decision.allowed else "red"
    console.print(
        Panel(
            f"[bold]Allowed:[/bold] [{color}]{decision.allowed}[/{color}]\n"
            f"[bold]Reason:[/bold] {decision.reason}\n"
            f"[bold]Rules:[/bold] {', '.join(decision.matched_rules) if decision.matched_rules else '(none)'}",
            title="Main MCP Decision",
            border_style=color,
        )
    )
    if not decision.allowed:
        raise typer.Exit(2)


# === SOVEREIGN COMMANDS ===
# These use the full dream stack: crystallization + conscience + temporal

sovereign_app = typer.Typer(help="Sovereign routing with full dream stack")
app.add_typer(sovereign_app, name="sovereign")


@sovereign_app.command("route")
def sovereign_route(
    description: Annotated[str, typer.Argument(help="Task description")],
    source: Annotated[str, typer.Option("--source", "-s", help="Source client")] = "cli",
    files: Annotated[Optional[str], typer.Option("--files", "-f", help="Affected files (comma-separated)")] = None,
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """
    Route through the FULL sovereign stack:
    - Intent crystallization (refine vague intents)
    - Conscience check (ethical memory)
    - Temporal analysis (causal impact)
    - Reflection (safety patterns)
    """
    router = SovereignRouter(state_dir=state_dir)

    files_affected = files.split(",") if files else None

    result = asyncio.run(router.route(
        description=description,
        source=source,
        files_affected=files_affected,
    ))

    # Verdict colors
    verdict_colors = {
        "proceed": "green",
        "clarify": "yellow",
        "reconsider": "red",
        "block": "red bold",
    }
    color = verdict_colors.get(result.verdict, "white")

    # Main result panel
    console.print(Panel(
        f"[bold]Task ID:[/bold] {result.task_id}\n"
        f"[bold]Verdict:[/bold] [{color}]{result.verdict.upper()}[/{color}]\n"
        f"[bold]Explanation:[/bold] {result.explanation}",
        title="Sovereign Routing Result",
        border_style=color.split()[0],  # Handle "red bold" -> "red"
    ))

    # Crystal details
    if result.crystal:
        clarity_colors = {
            "amorphous": "red",
            "translucent": "yellow",
            "clear": "green",
            "crystalline": "green bold",
        }
        clarity_color = clarity_colors.get(result.intent_clarity, "white")

        console.print(Panel(
            f"[bold]Clarity:[/bold] [{clarity_color}]{result.intent_clarity}[/{clarity_color}]\n"
            f"[bold]Specificity:[/bold] {result.crystal.specificity_score:.0%}\n"
            f"[bold]Refined Intent:[/bold] {result.crystal.refined_intent or result.crystal.raw_intent}",
            title="Intent Crystal",
        ))

        if result.crystal.ambiguity_flags:
            console.print("[yellow]Ambiguities:[/yellow]")
            for flag in result.crystal.ambiguity_flags:
                console.print(f"  - {flag}")

        if result.crystal.constraints:
            console.print("[cyan]Constraints discovered:[/cyan]")
            for c in result.crystal.constraints[:3]:
                console.print(f"  - {c.description}")

    # Ethical check details
    if result.ethical_check and result.ethical_check.concerns:
        console.print(Panel(
            f"[bold]Concerns:[/bold] {len(result.ethical_check.concerns)}\n"
            f"[bold]Max Severity:[/bold] {result.ethical_check.max_severity.value}\n"
            f"[bold]Memories Recalled:[/bold] {result.conscience_memories}",
            title="Conscience Check",
        ))

        for concern in result.ethical_check.concerns[:3]:
            severity_color = {"critical": "red", "warning": "yellow", "caution": "blue"}.get(concern["severity"], "white")
            console.print(f"  [{severity_color}][{concern['severity'].upper()}][/{severity_color}] {concern['description']}")

    # Temporal impact
    if result.would_contradict:
        console.print(Panel(
            "[bold]This task would contradict previous work:[/bold]\n" +
            "\n".join(f"  - {c}" for c in result.would_contradict),
            title="Temporal Impact",
            border_style="red",
        ))

    # Clarification needed
    if result.clarification_needed:
        console.print("\n[yellow bold]Clarification needed:[/yellow bold]")
        for item in result.clarification_needed:
            console.print(f"  - {item}")


@sovereign_app.command("crystallize")
def crystallize_intent(
    description: Annotated[str, typer.Argument(help="Raw intent to crystallize")],
):
    """Crystallize a vague intent into something executable"""
    crystal = refine_intent(description)

    clarity_colors = {
        "amorphous": "red",
        "translucent": "yellow",
        "clear": "green",
        "crystalline": "green bold",
    }
    color = clarity_colors.get(crystal.clarity.value, "white")

    console.print(Panel(
        f"[bold]Raw Intent:[/bold] {crystal.raw_intent}\n"
        f"[bold]Clarity:[/bold] [{color}]{crystal.clarity.value.upper()}[/{color}]\n"
        f"[bold]Specificity:[/bold] {crystal.specificity_score:.0%}\n"
        f"[bold]Refined:[/bold] {crystal.refined_intent or '(no refinement yet)'}",
        title="Intent Crystal",
        border_style=color.split()[0],
    ))

    if crystal.ambiguity_flags:
        console.print("\n[yellow]Ambiguities found:[/yellow]")
        for flag in crystal.ambiguity_flags:
            console.print(f"  - {flag}")

    if crystal.constraints:
        console.print("\n[cyan]Constraints:[/cyan]")
        for c in crystal.constraints:
            console.print(f"  - [{c.type}] {c.description}")

    if crystal.success_criteria:
        console.print("\n[green]Success criteria:[/green]")
        for s in crystal.success_criteria:
            console.print(f"  - {s.description}")

    console.print(f"\n[dim]Executable: {crystal.is_executable()}[/dim]")


@sovereign_app.command("conscience")
def check_conscience(
    description: Annotated[str, typer.Argument(help="Task to check ethically")],
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """Check a task against the ethical conscience"""
    conscience = Conscience(state_dir=state_dir or DEFAULT_STATE_DIR / "mirrorcowork")
    check = conscience.evaluate(description)

    # Recommendation colors
    rec_colors = {
        "proceed": "green",
        "caution": "yellow",
        "reconsider": "red",
        "block": "red bold",
    }
    color = rec_colors.get(check.recommendation, "white")

    console.print(Panel(
        f"[bold]Recommendation:[/bold] [{color}]{check.recommendation.upper()}[/{color}]\n"
        f"[bold]Max Severity:[/bold] {check.max_severity.value}\n"
        f"[bold]Concerns:[/bold] {len(check.concerns)}\n"
        f"[bold]Relevant Memories:[/bold] {len(check.relevant_memories)}",
        title="Conscience Check",
        border_style=color.split()[0],
    ))

    if check.concerns:
        console.print("\n[bold]Concerns:[/bold]")
        for c in check.concerns:
            severity_color = {"critical": "red", "warning": "yellow", "caution": "blue", "info": "dim"}.get(c["severity"], "white")
            console.print(f"  [{severity_color}][{c['category'].upper()}][/{severity_color}] {c['description']}")

    if check.relevant_memories:
        console.print("\n[bold]Relevant past experiences:[/bold]")
        for m in check.relevant_memories[:3]:
            outcome_color = {"regret": "red", "failure": "yellow", "success": "green"}.get(m.outcome, "white")
            console.print(f"  - [{outcome_color}]{m.task_summary[:60]}...[/{outcome_color}]")
            if m.lesson:
                console.print(f"    Lesson: {m.lesson}")

    if check.conditions_to_proceed:
        console.print("\n[yellow]Conditions to proceed:[/yellow]")
        for condition in check.conditions_to_proceed:
            console.print(f"  - {condition}")


@sovereign_app.command("wisdom")
def show_wisdom(
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """Show accumulated wisdom statistics"""
    router = SovereignRouter(state_dir=state_dir)
    wisdom = router.get_wisdom()

    table = Table(title="Accumulated Wisdom")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    # Conscience stats
    conscience = wisdom["conscience"]
    table.add_row("Total Memories", str(conscience["total_memories"]))
    table.add_row("Total Checks", str(conscience["total_checks"]))
    table.add_row("Blocks Issued", str(conscience["blocks_issued"]), style="red" if conscience["blocks_issued"] > 0 else "dim")
    table.add_row("Regrets Recorded", str(conscience["regrets_recorded"]), style="yellow" if conscience["regrets_recorded"] > 0 else "dim")
    table.add_row("Bad Patterns Learned", str(conscience["bad_patterns_learned"]))
    table.add_row("Good Patterns Learned", str(conscience["good_patterns_learned"]))
    table.add_row("", "")
    table.add_row("Temporal Chains", str(wisdom["temporal_chains"]))
    table.add_row("Temporal Nodes", str(wisdom["temporal_nodes"]))
    table.add_row("Crystallizer Patterns", str(wisdom["crystallizer_patterns"]))

    console.print(table)

    if conscience["timing_risks"]:
        console.print("\n[yellow]Timing risks learned:[/yellow]")
        for day, risks in conscience["timing_risks"].items():
            console.print(f"  {day}: {len(risks)} incidents")


@sovereign_app.command("regret")
def record_regret(
    task_id: Annotated[str, typer.Argument(help="Task ID that was regretted")],
    lesson: Annotated[str, typer.Option("--lesson", "-l", help="What did we learn?")] = "Unspecified regret",
    state_dir: Annotated[Optional[Path], typer.Option("--state-dir", help="State directory")] = None,
):
    """Record that a past decision was regretted (teaches the conscience)"""
    router = SovereignRouter(state_dir=state_dir)
    router.record_outcome(task_id, "regret", was_regret=True, lesson=lesson)

    console.print(f"[yellow]Regret recorded for task {task_id}[/yellow]")
    console.print(f"[dim]Lesson learned: {lesson}[/dim]")
    console.print("\n[green]The conscience will remember this for future decisions.[/green]")


if __name__ == "__main__":
    app()
