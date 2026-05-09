"""CLI entry point for Nexus AI."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from nexus.config import NexusConfig
from nexus.team import NexusTeam
from nexus.ui.app import NexusTerminal
from nexus.ui.terminal import TerminalUI

if TYPE_CHECKING:
    from nexus.core.message import Message


def setup_logging(verbose: bool) -> None:
    """Setup logging: technical logs to file, clean output to console."""
    log_dir = Path(".nexus")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "nexus.log"

    # Create formatters
    file_formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    # File handler (all logs)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Root logger setup
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    root_logger.addHandler(file_handler)

    # Suppress noisy logs from libraries
    for logger_name in ["httpx", "openai", "chromadb", "urllib3", "httpcore"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

@click.group(invoke_without_command=True)
@click.option("--config", "-c", type=click.Path(), default=None, help="Config file path")
@click.option("--provider", "-p", type=click.Choice(["nvidia", "openai", "anthropic"]), default=None)
@click.option("--model", "-m", default=None, help="LLM model name")
@click.option("--classic", is_flag=True, help="Use classic terminal (better Vietnamese IME support)")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def main(
    ctx: click.Context,
    config: str | None,
    provider: str | None,
    model: str | None,
    classic: bool,
    verbose: bool,
) -> None:
    """Nexus AI — Multi-Agent AI Development Platform."""
    setup_logging(verbose)

    cfg = NexusConfig.load(config)
    if provider:
        cfg.llm.provider = provider
    if model:
        cfg.llm.model = model

    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg

    if ctx.invoked_subcommand is None:
        if classic:
            _classic_interactive(cfg)
        else:
            _interactive(cfg)


def _interactive(config: NexusConfig) -> None:
    """Run the interactive full-screen TUI."""
    team = NexusTeam(config)
    app = NexusTerminal(config, team)
    app.run()


def _classic_interactive(config: NexusConfig) -> None:
    """Run the classic terminal UI with better IME support."""
    team = NexusTeam(config)
    ui = TerminalUI()
    ui.show_banner()

    # Hook into agent messages to display them in the UI
    def on_message(msg: Message) -> None:
        ui.show_agent_message(
            sender=msg.sender,
            recipient=msg.recipient,
            msg_type=msg.type.value,
            content=str(msg.payload.get("task") or msg.payload.get("result") or msg.payload),
        )

    team.bus.subscribe("__broadcast__", on_message)

    while True:
        try:
            query = ui.prompt()
            if not query:
                continue
            if query.lower() in ["/quit", "exit", "quit"]:
                break

            if not _handle_command(ui, team, config, query):
                with ui.status("Nexus Team is collaborating..."):
                    result = team.run(query)
                    ui.show_result(result.get("output", "Task completed."))
        except KeyboardInterrupt:
            break
        except Exception as e:
            ui.show_error(f"Error: {e}")


def _handle_command(ui: TerminalUI, team: NexusTeam, config: NexusConfig, cmd: str) -> bool:
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command == "/help":
        ui.show_help()
        return True

    if command == "/mode":
        new_mode = ui.toggle_mode()
        ui.show_info(f"  Switched mode to: {new_mode.upper()}")
        return True

    if command == "/toggle":
        ui.show_thoughts = not getattr(ui, 'show_thoughts', True)
        status = "ON" if ui.show_thoughts else "OFF"
        ui.show_info(f"  Agent thoughts visibility: {status}")
        return True

    if command == "/attach":
        if args:
            ui.show_info(f"  Attached file: {args}")
            team.memory.remember(f"User attached file: {args}", category="file_attachment")
        else:
            ui.show_error("  Usage: /attach <path/to/image_or_file>")
        return True

    if command == "/status":
        ui.status_bar.render(
            agents=team.agent_count,
            status="ready",
            memory_entries=team.memory.short_term.size,
        )
        return True

    if command == "/agents":
        for agent in team.registry.all_agents():
            ui.show_info(f"  {agent.agent_id}: {agent.role.value}")
        return True

    if command == "/memory":
        if args:
            memories = team.memory.recall(args)
            if memories:
                for mem in memories:
                    ui.show_info(f"  [{mem.metadata.get('category', '?')}] {mem.content[:200]}")
            else:
                ui.show_info("  No matching memories found.")
        else:
            ui.show_info(f"  Short-term: {team.memory.short_term.size} entries")
            context = team.memory.short_term.get_context_string(5)
            if context:
                ui.show_info(f"  Recent:\n{context}")
        return True

    if command == "/config":
        ui.show_info(f"  Provider: {config.llm.provider}")
        ui.show_info(f"  Model: {config.llm.model}")
        ui.show_info(f"  Max iterations: {config.max_iterations}")
        ui.show_info(f"  Memory dir: {config.memory.persist_dir}")
        return True

    if command == "/clear":
        team.memory.clear_short_term()
        ui.show_info("  Short-term memory cleared.")
        return True

    return False


@main.command()
@click.argument("request")
@click.pass_context
def run(ctx: click.Context, request: str) -> None:
    """Run a single request non-interactively."""
    config = ctx.obj["config"]
    team = NexusTeam(config)
    result = team.run(request)

    output = result.get("output", "")
    if isinstance(output, dict):
        output = json.dumps(output, indent=2)
    click.echo(output)

    if result.get("errors"):
        for error in result["errors"]:
            click.echo(f"ERROR: {error}", err=True)
        sys.exit(1)


@main.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize Nexus AI in the current project."""
    config = ctx.obj["config"]
    config.save()
    click.echo("Nexus AI initialized. Config saved to .nexus/config.yaml")


@main.command()
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8000, type=int, help="Port to listen on")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, reload: bool) -> None:
    """Start the web chat interface."""
    import uvicorn

    config = ctx.obj["config"]
    click.echo(f"Starting Nexus AI web interface on http://{host}:{port}")
    click.echo(f"Provider: {config.llm.provider} | Model: {config.llm.model}")
    if not config.llm.api_key:
        click.echo("Warning: No API key set — using rule-based mode")
    click.echo("Press Ctrl+C to stop\n")

    if reload:
        # Reload mode requires string import path; config from file/env only
        uvicorn.run(
            "nexus.web.server:create_app",
            host=host,
            port=port,
            reload=True,
            factory=True,
            log_level="info",
        )
    else:
        # Non-reload: pass the pre-configured app so CLI overrides are kept
        from nexus.web.server import create_app

        app = create_app(config)
        uvicorn.run(app, host=host, port=port, log_level="info")


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=9090, type=int, help="Port to listen on")
@click.pass_context
def mcp(ctx: click.Context, host: str, port: int) -> None:
    """Start the MCP tool server (Nexus Skill-Core)."""
    import uvicorn

    from nexus.mcp import MCPServer

    server = MCPServer()
    tools = server.store.list_tools()
    click.echo(f"Starting Nexus Skill-Core MCP Server on http://{host}:{port}")
    click.echo(f"Registered tools: {len(tools)}")
    for tool in tools:
        click.echo(f"  - {tool.name} ({tool.category}): {tool.source}")
    nvidia_ok = server.store.nvidia_wrapper.is_configured
    click.echo(f"NVIDIA NIM: {'configured' if nvidia_ok else 'not configured (code tools disabled)'}")
    click.echo("Press Ctrl+C to stop\n")

    app = server.create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


@main.command(name="mcp-tools")
@click.option("--category", "-c", default=None, help="Filter by category")
@click.option("--source", "-s", default=None, help="Filter by source (claude/gemini/codex)")
def mcp_tools(category: str | None, source: str | None) -> None:
    """List all available MCP tools."""
    from nexus.mcp.tools import ALL_MCP_TOOLS

    tools = ALL_MCP_TOOLS
    if category:
        tools = [t for t in tools if t.category == category]
    if source:
        tools = [t for t in tools if source in t.source]

    click.echo(f"MCP Tools ({len(tools)}):\n")
    for tool in sorted(tools, key=lambda t: (t.category, t.name)):
        click.echo(f"  [{tool.category}] {tool.name}")
        click.echo(f"    Source: {tool.source}")
        click.echo(f"    {tool.description.split('.')[0]}.")
        click.echo()


if __name__ == "__main__":
    main()
