from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from agent.memory_store import AgentMemoryStore
from agent.tool_registry import AgentToolSpec


def _extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text.strip()
    preview = message.get("text_preview")
    if isinstance(preview, str):
        return preview.strip()
    return ""


class AgentContextBuilder:
    """Builds stable agent context in the same spirit as picoclaw's ContextBuilder."""

    def __init__(self, workspace_dir: str | Path, memory_store: AgentMemoryStore | None = None) -> None:
        self.workspace_dir = Path(workspace_dir).resolve()
        self.memory = memory_store or AgentMemoryStore(self.workspace_dir)

    def build_system_prompt(
        self,
        *,
        session: dict[str, Any] | None,
        summary_text: str,
        available_tools: list[AgentToolSpec],
        current_question: str,
        strategic_context: dict[str, Any] | None = None,
    ) -> str:
        parts = [
            self._identity_section(available_tools),
            self._bootstrap_section(),
            self._memory_section(),
            self._dynamic_section(
                session=session,
                summary_text=summary_text,
                current_question=current_question,
                strategic_context=strategic_context,
            ),
        ]
        return "\n\n---\n\n".join(part for part in parts if part.strip())

    def build_messages(
        self,
        *,
        session: dict[str, Any] | None,
        summary_text: str,
        history_messages: list[dict[str, Any]],
        available_tools: list[AgentToolSpec],
        current_question: str,
        strategic_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        system_prompt = self.build_system_prompt(
            session=session,
            summary_text=summary_text,
            available_tools=available_tools,
            current_question=current_question,
            strategic_context=strategic_context,
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        history = self._normalize_history(history_messages)
        messages.extend(history)

        if current_question and not self._history_ends_with_prompt(history, current_question):
            messages.append({"role": "user", "content": current_question})

        return messages

    def _identity_section(self, available_tools: list[AgentToolSpec]) -> str:
        workspace = str(self.workspace_dir)
        tool_lines = []
        for spec in available_tools:
            tool_lines.append(
                f"- `{spec.action}` ({spec.category}, {spec.target_service}): {spec.description}"
            )

        return "\n".join(
            [
                "# Urban Insight Agent",
                "",
                "You are the always-on operations agent for the Urban Insight platform.",
                "",
                "## Workspace",
                f"- Workspace: {workspace}",
                f"- Long-term memory: {self.memory.long_term_path}",
                f"- Daily notes: {self.memory.memory_dir / 'YYYYMM' / 'YYYYMMDD.md'}",
                "",
                "## Operating Rules",
                "1. When a task requires action, use the available tools. Do not pretend work was completed.",
                "2. Prefer read/inspect tools first, then summarize findings before making changes.",
                "3. Use memory carefully: daily notes for observations, long-term memory only for durable facts or explicit instructions.",
                "4. Stay grounded in tool outputs and known platform state. If evidence is missing, say so explicitly.",
                "5. Keep answers concise, concrete, and operationally useful.",
                "",
                "## Available Tools",
                *tool_lines,
            ]
        ).strip()

    def _bootstrap_section(self) -> str:
        chunks: list[str] = []
        for name in ("AGENTS.md", "SOUL.md", "USER.md", "IDENTITY.md"):
            path = self.workspace_dir / name
            if not path.exists():
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if content:
                chunks.append(f"## {name}\n\n{content}")
        return "\n\n".join(chunks)

    def _memory_section(self) -> str:
        memory_context = self.memory.get_context(days=3).strip()
        if not memory_context:
            return ""
        return "# Memory\n\n" + memory_context

    def _dynamic_section(
        self,
        *,
        session: dict[str, Any] | None,
        summary_text: str,
        current_question: str,
        strategic_context: dict[str, Any] | None,
    ) -> str:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# Current Context",
            "",
            f"- Local time: {now}",
        ]
        if session:
            lines.extend(
                [
                    f"- Session id: {session.get('id') or '--'}",
                    f"- Session title: {session.get('title') or '--'}",
                    f"- Session kind: {session.get('kind') or '--'}",
                    f"- Session source: {session.get('source') or '--'}",
                    f"- Site: {session.get('site_id') or '--'}",
                    f"- Camera: {session.get('camera_id') or '--'}",
                ]
            )
        if summary_text.strip():
            lines.extend(["", "## Conversation Summary", "", summary_text.strip()])
        strategy_section = self._strategic_context_section(strategic_context)
        if strategy_section:
            lines.extend(["", strategy_section])
        if current_question.strip():
            lines.extend(["", "## Current User Request", "", current_question.strip()])
        return "\n".join(lines).strip()

    @staticmethod
    def _strategic_context_section(strategic_context: dict[str, Any] | None) -> str:
        if not isinstance(strategic_context, dict):
            return ""

        lines = ["## Strategic Context", ""]
        priority_tier = str(strategic_context.get("priority_tier") or "").strip()
        priority_score = strategic_context.get("priority_score")
        if priority_tier:
            score_text = ""
            if isinstance(priority_score, (int, float)):
                score_text = f" (score {float(priority_score):.2f})"
            lines.append(f"- Priority tier: {priority_tier}{score_text}")
        verification_mode = str(strategic_context.get("verification_mode") or "").strip()
        if verification_mode:
            lines.append(f"- Verification mode: {verification_mode}")
        tool_loop_budget = strategic_context.get("tool_loop_max_iterations")
        if isinstance(tool_loop_budget, (int, float)):
            lines.append(f"- Tool loop budget: {int(tool_loop_budget)}")
        planner_step_budget = strategic_context.get("planner_step_budget")
        if isinstance(planner_step_budget, (int, float)):
            lines.append(f"- Planner step budget: {int(planner_step_budget)}")

        strategy_summary = str(strategic_context.get("strategy_summary") or "").strip()
        if strategy_summary:
            lines.extend(["", "### Strategy Summary", "", strategy_summary])

        strategy_feedback_summary = str(strategic_context.get("strategy_feedback_summary") or "").strip()
        if strategy_feedback_summary:
            lines.extend(["", "### Strategy Feedback", "", strategy_feedback_summary])

        feedback_status_counts = strategic_context.get("feedback_status_counts")
        if isinstance(feedback_status_counts, dict) and feedback_status_counts:
            lines.extend(["", "### Feedback Counts"])
            for key, value in sorted(feedback_status_counts.items()):
                lines.append(f"- {key}: {value}")

        preferred_tools = strategic_context.get("preferred_tool_actions")
        if isinstance(preferred_tools, list) and preferred_tools:
            lines.extend(["", "### Preferred Tools Now"])
            for action in preferred_tools[:6]:
                text = " ".join(str(action or "").split()).strip()
                if text:
                    lines.append(f"- {text}")

        directives = strategic_context.get("strategy_directives")
        if isinstance(directives, list) and directives:
            lines.extend(["", "### Strategy Directives"])
            for item in directives[:6]:
                text = " ".join(str(item or "").split()).strip()
                if text:
                    lines.append(f"- {text}")

        risk_clusters = strategic_context.get("risk_clusters")
        if isinstance(risk_clusters, list) and risk_clusters:
            lines.extend(["", "### Risk Clusters"])
            for item in risk_clusters[:5]:
                if not isinstance(item, dict):
                    continue
                label = " ".join(str(item.get("label") or "").split()).strip()
                summary = " ".join(str(item.get("summary") or "").split()).strip()
                severity = " ".join(str(item.get("severity") or "").split()).strip()
                recommended = " ".join(str(item.get("recommended_strategy") or "").split()).strip()
                if not label and not summary:
                    continue
                head = f"- [{severity or 'medium'}] {label or 'risk cluster'}"
                if recommended:
                    head += f" -> {recommended}"
                lines.append(head)
                if summary:
                    lines.append(f"  {summary}")

        if len(lines) <= 2:
            return ""
        return "\n".join(lines).strip()

    def _normalize_history(self, history_messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in history_messages:
            role = str(item.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            text = _extract_message_text(item)
            if not text:
                continue
            normalized.append({"role": role, "content": text})
        return normalized

    @staticmethod
    def _history_ends_with_prompt(history: list[dict[str, str]], prompt: str) -> bool:
        if not history:
            return False
        last = history[-1]
        return last.get("role") == "user" and (last.get("content") or "").strip() == prompt.strip()
