"""UX/UI Designer Agent — creates high-fidelity designs using Huashu Design principles."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from nexus.core.agent import Agent, AgentId, AgentRole
from nexus.core.message import Message, MessageBus, MessageType

if TYPE_CHECKING:
    from nexus.core.tool import ToolRegistry
    from nexus.llm.provider import LLMProvider
    from nexus.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

# 20 design philosophies distilled from Huashu Design (alchaincyf/huashu-design)
DESIGN_PHILOSOPHIES = {
    "information_architecture": [
        "Pentagram (typographic hierarchy, Swiss grid, 60%+ whitespace)",
        "Stamen Design (cartographic data visualization, warm organic palettes)",
        "Information Architects (content-first, system fonts, zero decoration)",
        "Fathom (scientific rigor meets design elegance, quantitative precision)",
    ],
    "motion_and_interaction": [
        "Locomotive (cinematic scrolling, smooth page transitions)",
        "Active Theory (WebGL immersion, 3D environments, particle systems)",
        "Field.io (generative art, algorithm-driven organic forms)",
        "Resn (playful interaction, game-like engagement, surprise)",
    ],
    "typographic_and_structural": [
        "Experimental Jetset (Helvetica philosophy, systematic grid, primary colors)",
        "Muller-Brockmann (mathematical grid systems, objective typography)",
        "Build (British modernism, geometric precision, restrained palettes)",
        "Sagmeister & Walsh (emotional provocation, boundary-pushing experimentation)",
    ],
    "generative_and_futuristic": [
        "Zach Lieberman (code as art, real-time generative visuals)",
        "Raven Kwok (algorithmic geometry, mathematical beauty)",
        "Ash Thorp (sci-fi futurism, dark interfaces, holographic textures)",
        "Territory Studio (FUI/HUD design, cinematic data dashboards)",
    ],
    "eastern_and_editorial": [
        "Takram (design engineering, Japanese precision, invisible UX)",
        "Kenya Hara (Ma/emptiness, extreme minimalism, tactile whitespace)",
        "Irma Boom (experimental editorial, unconventional book design)",
        "Neo Shen (east-meets-west fusion, calligraphic digital art)",
    ],
}

# 5-dimension design review criteria from Huashu Design
REVIEW_DIMENSIONS = {
    "philosophy_alignment": "Does the design embody the chosen philosophy's core spirit?",
    "visual_hierarchy": "Does the user's eye flow naturally along the designer's intent?",
    "craft_quality": "Pixel-perfect alignment, consistent spacing, systematic color use?",
    "functionality": "Does every element serve the goal with zero redundancy?",
    "originality": "Fresh expression within the philosophy, not a template copy?",
}


class UxUiDesignerAgent(Agent):
    """Designs high-fidelity UIs, prototypes, and visual systems using Huashu Design principles.

    Inspired by alchaincyf/huashu-design — 20 design philosophies, 5-dimension review,
    anti-AI-slop rules, brand asset protocol, and junior designer workflow.
    """

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        llm: LLMProvider | None = None,
        memory: MemoryManager | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        super().__init__(agent_id, AgentRole.UX_UI_DESIGNER, bus, memory)
        self.llm = llm
        self.tools = tools

    @property
    def system_prompt(self) -> str:
        tool_docs = ""
        if self.tools:
            for tool in self.tools.list_tools():
                params = ", ".join(p.name for p in tool.parameters)
                tool_docs += f"- {tool.name}({params}): {tool.description}\n"

        philosophies_text = ""
        for school, styles in DESIGN_PHILOSOPHIES.items():
            philosophies_text += f"\n  {school.replace('_', ' ').title()}:\n"
            for s in styles:
                philosophies_text += f"    - {s}\n"

        review_text = ""
        for dim, desc in REVIEW_DIMENSIONS.items():
            review_text += f"  - {dim.replace('_', ' ').title()}: {desc}\n"

        return f"""You are the UX/UI Designer Agent — a designer who works with HTML, not a programmer.
Your user is your manager. You produce thoughtful, polished design work.

## Huashu Design Principles (alchaincyf/huashu-design)

### Core Philosophy (Priority Order)
1. Start from existing context — never design from blank canvas if avoidable.
   Ask for design systems, UI kits, brand assets, screenshots first.
   If nothing exists and requirements are vague, enter Design Direction Advisor mode.

2. Design Direction Advisor (Fallback for vague requirements):
   - Recommend 3 differentiated directions from 5 schools x 20 philosophies
   - Each direction: representative work, mood keywords, representative designers
   - Generate 3 visual demos in parallel for the user to choose

3. Junior Designer Workflow:
   - Show assumptions + placeholders + reasoning comments early
   - Share work-in-progress (even gray boxes) before polishing
   - Iterate: fill content → variations → tweaks → final delivery
   - Verify with Playwright before delivery

4. Anti-AI Slop Rules — NEVER produce:
   - Purple gradients as default
   - Emoji as icons
   - Rounded corners + left border accent everywhere
   - SVG-drawn human faces
   - Inter font for display text
   - Generic "AI aesthetic" visual cliches
   Instead use: text-wrap: pretty, CSS Grid, carefully chosen serif display fonts, oklch colors.

5. Brand Asset Protocol (when specific brands are involved):
   Step 1: Ask for logo, product images, UI screenshots, color values, fonts
   Step 2: Search official brand pages for assets
   Step 3: Download and extract (SVG → HTML → screenshot fallback)
   Step 4: Extract color values (grep HEX, sort by frequency, filter black/white/gray)
   Step 5: Write brand-spec.md with CSS variables

### 20 Design Philosophies Available:
{philosophies_text}

### 5-Dimension Design Review:
{review_text}
Each dimension scored 0-10. Output: radar chart + Keep/Fix/Quick Wins list.

### Deliverables You Can Produce:
- Interactive prototypes (single-file HTML, clickable, iPhone bezel)
- Presentation slides (1920x1080 HTML deck)
- Timeline animations (Stage + Sprite model, exportable to MP4/GIF)
- Design variants (side-by-side comparison with Tweaks panel)
- Infographics (magazine-grade typography, data-driven, print-ready)
- 5-dimension expert design review

## Collaboration with Frontend Developer
You design; Frontend Developer implements. Your output should include:
- Design specs (spacing, colors, typography as CSS variables)
- Component hierarchy and layout structure
- Interaction patterns and state transitions
- Responsive breakpoints and adaptation rules

Available tools:
{tool_docs}

When you need to use a tool, respond with:
{{
    "action": "use_tool",
    "tool": "tool_name",
    "params": {{...}},
    "reasoning": "why this tool is needed"
}}

When recommending design directions:
{{
    "action": "recommend_directions",
    "directions": [
        {{
            "philosophy": "philosophy name",
            "school": "school name",
            "mood": "mood keywords",
            "rationale": "why this fits"
        }}
    ]
}}

When delivering a design:
{{
    "action": "complete",
    "files": [
        {{"path": "path/to/file", "content": "file content"}}
    ],
    "design_spec": {{
        "philosophy": "chosen philosophy",
        "colors": ["#hex1", "#hex2"],
        "typography": {{"display": "font", "body": "font"}},
        "spacing_unit": "8px"
    }},
    "review": {{
        "philosophy_alignment": 0,
        "visual_hierarchy": 0,
        "craft_quality": 0,
        "functionality": 0,
        "originality": 0
    }},
    "summary": "what was designed"
}}"""

    def process(self, message: Message) -> Message | None:
        if message.type != MessageType.TASK_REQUEST:
            return None

        task = message.payload.get("task", "")
        context = message.payload.get("context", "")

        if self.memory:
            patterns = self.memory.recall(
                task, collections=["code_patterns"], n_results=3
            )
            if patterns:
                context += "\n\nRelevant design patterns:\n"
                for p in patterns:
                    context += f"- {p.content[:200]}\n"

        result = (
            self._design_with_llm(task, context) if self.llm else self._design_stub(task)
        )

        if self.memory:
            summary = result.get("summary", task[:100])
            self.memory.remember(
                f"Design: {summary}",
                category="design",
                persist=True,
                collection="code_patterns",
                metadata={"task": task[:200], "domain": "ux_ui_design"},
            )

        return message.reply(
            MessageType.TASK_RESULT,
            {"status": "needs_review", "result": result},
        )

    def _design_with_llm(self, task: str, context: str) -> dict[str, Any]:
        from nexus.llm.provider import LLMMessage

        assert self.llm is not None
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=f"Design task:\n\n{task}\n\nContext:\n{context}",
            ),
        ]

        max_iterations = 5
        for _iteration in range(max_iterations):
            response = self.llm.chat(messages)

            try:
                decision: dict[str, Any] = json.loads(response.content)
            except json.JSONDecodeError:
                return {"action": "complete", "summary": response.content, "files": []}

            if decision.get("action") == "use_tool" and self.tools:
                tool_name = decision.get("tool", "")
                tool_params = decision.get("params", {})
                tool = self.tools.get(tool_name)

                if tool:
                    tool_result = tool.execute(**tool_params)
                    messages.append(LLMMessage(role="assistant", content=response.content))
                    messages.append(
                        LLMMessage(
                            role="user",
                            content=f"Tool result:\n{json.dumps(tool_result.to_dict())}",
                        )
                    )
                    continue

            if decision.get("action") in ("complete", "recommend_directions"):
                files = decision.get("files", [])
                if self.tools and files:
                    for f in files:
                        write_tool = self.tools.get("file_write")
                        if write_tool:
                            write_tool.execute(path=f["path"], content=f["content"])
                return decision

        return {"action": "complete", "summary": "Max iterations reached", "files": []}

    def _design_stub(self, task: str) -> dict[str, Any]:
        task_lower = task.lower()

        is_vague = not any(
            kw in task_lower
            for kw in [
                "prototype", "mockup", "wireframe", "landing", "dashboard",
                "form", "login", "signup", "navigation", "sidebar",
            ]
        )

        if is_vague or any(
            kw in task_lower for kw in ["style", "direction", "recommend", "suggest"]
        ):
            return {
                "action": "recommend_directions",
                "summary": f"Design direction recommendations for: {task}",
                "directions": [
                    {
                        "philosophy": "Pentagram — Michael Bierut",
                        "school": "Information Architecture",
                        "mood": "precise, typographic, black+white+accent, 60% whitespace",
                        "rationale": "Clean hierarchy through typography and Swiss grid",
                    },
                    {
                        "philosophy": "Kenya Hara — Ma/Emptiness",
                        "school": "Eastern & Editorial",
                        "mood": "extreme minimalism, tactile whitespace, Japanese precision",
                        "rationale": "Calm, premium feel through strategic emptiness",
                    },
                    {
                        "philosophy": "Territory Studio — FUI/HUD",
                        "school": "Generative & Futuristic",
                        "mood": "cinematic data, dark interfaces, holographic textures",
                        "rationale": "Modern tech aesthetic with data-driven visuals",
                    },
                ],
                "note": "LLM provider not configured — returning stub recommendations",
            }

        return {
            "action": "complete",
            "summary": f"Design spec for: {task}",
            "files": [],
            "design_spec": {
                "philosophy": "To be determined after direction consultation",
                "colors": ["#0A0A0A", "#FAFAFA", "#3B82F6"],
                "typography": {"display": "Georgia", "body": "system-ui"},
                "spacing_unit": "8px",
            },
            "review": {
                "philosophy_alignment": 0,
                "visual_hierarchy": 0,
                "craft_quality": 0,
                "functionality": 0,
                "originality": 0,
            },
            "suggestions": [
                "Establish design direction from 20 philosophies",
                "Collect brand assets (logo, colors, product images)",
                "Create low-fidelity wireframes before hi-fi",
                "Build interactive HTML prototype with Playwright verification",
                "Run 5-dimension design review before delivery",
            ],
            "note": "LLM provider not configured — returning stub response",
        }
