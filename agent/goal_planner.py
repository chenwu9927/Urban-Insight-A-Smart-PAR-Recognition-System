from __future__ import annotations

import json
from typing import Any, Callable

from agent.tool_registry import AgentToolSpec, get_tool_spec


class AgentGoalPlanner:
    def __init__(self, *, max_steps: int = 3) -> None:
        self.max_steps = max(1, int(max_steps))

    def plan(
        self,
        *,
        question: str,
        answer: str,
        tool_events: list[dict[str, Any]],
        available_tools: list[AgentToolSpec | None],
        strategic_context: dict[str, Any] | None = None,
        planner: Callable[[str], str] | None = None,
        force: bool = False,
        max_steps: int | None = None,
    ) -> dict[str, Any]:
        allowed_specs = [spec for spec in available_tools if spec is not None and spec.action != "agent.chat"]
        step_limit = max(1, int(max_steps or self.max_steps))
        if not force and not self._looks_open_ended(question, strategic_context=strategic_context):
            return {"goal_summary": "", "steps": [], "auto_dispatch": False, "planning_mode": "suppressed"}

        if planner is not None:
            payload = self._plan_with_llm(
                question=question,
                answer=answer,
                tool_events=tool_events,
                available_tools=allowed_specs,
                strategic_context=strategic_context,
                planner=planner,
                step_limit=step_limit,
            )
            if payload["steps"]:
                return payload

        return self._heuristic_plan(
            question=question,
            tool_events=tool_events,
            available_tools=allowed_specs,
            strategic_context=strategic_context,
            step_limit=step_limit,
        )

    def _plan_with_llm(
        self,
        *,
        question: str,
        answer: str,
        tool_events: list[dict[str, Any]],
        available_tools: list[AgentToolSpec],
        strategic_context: dict[str, Any] | None,
        planner: Callable[[str], str],
        step_limit: int,
    ) -> dict[str, Any]:
        tool_lines = [f"- {spec.action}: {spec.description}" for spec in available_tools]
        strategy_lines = self._strategic_context_lines(strategic_context)
        prompt = "\n".join(
            [
                "You are planning follow-up steps for an always-on operations agent.",
                "Return strict JSON with keys: goal_summary, auto_dispatch, steps.",
                "Each step must contain: title, action, params, rationale.",
                "Use only listed actions. Prefer zero steps for purely informational requests.",
                f"Limit to {step_limit} steps.",
                "",
                "Available actions:",
                *tool_lines,
                "",
                f"Question: {question.strip()}",
                f"Answer: {answer.strip()}",
                *strategy_lines,
                "Tool events:",
                json.dumps(tool_events[:8], ensure_ascii=False),
            ]
        ).strip()
        raw = (planner(prompt) or "").strip()
        payload = self._parse_json_payload(raw)
        if not isinstance(payload, dict):
            return {"goal_summary": "", "steps": [], "auto_dispatch": False, "planning_mode": "llm_parse_failed"}

        steps = self._normalize_steps(payload.get("steps"), available_tools, step_limit=step_limit)
        auto_dispatch = bool(payload.get("auto_dispatch")) and bool(steps)
        return {
            "goal_summary": str(payload.get("goal_summary") or "").strip(),
            "steps": steps,
            "auto_dispatch": auto_dispatch,
            "planning_mode": "llm_v1" if steps else "llm_empty",
        }

    def _heuristic_plan(
        self,
        *,
        question: str,
        tool_events: list[dict[str, Any]],
        available_tools: list[AgentToolSpec],
        strategic_context: dict[str, Any] | None,
        step_limit: int,
    ) -> dict[str, Any]:
        normalized = (question or "").lower()
        breaches = [
            event
            for event in tool_events
            if isinstance(event, dict)
            and event.get("ok") is True
            and isinstance(event.get("output_payload"), dict)
            and isinstance(event["output_payload"].get("data"), dict)
            and event["output_payload"]["data"].get("breached") is True
        ]
        steps: list[dict[str, Any]] = []
        available_actions = {spec.action for spec in available_tools}
        priority_tier = str((strategic_context or {}).get("priority_tier") or "").strip().lower()
        risk_clusters = (strategic_context or {}).get("risk_clusters")

        if breaches and "memory.append_daily_note" in available_actions:
            steps.append(
                {
                    "title": "Persist breach summary",
                    "action": "memory.append_daily_note",
                    "params": {
                        "heading": "autonomous follow-up",
                        "content": breaches[0].get("result_summary") or "Patrol breach detected.",
                    },
                    "rationale": "Preserve the current incident trail for later operator review.",
                }
            )

        if priority_tier in {"elevated", "urgent"} and "agent.list_alerts" in available_actions:
            steps.append(
                {
                    "title": "Refresh open alerts for strategic risk cluster",
                    "action": "agent.list_alerts",
                    "params": {"status": "open", "limit": 10},
                    "rationale": "Strategic context indicates elevated memory-derived risk; refresh current alerts before closing the loop.",
                }
            )

        if priority_tier == "urgent" and isinstance(risk_clusters, list) and risk_clusters and "memory.append_daily_note" in available_actions:
            cluster = risk_clusters[0] if isinstance(risk_clusters[0], dict) else {}
            label = str(cluster.get("label") or "priority risk cluster").strip()
            summary = str(cluster.get("summary") or "").strip()
            steps.append(
                {
                    "title": "Persist urgent strategic risk snapshot",
                    "action": "memory.append_daily_note",
                    "params": {
                        "heading": "strategic risk snapshot",
                        "content": f"{label}: {summary}".strip(": "),
                    },
                    "rationale": "Urgent memory-derived risk should be preserved in the workspace trail for later recovery and operator review.",
                }
            )

        follow_up_keywords = (
            "continue",
            "follow up",
            "\u8ddf\u8fdb",
            "\u7ee7\u7eed",
            "\u6301\u7eed",
            "\u76d1\u63a7",
        )
        if any(keyword in normalized for keyword in follow_up_keywords) and "agent.list_alerts" in available_actions:
            steps.append(
                {
                    "title": "Refresh open alerts",
                    "action": "agent.list_alerts",
                    "params": {"status": "open", "limit": 10},
                    "rationale": "Re-check open alerts as part of the requested follow-up loop.",
                }
            )

        steps = steps[:step_limit]
        return {
            "goal_summary": "Autonomous follow-up chain" if steps else "",
            "steps": steps,
            "auto_dispatch": bool(steps),
            "planning_mode": "heuristic_v1" if steps else "heuristic_empty",
        }

    @staticmethod
    def _looks_open_ended(question: str, *, strategic_context: dict[str, Any] | None = None) -> bool:
        normalized = (question or "").lower()
        keywords = (
            "continue",
            "keep",
            "follow up",
            "monitor",
            "\u5de1\u67e5",
            "\u6301\u7eed",
            "\u7ee7\u7eed",
            "\u8ddf\u8fdb",
            "\u76ef\u7740",
            "\u76d1\u63a7",
        )
        if any(keyword in normalized for keyword in keywords):
            return True
        priority_tier = str((strategic_context or {}).get("priority_tier") or "").strip().lower()
        return priority_tier in {"elevated", "urgent"}

    @staticmethod
    def _strategic_context_lines(strategic_context: dict[str, Any] | None) -> list[str]:
        if not isinstance(strategic_context, dict):
            return []
        lines: list[str] = ["Strategic context:"]
        priority_tier = str(strategic_context.get("priority_tier") or "").strip()
        if priority_tier:
            lines.append(f"- Priority tier: {priority_tier}")
        verification_mode = str(strategic_context.get("verification_mode") or "").strip()
        if verification_mode:
            lines.append(f"- Verification mode: {verification_mode}")
        strategy_summary = str(strategic_context.get("strategy_summary") or "").strip()
        if strategy_summary:
            lines.append(f"- Strategy summary: {strategy_summary}")
        strategy_feedback_summary = str(strategic_context.get("strategy_feedback_summary") or "").strip()
        if strategy_feedback_summary:
            lines.append(f"- Recent strategy feedback: {strategy_feedback_summary}")
        feedback_status_counts = strategic_context.get("feedback_status_counts")
        if isinstance(feedback_status_counts, dict) and feedback_status_counts:
            lines.append(
                "- Feedback counts: "
                + ", ".join(f"{key}={value}" for key, value in sorted(feedback_status_counts.items()))
            )
        preferred_tools = strategic_context.get("preferred_tool_actions")
        if isinstance(preferred_tools, list) and preferred_tools:
            lines.append("- Preferred tools now:")
            for item in preferred_tools[:5]:
                text = " ".join(str(item or "").split()).strip()
                if text:
                    lines.append(f"  - {text}")
        directives = strategic_context.get("strategy_directives")
        if isinstance(directives, list) and directives:
            lines.append("- Strategy directives:")
            for item in directives[:4]:
                text = " ".join(str(item or "").split()).strip()
                if text:
                    lines.append(f"  - {text}")
        risk_clusters = strategic_context.get("risk_clusters")
        if isinstance(risk_clusters, list) and risk_clusters:
            lines.append("- Risk clusters:")
            for item in risk_clusters[:4]:
                if not isinstance(item, dict):
                    continue
                label = " ".join(str(item.get('label') or '').split()).strip()
                severity = " ".join(str(item.get('severity') or '').split()).strip()
                summary = " ".join(str(item.get('summary') or '').split()).strip()
                if label or summary:
                    lines.append(f"  - [{severity or 'medium'}] {label}: {summary}")
        return lines if len(lines) > 1 else []

    @staticmethod
    def _parse_json_payload(raw: str) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    return None
        return None

    def _normalize_steps(
        self,
        raw_steps: Any,
        available_tools: list[AgentToolSpec],
        *,
        step_limit: int,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_steps, list):
            return []
        allowed_actions = {spec.action for spec in available_tools}
        normalized: list[dict[str, Any]] = []
        for step in raw_steps[:step_limit]:
            if not isinstance(step, dict):
                continue
            action = str(step.get("action") or "").strip()
            if not action or action not in allowed_actions or get_tool_spec(action) is None:
                continue
            params = step.get("params")
            normalized.append(
                {
                    "title": str(step.get("title") or action).strip(),
                    "action": action,
                    "params": params if isinstance(params, dict) else {},
                    "rationale": str(step.get("rationale") or "").strip(),
                }
            )
        return normalized
