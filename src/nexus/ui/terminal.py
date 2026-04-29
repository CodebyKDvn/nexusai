"""Rich terminal UI for interactive use."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

from nexus.ui.panels import AgentPanel, StatusBar

NEXUS_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "agent": "bold magenta",
    "tool": "bold blue",
})

BANNER = r"""
 _   _                        _    ___
| \ | | _____  ___   _ ___   / \  |_ _|
|  \| |/ _ \ \/ / | | / __| / _ \  | |
| |\  |  __/>  <| |_| \__ \/ ___ \ | |
|_| \_|\___/_/\_\\__,_|___/_/   \_\___|

  Multi-Agent AI Development Platform
"""


class TerminalUI:
    """Interactive terminal interface for Nexus AI."""

    def __init__(self) -> None:
        self.console = Console(theme=NEXUS_THEME)
        self.status_bar = StatusBar(self.console)
        self.agent_panel = AgentPanel(self.console)

    def show_banner(self) -> None:
        self.console.print(Text(BANNER, style="bold cyan"))
        self.console.print(
            "[dim]Type your request below. Use /help for commands, /quit to exit.[/dim]\n"
        )

    def show_help(self) -> None:
        help_text = """
## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show this help message |
| `/status` | Show system status |
| `/memory [query]` | Search memory |
| `/plan` | Show current plan |
| `/agents` | List active agents |
| `/config` | Show configuration |
| `/clear` | Clear short-term memory |
| `/quit` | Exit Nexus AI |
"""
        self.console.print(Markdown(help_text))

    def prompt(self) -> str:
        self.console.print()
        return self.console.input("[bold cyan]nexus>[/bold cyan] ")

    def show_thinking(self, agent: str, action: str) -> None:
        self.console.print(f"  [dim]{agent}[/dim] [agent]{action}[/agent]")

    def show_result(self, result: str) -> None:
        self.console.print()
        self.console.print(Panel(Markdown(result), title="Result", border_style="green"))

    def show_error(self, error: str) -> None:
        self.console.print(f"\n[error]{error}[/error]")

    def show_info(self, info: str) -> None:
        self.console.print(f"[info]{info}[/info]")

    def show_agent_message(
        self,
        sender: str,
        recipient: str,
        msg_type: str,
        content: str,
    ) -> None:
        self.agent_panel.render_message(
            sender=sender, recipient=recipient, msg_type=msg_type, content=content
        )
