from __future__ import annotations

import time
from pathlib import Path

from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.spinner import Spinner

class Dashboard:
    def __init__(self, config):
        self.config = config
        self.logs = []
        self.tasks = []
        self.start_time = time.time()
        self.status = "Initializing..."
        self.current_agent = "system"
        self.iteration = 0

    def add_log(self, text: str):
        self.logs.append(text)
        if len(self.logs) > 30:
            self.logs.pop(0)

    def set_status(self, agent: str, status: str):
        self.current_agent = agent
        self.status = status

    def generate(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        layout["main"].split_row(
            Layout(name="chat", ratio=2),
            Layout(name="sidebar", ratio=1)
        )

        # Header
        header = Table.grid(expand=True)
        header.add_column(justify="left", ratio=1)
        header.add_column(justify="center", ratio=1)
        header.add_column(justify="right", ratio=1)
        
        logo = Text()
        logo.append(" N ", style="bold #111111 on #00f2fe")
        logo.append(" nexus ai", style="bold white")
        
        header.add_row(
            logo,
            Text(f"📂 {Path.cwd().name}", style="dim"),
            Text(f"🤖 {self.config.llm.model}", style="dim")
        )
        layout["header"].update(Panel(header, style="white on #1a1a2e"))

        # Chat Area
        chat_text = Text("\n".join(self.logs))
        layout["chat"].update(Panel(chat_text, title="[#00f2fe]Terminal Output[/]", border_style="#40c6fe"))

        # Sidebar
        sidebar = Table.grid(padding=1)
        sidebar.add_column(style="bold #a166ab")
        sidebar.add_column()
        
        elapsed = int(time.time() - self.start_time)
        sidebar.add_row("SESSION", "")
        sidebar.add_row("⏱️ Time", f"{elapsed}s")
        sidebar.add_row("🔄 Iteration", str(self.iteration))
        sidebar.add_row("", "")
        sidebar.add_row("TASKS", "")
        for t in self.tasks[-5:]:
            sidebar.add_row("✓", f"[dim]{t}[/]")
            
        layout["sidebar"].update(Panel(sidebar, title="[#ff9a9e]Workspace Info[/]", border_style="#a166ab"))

        # Footer (Spinner)
        footer = Table.grid(padding=1)
        footer.add_column()
        footer.add_row(Spinner("dots12", style="bold #A8D5BA"), f" [#A8D5BA]{self.current_agent}[/]: {self.status}")
        layout["footer"].update(Panel(footer, border_style="#00f2fe"))

        return layout
