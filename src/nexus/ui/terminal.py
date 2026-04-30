"""Rich terminal UI for interactive use."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme
from rich.columns import Columns

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

from nexus.ui.panels import AgentPanel, StatusBar

NEXUS_THEME = Theme({
    "info": "#00f2fe",      # Cyan
    "warning": "#ff9a9e",   # Pink/Orange
    "error": "bold #ff9a9e",
    "success": "bold #A8D5BA",
    "agent": "bold #a166ab", # Purple
    "tool": "bold #00f2fe",  # Cyan
    "nexus": "bold #00f2fe",
    "prompt": "bold #a166ab",
})

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

    def show_banner(self) -> None:
        self.console.print(BANNER)
        
        # ChatGPT-like Greeting Suggestions
        welcome_text = """[bold white]Chào mừng bạn đến với Nexus AI![/]

💡 [dim]Gợi ý cho bạn:[/dim]
  [#a166ab]1.[/] /plan Thiết kế kiến trúc cho ứng dụng Chat
  [#a166ab]2.[/] Tạo module đăng nhập với JWT và refresh token
  [#a166ab]3.[/] /mode fast Tối ưu hóa file index.html
  [#a166ab]4.[/] /attach <kéo-thả-hình-ảnh-vào-đây>
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

    def setup_prompt(self):
        style = Style.from_dict({
            'bottom-toolbar': 'bg:#111111 #00f2fe',
            'prompt': 'bold #a166ab',
        })
        self.session = PromptSession(
            style=style,
            placeholder=HTML('<style color="#888888"> Type here... (use /help, /mode, /attach)</style>'),
        )
        self.ui_mode = "thinking" # thinking, fast, plan
        self.show_thoughts = True

    def toggle_mode(self):
        modes = ["thinking", "fast", "plan"]
        idx = modes.index(self.ui_mode)
        self.ui_mode = modes[(idx + 1) % len(modes)]
        return self.ui_mode
        
    def prompt(self) -> str:
        self.console.print()
        
        def bottom_toolbar():
            thoughts_status = "ON" if self.show_thoughts else "OFF"
            return HTML(f' <b>Nexus AI</b> | Mode: <b>{self.ui_mode.upper()}</b> | Thoughts: <b>{thoughts_status}</b> | <i>Press Tab for autocomplete</i>')

        if not hasattr(self, 'session'):
            self.setup_prompt()

        return self.session.prompt("nexus > ", bottom_toolbar=bottom_toolbar)

    def status(self, message: str):
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
