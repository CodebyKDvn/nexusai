"""Rich UI panels and layout components."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class StatusBar:
    """Displays system status in a Rich table."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def render(
        self,
        *,
        agents: int = 0,
        iteration: int = 0,
        max_iterations: int = 20,
        status: str = "idle",
        memory_entries: int = 0,
    ) -> None:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="bold cyan")
        table.add_column()

        table.add_row("Status", Text(status.upper(), style="bold #A8D5BA" if status == "idle" else "bold #a166ab"))
        table.add_row("Agents", f"[#00f2fe]{agents}[/]")
        table.add_row("Iteration", f"[#a166ab]{iteration}[/]/[dim]{max_iterations}[/dim]")
        table.add_row("Memory", f"[#ff9a9e]{memory_entries}[/]")

        self.console.print(Panel(table, title="[bold #00f2fe]N E X U S[/]", border_style="#a166ab"))


class AgentPanel:
    """Displays agent activity in a Rich panel."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def render_message(
        self,
        *,
        sender: str,
        recipient: str,
        msg_type: str,
        content: str,
    ) -> None:
        style_map = {
            "task_request": "#a166ab",
            "task_result": "#A8D5BA",
            "error": "#ff9a9e",
            "query": "#00f2fe",
            "status": "dim",
            "reflection": "#a166ab",
        }
        style = style_map.get(msg_type, "white")

        header = Text(f" {sender} ➔ {recipient} ", style=f"bold {style} on #1a1a1a")
        body = content[:1000]
        if len(content) > 1000:
            body += "\n[dim]... content truncated ...[/dim]"

        self.console.print(Panel(body, title=header, border_style=style, padding=(0, 2)))

    def render_plan(self, plan: dict) -> None:  # type: ignore[type-arg]
        table = Table(title="Execution Plan", show_lines=True)
        table.add_column("#", style="bold", width=4)
        table.add_column("Step", min_width=30)
        table.add_column("Agent", style="cyan", width=12)
        table.add_column("Deps", width=10)
        table.add_column("Complexity", width=10)

        for step in plan.get("steps", []):
            deps = ", ".join(str(d) for d in step.get("dependencies", []))
            table.add_row(
                str(step.get("id", "")),
                step.get("description", ""),
                step.get("agent", ""),
                deps or "-",
                step.get("estimated_complexity", ""),
            )

        self.console.print(table)

    def render_evaluation(self, evaluation: dict) -> None:  # type: ignore[type-arg]
        scores = evaluation.get("scores", {})
        table = Table(title="Quality Evaluation", show_lines=True)
        table.add_column("Criterion", style="bold")
        table.add_column("Score", justify="center")

        for criterion, score in scores.items():
            color = "green" if score >= 7 else "yellow" if score >= 5 else "red"
            table.add_row(criterion.replace("_", " ").title(), f"[{color}]{score}/10[/{color}]")

        overall = evaluation.get("overall_score", 0)
        overall_color = "green" if overall >= 7 else "yellow" if overall >= 5 else "red"
        table.add_row(
            "[bold]Overall[/bold]",
            f"[bold {overall_color}]{overall}/10[/bold {overall_color}]",
        )

        self.console.print(table)

        verdict = evaluation.get("verdict", "unknown")
        verdict_style = "bold green" if verdict == "approve" else "bold red"
        self.console.print(f"\nVerdict: [{verdict_style}]{verdict.upper()}[/{verdict_style}]")
