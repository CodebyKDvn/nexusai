"""Dynamic Crew Assembly — auto-select agent teams based on task analysis.

When a user request arrives, the CrewAssembler analyzes the task and
determines which agents (and how many) should form the crew.  This
enables task-specific team composition rather than sending everything
through a fixed set of agents.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class TaskCategory(StrEnum):
    """High-level task categories for crew selection."""

    FULL_STACK = "full_stack"
    FRONTEND = "frontend"
    BACKEND = "backend"
    BUG_FIX = "bug_fix"
    DESIGN = "design"
    RESEARCH = "research"
    TESTING = "testing"
    CODE_REVIEW = "code_review"
    PLANNING = "planning"
    GENERAL = "general"


@dataclass
class CrewTemplate:
    """A predefined team template for a task category."""

    category: TaskCategory
    required_agents: list[str]
    optional_agents: list[str] = field(default_factory=list)
    parallel_phases: bool = False
    description: str = ""


# Built-in crew templates
CREW_TEMPLATES: dict[TaskCategory, CrewTemplate] = {
    TaskCategory.FULL_STACK: CrewTemplate(
        category=TaskCategory.FULL_STACK,
        required_agents=[
            "planner", "ux_ui_designer",
            "frontend_developer", "backend_developer", "qa",
        ],
        optional_agents=["critic", "research"],
        parallel_phases=True,
        description="Full-stack application: plan, design, code (parallel FE+BE), test, review",
    ),
    TaskCategory.FRONTEND: CrewTemplate(
        category=TaskCategory.FRONTEND,
        required_agents=["planner", "ux_ui_designer", "frontend_developer", "qa"],
        optional_agents=["critic"],
        parallel_phases=False,
        description="Frontend-focused: design, implement UI, test",
    ),
    TaskCategory.BACKEND: CrewTemplate(
        category=TaskCategory.BACKEND,
        required_agents=["planner", "backend_developer", "qa"],
        optional_agents=["critic", "debugger"],
        parallel_phases=False,
        description="Backend-focused: plan, implement API/DB, test",
    ),
    TaskCategory.BUG_FIX: CrewTemplate(
        category=TaskCategory.BUG_FIX,
        required_agents=["debugger", "qa"],
        optional_agents=["research", "critic"],
        parallel_phases=False,
        description="Bug fixing: debug, fix, test",
    ),
    TaskCategory.DESIGN: CrewTemplate(
        category=TaskCategory.DESIGN,
        required_agents=["ux_ui_designer"],
        optional_agents=["frontend_developer", "research"],
        parallel_phases=False,
        description="Design task: UX/UI design, optionally prototype",
    ),
    TaskCategory.RESEARCH: CrewTemplate(
        category=TaskCategory.RESEARCH,
        required_agents=["research"],
        optional_agents=["planner"],
        parallel_phases=False,
        description="Research: gather information, analyze",
    ),
    TaskCategory.TESTING: CrewTemplate(
        category=TaskCategory.TESTING,
        required_agents=["qa"],
        optional_agents=["debugger"],
        parallel_phases=False,
        description="Testing: write and run tests",
    ),
    TaskCategory.CODE_REVIEW: CrewTemplate(
        category=TaskCategory.CODE_REVIEW,
        required_agents=["critic"],
        optional_agents=["qa"],
        parallel_phases=False,
        description="Code review: evaluate quality, suggest improvements",
    ),
    TaskCategory.PLANNING: CrewTemplate(
        category=TaskCategory.PLANNING,
        required_agents=["planner"],
        optional_agents=["research"],
        parallel_phases=False,
        description="Planning: break down task, create roadmap",
    ),
    TaskCategory.GENERAL: CrewTemplate(
        category=TaskCategory.GENERAL,
        required_agents=["planner"],
        optional_agents=["research", "critic"],
        parallel_phases=False,
        description="General task: plan and execute",
    ),
}


# Keyword patterns for task classification
_CATEGORY_PATTERNS: list[tuple[TaskCategory, list[str]]] = [
    (TaskCategory.BUG_FIX, [
        "bug", "fix", "error", "crash", "debug", "issue", "broken",
        "not working", "fails", "exception", "traceback",
    ]),
    (TaskCategory.DESIGN, [
        "ui design", "ux design", "visual design", "mockup", "wireframe",
        "prototype", "brand", "typography", "color scheme", "layout design",
    ]),
    (TaskCategory.TESTING, [
        "write test", "add test", "test coverage", "unit test",
        "integration test", "e2e test", "testing",
    ]),
    (TaskCategory.CODE_REVIEW, [
        "review", "code review", "evaluate", "critique", "audit",
    ]),
    (TaskCategory.RESEARCH, [
        "research", "find out", "investigate", "look up", "learn about",
        "documentation", "explore",
    ]),
    (TaskCategory.PLANNING, [
        "plan", "roadmap", "architecture", "break down", "design system",
    ]),
    (TaskCategory.FRONTEND, [
        "frontend", "react", "vue", "angular", "css", "html",
        "component", "ui component", "responsive", "animation",
    ]),
    (TaskCategory.BACKEND, [
        "backend", "api", "database", "server", "endpoint", "rest",
        "graphql", "auth", "migration", "microservice",
    ]),
    (TaskCategory.FULL_STACK, [
        "full stack", "fullstack", "full-stack", "web app", "application",
        "build a", "create a", "develop a",
    ]),
]


@dataclass
class CrewAssignment:
    """The result of crew assembly — which agents to use and how."""

    category: TaskCategory
    agents: list[str]
    parallel: bool = False
    template: CrewTemplate | None = None
    confidence: float = 0.0
    reasoning: str = ""


class CrewAssembler:
    """Analyzes tasks and assembles the optimal crew.

    Uses keyword analysis (rule-based) by default, but can be enhanced
    with LLM-based classification when an LLM is available.
    """

    def __init__(
        self,
        available_agents: list[str] | None = None,
        custom_templates: dict[TaskCategory, CrewTemplate] | None = None,
    ) -> None:
        self._available = set(available_agents or [])
        self._templates = {**CREW_TEMPLATES}
        if custom_templates:
            self._templates.update(custom_templates)

    def set_available_agents(self, agents: list[str]) -> None:
        self._available = set(agents)

    def analyze_task(self, task: str) -> TaskCategory:
        """Classify a task into a category using keyword matching."""
        task_lower = task.lower()

        scores: dict[TaskCategory, float] = {}

        for category, keywords in _CATEGORY_PATTERNS:
            score = 0.0
            for kw in keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', task_lower):
                    score += 1.0
            if score > 0:
                scores[category] = score

        if not scores:
            return TaskCategory.GENERAL

        # If both frontend and backend match, it's full-stack
        if (
            TaskCategory.FRONTEND in scores
            and TaskCategory.BACKEND in scores
        ):
            return TaskCategory.FULL_STACK

        return max(scores, key=lambda k: scores[k])

    def assemble(self, task: str) -> CrewAssignment:
        """Analyze the task and assemble the optimal crew."""
        category = self.analyze_task(task)
        template = self._templates.get(category, self._templates[TaskCategory.GENERAL])

        # Filter to available agents
        agents: list[str] = []
        for agent_id in template.required_agents:
            if not self._available or agent_id in self._available:
                agents.append(agent_id)

        for agent_id in template.optional_agents:
            if not self._available or agent_id in self._available:
                agents.append(agent_id)

        # Always include orchestrator (supervisor)
        if "orchestrator" not in agents:
            agents.insert(0, "orchestrator")

        confidence = len([a for a in template.required_agents if a in agents])
        max_conf = len(template.required_agents) or 1

        return CrewAssignment(
            category=category,
            agents=agents,
            parallel=template.parallel_phases,
            template=template,
            confidence=confidence / max_conf,
            reasoning=template.description,
        )

    def get_template(self, category: TaskCategory) -> CrewTemplate:
        return self._templates.get(category, self._templates[TaskCategory.GENERAL])

    def add_template(self, template: CrewTemplate) -> None:
        self._templates[template.category] = template
