from __future__ import annotations

import datetime
from typing import Any

import httpx

from agent.executor.config import ExecutorSettings
from agent.memory_store import AgentMemoryStore
from agent.tool_registry import get_tool_spec, list_tool_specs


def extract_prompt(trigger_message: dict[str, Any] | None) -> str:
    if not trigger_message:
        return ""
    content = trigger_message.get("content")
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts)
    preview = trigger_message.get("text_preview")
    if isinstance(preview, str):
        return preview.strip()
    return ""


class ApiOnlyExecutionService:
    def __init__(self, settings: ExecutorSettings | None = None) -> None:
        self.settings = settings or ExecutorSettings()
        self.client = httpx.Client(timeout=self.settings.timeout_seconds)
        self.memory = AgentMemoryStore(self.settings.workspace_dir)

    def close(self) -> None:
        self.client.close()

    def execute(self, claim: dict[str, Any]) -> tuple[dict[str, Any], str]:
        run = claim.get("run") or {}
        trigger_message = claim.get("trigger_message") or {}
        action = ((run.get("input_payload") or {}).get("action") or "").strip()
        prompt = extract_prompt(trigger_message)
        params = (run.get("input_payload") or {}).get("params") or {}
        run_id = str(run.get("id") or "").strip()
        session_id = str(run.get("session_id") or "").strip()

        if not action:
            output_payload = {
                "executor_mode": "api_only",
                "action": None,
                "status": "accepted",
                "trigger_prompt": prompt,
                "message": "Run was accepted by executor. No explicit action was provided yet.",
            }
            return output_payload, "Accepted run without explicit action"

        tool_spec = get_tool_spec(action)
        if tool_spec is None:
            supported_actions = ", ".join(spec.action for spec in list_tool_specs())
            raise ValueError(f"Unsupported action: {action}. Supported actions: {supported_actions}")

        if action == "stats.get":
            data = self._get(f"{self.settings.insight_service_url}/stats", params=params)
            return self._wrap(action, prompt, params, data), "Fetched stats successfully"

        if action == "insights.get_brief":
            data = self._get(f"{self.settings.insight_service_url}/insights/brief", params=params)
            return self._wrap(action, prompt, params, data), "Fetched insights brief successfully"

        if action == "insights.ask":
            data = self._post(f"{self.settings.insight_service_url}/insights/ask", json=params)
            return self._wrap(action, prompt, params, data), "Answered insight question successfully"

        if action == "search.structured":
            data = self._post(f"{self.settings.search_service_url}/search", json=params)
            return self._wrap(action, prompt, params, data), "Structured search completed"

        if action == "search.nl":
            data = self._post(f"{self.settings.search_service_url}/search/nl", json=params)
            return self._wrap(action, prompt, params, data), "Natural language search completed"

        if action == "analysis.get_task":
            task_id = params.get("task_id")
            if not task_id:
                raise ValueError("analysis.get_task requires params.task_id")
            data = self._get(f"{self.settings.analysis_service_url}/analyze/tasks/{task_id}")
            return self._wrap(action, prompt, params, data), "Fetched analysis task successfully"

        if action == "agent.chat":
            data, result_summary = self._run_agent_chat(prompt=prompt, params=params)
            return self._wrap(action, prompt, params, data), result_summary

        if action == "patrol.analysis_backlog":
            data, result_summary = self._run_analysis_backlog_patrol(params)
            return self._wrap(action, prompt, params, data), result_summary

        if action == "patrol.analysis_failures":
            data, result_summary = self._run_analysis_failure_patrol(params)
            return self._wrap(action, prompt, params, data), result_summary

        if action == "patrol.approval_timeout":
            data, result_summary = self._run_approval_timeout_patrol(params)
            return self._wrap(action, prompt, params, data), result_summary

        if action == "memory.get_context":
            days = int(params.get("days") or 3)
            data = {
                "workspace_dir": str(self.memory.workspace_dir),
                "context": self.memory.get_context(days=days),
                "days": max(1, min(30, days)),
            }
            return self._wrap(action, prompt, params, data), "Fetched memory context successfully"

        if action == "memory.read_long_term":
            data = {
                "workspace_dir": str(self.memory.workspace_dir),
                "content": self.memory.read_long_term(),
            }
            return self._wrap(action, prompt, params, data), "Read long-term memory successfully"

        if action == "memory.write_long_term":
            content = str(params.get("content") or "").strip()
            if not content:
                raise ValueError("memory.write_long_term requires params.content")
            self.memory.write_long_term(content)
            data = {
                "workspace_dir": str(self.memory.workspace_dir),
                "path": str(self.memory.long_term_path),
            }
            return self._wrap(action, prompt, params, data), "Updated long-term memory successfully"

        if action == "memory.append_daily_note":
            content = str(params.get("content") or "").strip()
            if not content:
                raise ValueError("memory.append_daily_note requires params.content")
            heading = str(params.get("heading") or "").strip()
            if not heading:
                parts = [part for part in [f"run={run_id}" if run_id else "", f"session={session_id}" if session_id else ""] if part]
                heading = " | ".join(parts) or "agent note"
            path = self.memory.append_daily_note(content, heading=heading)
            data = {
                "workspace_dir": str(self.memory.workspace_dir),
                "path": str(path),
                "heading": heading,
            }
            return self._wrap(action, prompt, params, data), "Appended daily memory note successfully"

        raise ValueError(f"Action is registered but not implemented by executor: {action}")

    def _run_agent_chat(self, *, prompt: str, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
        question = str(params.get("question") or prompt or "").strip()
        if not question:
            raise ValueError("agent.chat requires a prompt or params.question")

        normalized = question.lower()
        ops_keywords = [
            "agent",
            "run",
            "queue",
            "approval",
            "patrol",
            "session",
            "status",
            "current",
            "doing",
            "running",
            "当前",
            "状态",
            "审批",
            "巡检",
            "队列",
            "正在",
            "运行",
        ]
        insight_keywords = [
            "traffic",
            "stats",
            "insight",
            "report",
            "pedestrian",
            "analysis",
            "客流",
            "统计",
            "洞察",
            "报告",
            "行人",
            "分析",
        ]

        include_ops = any(keyword in normalized for keyword in ops_keywords)
        include_insight = any(keyword in normalized for keyword in insight_keywords) or not include_ops

        sections: list[str] = []
        output: dict[str, Any] = {"question": question}

        if include_ops:
            overview = self._get(f"{self.settings.control_plane_url}/agent/overview")
            output["agent_overview"] = overview
            sections.append(self._summarize_agent_overview(overview))

        if include_insight:
            insight_payload = self._post(
                f"{self.settings.insight_service_url}/insights/ask",
                json={
                    "question": question,
                    "interval": 60,
                    "use_llm": 1,
                    "cache": 1,
                },
            )
            output["insight_answer"] = insight_payload
            answer = str(insight_payload.get("answer") or "").strip()
            if answer:
                sections.append(answer)

        answer_text = "\n\n".join(section for section in sections if section).strip()
        if not answer_text:
            answer_text = "Agent accepted the request but could not produce a detailed answer."
        output["answer"] = answer_text
        return output, "Answered agent chat request"

    def _run_analysis_backlog_patrol(self, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
        limit = self._int_param(params, "limit", 200, minimum=1, maximum=500)
        stale_minutes = self._int_param(params, "stale_minutes", 15, minimum=1, maximum=24 * 60)
        alert_threshold = self._int_param(params, "alert_threshold", 5, minimum=1, maximum=10000)
        tasks = self._get(
            f"{self.settings.analysis_service_url}/analyze/tasks",
            params={"statuses": "queued,running", "limit": limit},
        )
        now = self._utcnow()
        stale_tasks = []
        for task in tasks:
            reference_time = self._parse_iso(task.get("started_at")) or self._parse_iso(task.get("created_at"))
            if reference_time is None:
                continue
            age_minutes = int((now - reference_time).total_seconds() // 60)
            if age_minutes >= stale_minutes:
                item = dict(task)
                item["age_minutes"] = age_minutes
                stale_tasks.append(item)

        breached = len(stale_tasks) >= alert_threshold
        data = {
            "patrol_type": "analysis_backlog",
            "breached": breached,
            "active_task_count": len(tasks),
            "stale_task_count": len(stale_tasks),
            "stale_minutes": stale_minutes,
            "alert_threshold": alert_threshold,
            "stale_tasks": stale_tasks[:20],
        }
        if breached:
            summary = (
                f"Analysis backlog alert: {len(stale_tasks)} stale tasks exceed {stale_minutes} minutes "
                f"(threshold {alert_threshold})"
            )
            self.memory.append_daily_note(summary, heading="analysis backlog patrol")
        else:
            summary = (
                f"Analysis backlog healthy: {len(stale_tasks)} stale tasks over {stale_minutes} minutes "
                f"(threshold {alert_threshold})"
            )
        return data, summary

    def _run_analysis_failure_patrol(self, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
        limit = self._int_param(params, "limit", 200, minimum=1, maximum=500)
        window_minutes = self._int_param(params, "window_minutes", 60, minimum=1, maximum=7 * 24 * 60)
        alert_threshold = self._int_param(params, "alert_threshold", 3, minimum=1, maximum=10000)
        tasks = self._get(
            f"{self.settings.analysis_service_url}/analyze/tasks",
            params={"status": "failed", "limit": limit},
        )
        now = self._utcnow()
        failed_tasks = []
        for task in tasks:
            reference_time = self._parse_iso(task.get("finished_at")) or self._parse_iso(task.get("created_at"))
            if reference_time is None:
                continue
            age_minutes = int((now - reference_time).total_seconds() // 60)
            if age_minutes <= window_minutes:
                item = dict(task)
                item["age_minutes"] = age_minutes
                failed_tasks.append(item)

        breached = len(failed_tasks) >= alert_threshold
        data = {
            "patrol_type": "analysis_failures",
            "breached": breached,
            "window_minutes": window_minutes,
            "failed_task_count": len(failed_tasks),
            "alert_threshold": alert_threshold,
            "failed_tasks": failed_tasks[:20],
        }
        if breached:
            summary = (
                f"Analysis failure alert: {len(failed_tasks)} failed tasks in the last {window_minutes} minutes "
                f"(threshold {alert_threshold})"
            )
            self.memory.append_daily_note(summary, heading="analysis failure patrol")
        else:
            summary = (
                f"Analysis failures healthy: {len(failed_tasks)} failed tasks in the last {window_minutes} minutes "
                f"(threshold {alert_threshold})"
            )
        return data, summary

    def _run_approval_timeout_patrol(self, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
        limit = self._int_param(params, "limit", 200, minimum=1, maximum=500)
        older_than_minutes = self._int_param(params, "older_than_minutes", 30, minimum=1, maximum=7 * 24 * 60)
        alert_threshold = self._int_param(params, "alert_threshold", 1, minimum=1, maximum=10000)
        approvals = self._get(
            f"{self.settings.control_plane_url}/agent/approvals",
            params={"status": "pending", "limit": limit},
        )
        now = self._utcnow()
        timed_out = []
        for approval in approvals:
            created_at = self._parse_iso(approval.get("created_at"))
            if created_at is None:
                continue
            age_minutes = int((now - created_at).total_seconds() // 60)
            if age_minutes >= older_than_minutes:
                item = dict(approval)
                item["age_minutes"] = age_minutes
                timed_out.append(item)

        breached = len(timed_out) >= alert_threshold
        data = {
            "patrol_type": "approval_timeout",
            "breached": breached,
            "older_than_minutes": older_than_minutes,
            "timed_out_approval_count": len(timed_out),
            "alert_threshold": alert_threshold,
            "timed_out_approvals": timed_out[:20],
        }
        if breached:
            summary = (
                f"Approval timeout alert: {len(timed_out)} pending approvals older than {older_than_minutes} minutes "
                f"(threshold {alert_threshold})"
            )
            self.memory.append_daily_note(summary, heading="approval timeout patrol")
        else:
            summary = (
                f"Approval queue healthy: {len(timed_out)} pending approvals older than {older_than_minutes} minutes "
                f"(threshold {alert_threshold})"
            )
        return data, summary

    @staticmethod
    def _summarize_agent_overview(overview: dict[str, Any]) -> str:
        counts = overview.get("counts") or {}
        active_runs = overview.get("active_runs") or []
        approvals = overview.get("pending_approvals") or []
        sessions = overview.get("recent_sessions") or []

        lines = [
            "Agent operations overview:",
            (
                f"- Active runs: {counts.get('active_runs', 0)}, queued: {counts.get('queued_runs', 0)}, "
                f"pending approvals: {counts.get('pending_approvals', 0)}, enabled patrol plans: {counts.get('enabled_scheduled_tasks', 0)}"
            ),
            (
                f"- Completed in last 24h: {counts.get('completed_last_24h', 0)}, "
                f"failed in last 24h: {counts.get('failed_last_24h', 0)}"
            ),
        ]

        if active_runs:
            lines.append("- Currently processing:")
            for run in active_runs[:3]:
                action = ((run.get("input_payload") or {}).get("action") or run.get("schedule_mode") or "run").strip()
                detail = str(run.get("trigger_text") or run.get("result_summary") or run.get("session_title") or "").strip()
                lines.append(
                    f"  - {run.get('status')} {action}, progress {run.get('progress', 0)}%, detail: {detail or 'No summary'}"
                )

        if approvals:
            lines.append("- Pending approvals:")
            for approval in approvals[:3]:
                lines.append(
                    f"  - {approval.get('tool_name')}, risk {approval.get('risk_level')}, "
                    f"session {approval.get('session_title') or approval.get('session_id')}"
                )

        if sessions:
            lines.append("- Recent sessions:")
            for session in sessions[:3]:
                lines.append(
                    f"  - {session.get('title') or session.get('id')}, source {session.get('source')}, "
                    f"last updated {session.get('updated_at') or '--'}"
                )

        return "\n".join(lines)

    def _get(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _post(self, url: str, *, json: dict[str, Any] | None = None) -> Any:
        response = self.client.post(url, json=json)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _wrap(action: str, prompt: str, params: dict[str, Any], data: Any) -> dict[str, Any]:
        payload = {
            "executor_mode": "api_only",
            "action": action,
            "trigger_prompt": prompt,
            "params": params,
            "data": data,
        }
        tool = get_tool_spec(action)
        if tool is not None:
            payload["tool"] = {
                "action": tool.action,
                "name": tool.name,
                "category": tool.category,
                "target_service": tool.target_service,
                "risk_level": tool.risk_level,
                "approval_mode": tool.approval_mode,
            }
        return payload

    @staticmethod
    def _int_param(
        params: dict[str, Any],
        key: str,
        default: int,
        *,
        minimum: int,
        maximum: int,
    ) -> int:
        raw = params.get(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _utcnow():
        return datetime.datetime.utcnow()

    @staticmethod
    def _parse_iso(value: Any):
        if not value or not isinstance(value, str):
            return None
        try:
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            return None
