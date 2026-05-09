"""Textual TUI application for Nexus AI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.align import Align
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static

from nexus.core.repo import RepoIntelligence

if TYPE_CHECKING:
    from nexus.config import NexusConfig
    from nexus.core.message import Message
    from nexus.team import NexusTeam


class NexusTerminal(App):  # type: ignore[type-arg]
    """A Textual app for Nexus AI."""

    CSS = """
    Screen {
        background: #0f0f13;
        color: white;
    }

    #sidebar {
        width: 30%;
        dock: right;
        border-left: solid #2a2a35;
        padding: 1;
        background: #111116;
    }

    #chat-log {
        height: 1fr;
        padding: 1;
        overflow-y: scroll;
        border: none;
        background: transparent;
    }

    #input-container {
        height: 3;
        dock: bottom;
        margin: 0 1 1 1;
    }

    Input {
        background: #1e1e24;
        border: round #a166ab;
        color: white;
    }

    Input:focus {
        border: round #00f2fe;
    }

    .sidebar-title {
        color: #00f2fe;
        text-style: bold;
        padding-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+p", "toggle_plan", "Mode: PLAN"),
        Binding("ctrl+f", "toggle_fast", "Mode: FAST"),
        Binding("ctrl+t", "toggle_thoughts", "Thoughts: ON"),
        Binding("ctrl+i", "index_codebase", "Index Repo"),
    ]

    def __init__(self, config: NexusConfig, team: NexusTeam) -> None:
        super().__init__()
        self.config = config
        self.team = team
        self.mode = "THINKING"
        self.show_thoughts = True
        self.iteration = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical():
                self.chat_log = RichLog(id="chat-log", markup=True)
                yield self.chat_log
                with Container(id="input-container"):
                    self.input_widget = Input(
                        placeholder="> Type here... (Ctrl+T toggle thoughts, /attach to upload)",
                        id="chat-input",
                    )
                    yield self.input_widget
            with Vertical(id="sidebar"):
                yield Static("TASKS", classes="sidebar-title")
                self.tasks_log = RichLog(id="tasks-log", markup=True)
                self.tasks_log.styles.height = 10
                yield self.tasks_log
                yield Static("\nSESSION", classes="sidebar-title")
                self.session_log = Static("Status: [bold #A8D5BA]Ready[/]")
                yield self.session_log
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Nexus AI Dashboard"
        self.sub_title = f"Model: {self.config.llm.model}"
        welcome = r"""
[bold #00f2fe]██\      ██\[/]
[bold #40c6fe]████\    ██ |[/]
[bold #809afe]██ |\██\ ██ |[/]
[bold #a166ab]██ | \█████ |[/]
[bold #d080a4]██ |  \████ |[/]
[bold #ff9a9e]\__|   \____|[/]
   [bold #a166ab]N E X U S   A I[/]
   [italic #ff9a9e]Multi-Agent Platform[/]

[dim]Type your request below to start collaborating.[/dim]
"""
        padding = "\n" * 5
        self.chat_log.write(Align.center(Text.from_markup(padding + welcome)))
        self.input_widget.focus()

        def on_message(msg: Message) -> None:
            self.call_from_thread(self.handle_agent_message, msg)

        self.team.bus.subscribe("__broadcast__", on_message)

    def handle_agent_message(self, msg: Message) -> None:
        payload: dict[str, Any] = msg.payload
        content = str(
            payload.get("task") or payload.get("result") or payload.get("error") or payload
        )
        short_content = content.split("\n")[0][:80]

        if msg.type.value == "task_result":
            self.tasks_log.write(f"[bold #A8D5BA]✓[/] {short_content}")
            self.chat_log.write(f"\n[bold #A8D5BA]Result:[/] {content}\n\n")
        elif msg.type.value == "error":
            self.chat_log.write(f"\n[bold #ff9a9e]Error:[/] {content}\n")
        else:
            if self.show_thoughts:
                self.chat_log.write(
                    f"[dim]{msg.sender}[/] ➔ [dim]{msg.recipient}[/]: {short_content}"
                )
            self.session_log.update(f"Status: [bold #a166ab]{msg.sender}[/] is working")

        self.iteration += 1

    @work(thread=True)
    def run_nexus_team(self, query: str) -> None:
        self.call_from_thread(self.chat_log.write, f"[bold #00f2fe]> {query}[/]\n")
        try:
            self.team.run(query)
        except Exception as e:
            self.call_from_thread(
                self.chat_log.write, f"[bold #ff9a9e]System Error:[/] {e}\n"
            )

        self.call_from_thread(self.session_log.update, "Status: [bold #A8D5BA]Ready[/]")

        def reset_input() -> None:
            self.input_widget.disabled = False
            self.input_widget.focus()

        self.call_from_thread(reset_input)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if not event.value.strip():
            return

        query = event.value.strip()
        self.input_widget.value = ""

        if query == "/quit":
            self.exit()
            return

        if query.startswith("/attach"):
            self.chat_log.write(f"[bold #a166ab]Attached file:[/] {query[8:]}\n")
            self.team.memory.remember(
                f"User attached file: {query[8:]}", category="file_attachment"
            )
            return

        if query == "/index":
            self.action_index_codebase()
            return

        if query == "/gitnexus":
            self.config.gitnexus = not self.config.gitnexus
            status = "ENABLED" if self.config.gitnexus else "DISABLED"
            self.chat_log.write(f"[italic #00f2fe]GitNexus Intelligence: {status}[/]\n")
            return

        self.input_widget.disabled = True
        self.session_log.update("Status: [bold #00f2fe]Running...[/]")
        self.run_nexus_team(query)

    def action_toggle_thoughts(self) -> None:
        self.show_thoughts = not self.show_thoughts
        status = "ON" if self.show_thoughts else "OFF"
        self.chat_log.write(f"[italic #a166ab]Thoughts visibility: {status}[/]\n")

    def action_toggle_plan(self) -> None:
        self.mode = "PLAN"
        self.chat_log.write("[italic #00f2fe]Switched to PLAN mode[/]\n")

    def action_toggle_fast(self) -> None:
        self.mode = "FAST"
        self.chat_log.write("[italic #00f2fe]Switched to FAST mode[/]\n")

    @work(thread=True)
    def action_index_codebase(self) -> None:
        self.call_from_thread(
            self.chat_log.write, "[bold #a166ab]Indexing codebase with GitNexus...[/]\n"
        )
        self.call_from_thread(
            self.session_log.update, "Status: [bold #a166ab]Indexing...[/]"
        )

        repo_intel = RepoIntelligence(self.config.project_dir)
        output = repo_intel.analyze()

        if "Error" in output:
            self.call_from_thread(
                self.chat_log.write, f"[bold #ff9a9e]Indexing Failed:[/] {output}\n"
            )
        else:
            self.config.gitnexus = True
            self.call_from_thread(
                self.chat_log.write,
                "[bold #A8D5BA]Indexing Complete![/] Context files updated.\n",
            )
            self.call_from_thread(
                self.chat_log.write,
                "[dim]Nexus AI will now use the Repo Map to save tokens.[/]\n",
            )

        self.call_from_thread(
            self.session_log.update, "Status: [bold #A8D5BA]Ready[/]"
        )
