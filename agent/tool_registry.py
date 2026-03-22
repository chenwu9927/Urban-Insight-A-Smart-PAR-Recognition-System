from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentToolParameter:
    name: str
    value_type: str
    required: bool
    description: str
    default: Any = None


@dataclass(frozen=True)
class AgentToolSpec:
    action: str
    name: str
    category: str
    description: str
    target_service: str
    risk_level: str
    approval_mode: str
    idempotent: bool = True
    input_parameters: tuple[AgentToolParameter, ...] = field(default_factory=tuple)
    output_fields: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["input_parameters"] = [asdict(item) for item in self.input_parameters]
        return payload


AGENT_TOOL_SPECS: tuple[AgentToolSpec, ...] = (
    AgentToolSpec(
        action="stats.get",
        name="Platform Stats",
        category="insight",
        description="Read the current platform statistics summary from the insight service.",
        target_service="insight-service",
        risk_level="R0",
        approval_mode="none",
        input_parameters=(
            AgentToolParameter("interval", "integer", False, "Optional stats aggregation interval in minutes.", 60),
        ),
        output_fields=("summary", "counts", "series"),
    ),
    AgentToolSpec(
        action="insights.get_brief",
        name="Insight Brief",
        category="insight",
        description="Fetch the short textual brief for the current traffic and monitoring context.",
        target_service="insight-service",
        risk_level="R0",
        approval_mode="none",
        output_fields=("brief", "generated_at"),
    ),
    AgentToolSpec(
        action="insights.ask",
        name="Insight QA",
        category="insight",
        description="Ask the insight service a question and receive a synthesized answer.",
        target_service="insight-service",
        risk_level="R1",
        approval_mode="none",
        input_parameters=(
            AgentToolParameter("question", "string", True, "Natural-language question for the insight service."),
            AgentToolParameter("interval", "integer", False, "Time window in minutes.", 60),
            AgentToolParameter("use_llm", "boolean", False, "Whether to use the configured LLM.", True),
        ),
        output_fields=("answer", "supporting_stats"),
    ),
    AgentToolSpec(
        action="search.structured",
        name="Structured Search",
        category="search",
        description="Run a structured search against the retrieval service.",
        target_service="search-service",
        risk_level="R1",
        approval_mode="none",
        input_parameters=(
            AgentToolParameter("query", "object", True, "Structured retrieval query payload."),
        ),
        output_fields=("items", "total"),
    ),
    AgentToolSpec(
        action="search.nl",
        name="Natural Language Search",
        category="search",
        description="Use natural language to search indexed monitoring records.",
        target_service="search-service",
        risk_level="R1",
        approval_mode="none",
        input_parameters=(
            AgentToolParameter("query", "string", True, "Natural-language retrieval query."),
        ),
        output_fields=("items", "answer", "total"),
    ),
    AgentToolSpec(
        action="analysis.get_task",
        name="Analysis Task Detail",
        category="analysis",
        description="Read the state of a single analysis task from the analysis service.",
        target_service="analysis-service",
        risk_level="R0",
        approval_mode="none",
        input_parameters=(
            AgentToolParameter("task_id", "string", True, "Identifier of the analysis task."),
        ),
        output_fields=("task",),
    ),
    AgentToolSpec(
        action="agent.chat",
        name="Agent Chat",
        category="orchestration",
        description="Answer an operator question by combining operations context and insight results.",
        target_service="agent-service",
        risk_level="R1",
        approval_mode="none",
        input_parameters=(
            AgentToolParameter("question", "string", False, "Operator question. Falls back to the trigger prompt."),
        ),
        output_fields=("answer", "agent_overview", "insight_answer"),
    ),
    AgentToolSpec(
        action="patrol.analysis_backlog",
        name="Analysis Backlog Patrol",
        category="patrol",
        description="Inspect queued and running analysis tasks for stale backlog conditions.",
        target_service="analysis-service",
        risk_level="R1",
        approval_mode="none",
        input_parameters=(
            AgentToolParameter("stale_minutes", "integer", False, "How old a task must be to count as stale.", 15),
            AgentToolParameter("alert_threshold", "integer", False, "Minimum stale task count before alerting.", 5),
        ),
        output_fields=("breached", "stale_task_count", "stale_tasks"),
    ),
    AgentToolSpec(
        action="patrol.analysis_failures",
        name="Analysis Failure Patrol",
        category="patrol",
        description="Check recent failed analysis tasks and flag abnormal failure bursts.",
        target_service="analysis-service",
        risk_level="R1",
        approval_mode="none",
        input_parameters=(
            AgentToolParameter("window_minutes", "integer", False, "Observation window for recent failures.", 60),
            AgentToolParameter("alert_threshold", "integer", False, "Minimum failure count before alerting.", 3),
        ),
        output_fields=("breached", "failed_task_count", "failed_tasks"),
    ),
    AgentToolSpec(
        action="patrol.approval_timeout",
        name="Approval Timeout Patrol",
        category="patrol",
        description="Check pending approvals and surface approvals that have been waiting too long.",
        target_service="agent-control-plane",
        risk_level="R1",
        approval_mode="none",
        input_parameters=(
            AgentToolParameter("older_than_minutes", "integer", False, "Age threshold for overdue approvals.", 30),
            AgentToolParameter("alert_threshold", "integer", False, "Minimum overdue approval count before alerting.", 1),
        ),
        output_fields=("breached", "timed_out_approval_count", "timed_out_approvals"),
    ),
    AgentToolSpec(
        action="memory.get_context",
        name="Memory Context",
        category="memory",
        description="Read recent daily memory context for the current workspace.",
        target_service="agent-memory",
        risk_level="R0",
        approval_mode="none",
        input_parameters=(
            AgentToolParameter("days", "integer", False, "Number of days of daily notes to read.", 3),
        ),
        output_fields=("context", "days"),
    ),
    AgentToolSpec(
        action="memory.read_long_term",
        name="Long-Term Memory Read",
        category="memory",
        description="Read the persisted long-term memory note for the agent workspace.",
        target_service="agent-memory",
        risk_level="R0",
        approval_mode="none",
        output_fields=("content",),
    ),
    AgentToolSpec(
        action="memory.write_long_term",
        name="Long-Term Memory Write",
        category="memory",
        description="Overwrite the persisted long-term memory note.",
        target_service="agent-memory",
        risk_level="R2",
        approval_mode="recommended",
        idempotent=False,
        input_parameters=(
            AgentToolParameter("content", "string", True, "Full long-term memory content to persist."),
        ),
        output_fields=("path",),
    ),
    AgentToolSpec(
        action="memory.append_daily_note",
        name="Daily Memory Append",
        category="memory",
        description="Append a new entry to the current daily memory note.",
        target_service="agent-memory",
        risk_level="R1",
        approval_mode="none",
        idempotent=False,
        input_parameters=(
            AgentToolParameter("content", "string", True, "Note content to append."),
            AgentToolParameter("heading", "string", False, "Optional heading for the note entry."),
        ),
        output_fields=("path", "heading"),
    ),
)

AGENT_TOOL_SPECS_BY_ACTION = {spec.action: spec for spec in AGENT_TOOL_SPECS}


def list_tool_specs() -> list[AgentToolSpec]:
    return list(AGENT_TOOL_SPECS)


def list_tool_payloads() -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in AGENT_TOOL_SPECS]


def get_tool_spec(action: str) -> AgentToolSpec | None:
    return AGENT_TOOL_SPECS_BY_ACTION.get(action)
