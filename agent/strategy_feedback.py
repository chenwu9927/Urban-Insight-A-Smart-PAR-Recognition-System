from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyFeedbackResult:
    status: str
    note_body: str
    heading: str
    long_term_fact: str | None = None
    summary: str | None = None


class AgentStrategyFeedbackEngine:
    def evaluate_chat_feedback(
        self,
        *,
        output_payload: dict[str, Any],
        result_summary: str,
        run_id: str = "",
        session_id: str = "",
    ) -> StrategyFeedbackResult | None:
        strategic_context = output_payload.get("strategic_context")
        if not isinstance(strategic_context, dict) or not strategic_context:
            return None

        tool_events = output_payload.get("tool_events")
        events = tool_events if isinstance(tool_events, list) else []
        planned_steps = output_payload.get("planned_steps")
        steps = planned_steps if isinstance(planned_steps, list) else []
        directives = [str(item or "").strip() for item in strategic_context.get("strategy_directives") or [] if str(item or "").strip()]
        failed_tools = [event for event in events if isinstance(event, dict) and event.get("ok") is False]
        fallback_tools = [
            event
            for event in events
            if isinstance(event, dict)
            and isinstance(event.get("output_payload"), dict)
            and isinstance(event["output_payload"].get("fallback"), dict)
        ]

        if failed_tools:
            status = "needs_adjustment"
        elif fallback_tools or steps:
            status = "adapted"
        else:
            status = "validated"

        summary = self._build_summary(
            status=status,
            result_summary=result_summary,
            failed_count=len(failed_tools),
            fallback_count=len(fallback_tools),
            step_count=len(steps),
        )
        note_body = self._build_note_body(
            status=status,
            strategic_context=strategic_context,
            directives=directives,
            events=events,
            steps=steps,
            result_summary=result_summary,
            summary=summary,
        )
        long_term_fact = None
        if status == "validated" and directives:
            long_term_fact = f"Validated strategy: {directives[0]}"

        heading_parts = ["strategy feedback"]
        if run_id:
            heading_parts.append(f"run={run_id}")
        if session_id:
            heading_parts.append(f"session={session_id}")

        return StrategyFeedbackResult(
            status=status,
            note_body=note_body,
            heading=" | ".join(heading_parts),
            long_term_fact=long_term_fact,
            summary=summary,
        )

    @staticmethod
    def _build_summary(
        *,
        status: str,
        result_summary: str,
        failed_count: int,
        fallback_count: int,
        step_count: int,
    ) -> str:
        base = result_summary.strip() or "Agent chat turn completed."
        return (
            f"{base} | strategy_status={status}, failed_tools={failed_count}, "
            f"fallback_tools={fallback_count}, planned_steps={step_count}"
        )

    @staticmethod
    def _build_note_body(
        *,
        status: str,
        strategic_context: dict[str, Any],
        directives: list[str],
        events: list[dict[str, Any]],
        steps: list[dict[str, Any]],
        result_summary: str,
        summary: str,
    ) -> str:
        lines = [
            f"Status: {status}",
            f"Priority tier: {strategic_context.get('priority_tier') or 'normal'}",
            f"Verification mode: {strategic_context.get('verification_mode') or 'standard'}",
        ]

        strategy_summary = str(strategic_context.get("strategy_summary") or "").strip()
        if strategy_summary:
            lines.extend(["", "Strategy summary:", strategy_summary])

        if directives:
            lines.extend(["", "Strategy directives:"])
            for item in directives[:5]:
                lines.append(f"- {item}")

        risk_clusters = strategic_context.get("risk_clusters")
        if isinstance(risk_clusters, list) and risk_clusters:
            lines.extend(["", "Risk clusters:"])
            for cluster in risk_clusters[:4]:
                if not isinstance(cluster, dict):
                    continue
                label = str(cluster.get("label") or "").strip()
                severity = str(cluster.get("severity") or "").strip()
                cluster_summary = str(cluster.get("summary") or "").strip()
                lines.append(f"- [{severity or 'medium'}] {label}: {cluster_summary}".strip(": "))

        if result_summary.strip():
            lines.extend(["", "Execution summary:", result_summary.strip()])

        if events:
            success_count = sum(1 for event in events if isinstance(event, dict) and event.get("ok") is True)
            failed_count = sum(1 for event in events if isinstance(event, dict) and event.get("ok") is False)
            fallback_count = sum(
                1
                for event in events
                if isinstance(event, dict)
                and isinstance(event.get("output_payload"), dict)
                and isinstance(event["output_payload"].get("fallback"), dict)
            )
            lines.extend(
                [
                    "",
                    "Tool execution summary:",
                    f"- successful tools: {success_count}",
                    f"- failed tools: {failed_count}",
                    f"- fallback tools: {fallback_count}",
                ]
            )

        if steps:
            lines.extend(["", "Planned next steps:"])
            for step in steps[:5]:
                if not isinstance(step, dict):
                    continue
                title = str(step.get("title") or step.get("action") or "follow-up").strip()
                rationale = str(step.get("rationale") or "").strip()
                if rationale:
                    lines.append(f"- {title}: {rationale}")
                else:
                    lines.append(f"- {title}")

        lines.extend(["", "Feedback summary:", summary])
        return "\n".join(lines).strip()
