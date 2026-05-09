"""Rich terminal UI for interactive use."""

from __future__ import annotations

from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style as PTStyle
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme

from nexus.ui.panels import AgentPanel, StatusBar

NEXUS_THEME = Theme(
    {
        "info": "#00f2fe",
        "warning": "#ff9a9e",
        "error": "bold #ff9a9e",
        "success": "bold #A8D5BA",
        "agent": "bold #a166ab",
        "tool": "bold #00f2fe",
        "nexus": "bold #00f2fe",
        "prompt": "bold #a166ab",
    }
)

BANNER = r"""
             [#00f2fe]██\      ██\[/]
             [#40c6fe]████\    ██ |[/]
             [#809afe]██ |\██\ ██ |[/]
             [#a166ab]██ | \█████ |[/]
             [#d080a4]██ |  \████ |[/]
             [#ff9a9e]\__|   \____|[/]

[bold #a166ab]   N   E   X   U   S      A   I   [/]
[italic #ff9a9e]      Multi-Agent Intelligence Platform[/]
"""


class TerminalUI:
    """Interactive terminal interface for Nexus AI."""

    def __init__(self) -> None:
        self.console = Console(theme=NEXUS_THEME)
        self.status_bar = StatusBar(self.console)
        self.agent_panel = AgentPanel(self.console)
        self.ui_mode = "thinking"
        self.show_thoughts = True
        self._session: PromptSession[str] | None = None

    def show_banner(self) -> None:
        self.console.print(BANNER)

        welcome_text = """[bold white]Welcome to Nexus AI![/]

  [#a166ab]1.[/] /plan Design architecture for a Chat app
  [#a166ab]2.[/] Create login module with JWT and refresh token
  [#a166ab]3.[/] /mode fast Optimize the system
"""
        self.console.print(Panel(welcome_text, border_style="#00f2fe", expand=False))
        self.console.print()

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

    def _setup_prompt(self) -> None:
        style = PTStyle.from_dict(
            {
                "bottom-toolbar": "bg:#111111 #00f2fe",
                "prompt": "bold #a166ab",
            }
        )
        self._session = PromptSession(
            style=style,
            placeholder=HTML(
                '<style color="#888888"> Type here... (use /help, /mode, /attach)</style>'
            ),
        )

    def toggle_mode(self) -> str:
        modes = ["thinking", "fast", "plan"]
        idx = modes.index(self.ui_mode)
        self.ui_mode = modes[(idx + 1) % len(modes)]
        return self.ui_mode

    def prompt(self) -> str:
        self.console.print()

        def bottom_toolbar() -> str:
            thoughts_status = "ON" if self.show_thoughts else "OFF"
            return f" Nexus AI | Mode: {self.ui_mode.upper()} | Thoughts: {thoughts_status}"

        if self._session is None:
            self._setup_prompt()
        assert self._session is not None

        result: str = self._session.prompt("nexus > ", bottom_toolbar=bottom_toolbar)
        return result

    def status(self, message: str) -> Any:
        """Return a rich status context manager."""
        return self.console.status(f"[bold #A8D5BA]{message}[/]", spinner="dots12")

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
