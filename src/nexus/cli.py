"""CLI entry point for Nexus AI."""

from __future__ import annotations

import json
import logging
import sys

import click

from nexus.config import NexusConfig
from nexus.team import NexusTeam
from nexus.ui.terminal import TerminalUI


@click.group(invoke_without_command=True)
@click.option("--config", "-c", type=click.Path(), default=None, help="Config file path")
@click.option("--provider", "-p", type=click.Choice(["openai", "anthropic"]), default=None)
@click.option("--model", "-m", default=None, help="LLM model name")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def main(
    ctx: click.Context,
    config: str | None,
    provider: str | None,
    model: str | None,
    verbose: bool,
) -> None:
    """Nexus AI — Multi-Agent AI Development Platform."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    cfg = NexusConfig.load(config)
    if provider:
        cfg.llm.provider = provider
    if model:
        cfg.llm.model = model

    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg

    if ctx.invoked_subcommand is None:
        _interactive(cfg)


def _interactive(config: NexusConfig) -> None:
    """Run the interactive REPL."""
    ui = TerminalUI()
    ui.show_banner()

    team = NexusTeam(config)
    ui.show_info(f"Initialized with {team.agent_count} agents")

    if config.llm.api_key:
        ui.show_info(f"LLM: {config.llm.provider}/{config.llm.model}")
    else:
        ui.show_info("No LLM API key set — using rule-based mode (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")

    while True:
        try:
            user_input = ui.prompt()
        except (KeyboardInterrupt, EOFError):
            ui.show_info("\nGoodbye!")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.startswith("/"):
            if _handle_command(ui, team, config, user_input):
                continue
            if user_input in ("/quit", "/exit", "/q"):
                ui.show_info("Goodbye!")
                break
            continue

        ui.show_thinking("orchestrator", "Processing your request...")

        try:
            result = team.run(user_input)
        except Exception as e:
            ui.show_error(f"Error: {e}")
            continue

        output = result.get("output", "")
        if isinstance(output, dict):
            output = json.dumps(output, indent=2)

        ui.show_result(str(output))

        if result.get("errors"):
            for error in result["errors"]:
                ui.show_error(f"  {error}")


def _handle_command(ui: TerminalUI, team: NexusTeam, config: NexusConfig, cmd: str) -> bool:
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command == "/help":
        ui.show_help()
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


if __name__ == "__main__":
    main()
