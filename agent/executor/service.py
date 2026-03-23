from __future__ import annotations

import datetime
import time
from typing import Any

import httpx

from agent.context_builder import AgentContextBuilder
from agent.executor.config import ExecutorSettings
from agent.goal_planner import AgentGoalPlanner
from agent.memory_store import AgentMemoryStore
from agent.memory_writeback import AgentMemoryWritebackPolicy
from agent.session_summary import AgentSessionSummaryManager
from agent.tool_loop import OpenAICompatibleToolLoopClient, ToolLoopRunner
from agent.tool_registry import AgentToolSpec, get_tool_spec, list_tool_specs


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


class ApiOnlyExecutionService:
    def __init__(self, settings: ExecutorSettings | None = None) -> None:
        self.settings = settings or ExecutorSettings()
        self.client = httpx.Client(timeout=self.settings.timeout_seconds)
        self.memory = AgentMemoryStore(self.settings.workspace_dir)
        self.context_builder = AgentContextBuilder(self.settings.workspace_dir, memory_store=self.memory)
        self.summary_manager = AgentSessionSummaryManager()
        self.memory_writeback = AgentMemoryWritebackPolicy(self.memory)
        self.goal_planner = AgentGoalPlanner()
        self.tool_loop = ToolLoopRunner(
            llm_client=OpenAICompatibleToolLoopClient(timeout_seconds=self.settings.timeout_seconds),
            max_iterations=6,
        )

    def close(self) -> None:
        self.client.close()

    def execute(self, claim: dict[str, Any]) -> tuple[dict[str, Any], str]:
        run = claim.get("run") or {}
        session = claim.get("session") or {}
        trigger_message = claim.get("trigger_message") or {}
        action = ((run.get("input_payload") or {}).get("action") or "").strip()
        prompt = extract_prompt(trigger_message)
        params = (run.get("input_payload") or {}).get("params") or {}
        run_id = str(run.get("id") or "").strip()
        session_id = str(run.get("session_id") or "").strip()
        strategic_context = self._derive_tool_policy(
            question=str(params.get("question") or prompt or action).strip(),
            strategic_context=self._resolve_strategic_context(
                session=session if isinstance(session, dict) else {},
                run=run if isinstance(run, dict) else {},
                state_patch=session.get("state_patch") if isinstance(session, dict) else None,
            ),
        )

        if not action:
            output_payload = {
                "executor_mode": "api_only",
                "action": None,
                "status": "accepted",
                "trigger_prompt": prompt,
                "message": "Run was accepted by executor. No explicit action was provided yet.",
            }
            return output_payload, "Accepted run without explicit action"

        output_payload, result_summary = self._execute_action_with_retry(
            action,
            prompt=prompt,
            params=params,
            run_id=run_id,
            session_id=session_id,
            claim=claim,
            strategic_context=strategic_context,
        )
        writeback = self.memory_writeback.apply(
            action=action,
            params=params,
            output_payload=output_payload.get("data") if action != "agent.chat" else output_payload.get("data") or {},
            result_summary=result_summary,
            session_id=session_id,
            run_id=run_id,
            long_term_extractor=self._llm_extract_long_term_fact if self.tool_loop.llm_client.is_configured() else None,
        )
        if any(writeback.values()):
            output_payload["memory_writeback"] = writeback
        return output_payload, result_summary

    def _execute_action_with_retry(
        self,
        action: str,
        *,
        prompt: str,
        params: dict[str, Any],
        run_id: str = "",
        session_id: str = "",
        claim: dict[str, Any] | None = None,
        strategic_context: dict[str, Any] | None = None,
        allow_fallback: bool = True,
    ) -> tuple[dict[str, Any], str]:
        tool_spec = get_tool_spec(action)
        max_attempts = self._tool_retry_attempts(tool_spec, strategic_context)
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                return self._execute_action(
                    action,
                    prompt=prompt,
                    params=params,
                    run_id=run_id,
                    session_id=session_id,
                    claim=claim,
                    strategic_context=strategic_context,
                )
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts or not self._is_transient_exception(exc):
                    break
                time.sleep(min(1.0, 0.35 * attempt))

        if allow_fallback:
            fallback_result = self._try_fallback_actions(
                action,
                prompt=prompt,
                params=params,
                run_id=run_id,
                session_id=session_id,
                claim=claim,
                strategic_context=strategic_context,
                primary_error=last_error,
            )
            if fallback_result is not None:
                return fallback_result
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Failed to execute action: {action}")

    def _execute_action(
        self,
        action: str,
        *,
        prompt: str,
        params: dict[str, Any],
        run_id: str = "",
        session_id: str = "",
        claim: dict[str, Any] | None = None,
        strategic_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str]:
        tool_spec = get_tool_spec(action)
        if tool_spec is None:
            supported_actions = ", ".join(spec.action for spec in list_tool_specs())
            raise ValueError(f"Unsupported action: {action}. Supported actions: {supported_actions}")

        if action == "agent.get_overview":
            data = self._get(f"{self.settings.control_plane_url}/agent/overview")
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), "Fetched agent overview successfully"

        if action == "agent.get_runtime_status":
            data = self._get(f"{self.settings.control_plane_url}/agent/runtime-status")
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), "Fetched agent runtime status successfully"

        if action == "agent.list_alerts":
            data = self._get(
                f"{self.settings.control_plane_url}/agent/alerts",
                params={
                    "status": params.get("status", "open"),
                    "severity": params.get("severity"),
                    "limit": self._int_param(params, "limit", 10, minimum=1, maximum=50),
                },
            )
            return self._wrap(action, prompt, params, {"alerts": data}, strategic_context=strategic_context), "Fetched agent alerts successfully"

        if action == "agent.list_goals":
            data = self._get(
                f"{self.settings.control_plane_url}/agent/goals",
                params={
                    "status": params.get("status"),
                    "limit": self._int_param(params, "limit", 10, minimum=1, maximum=50),
                },
            )
            return self._wrap(action, prompt, params, {"goals": data}, strategic_context=strategic_context), "Fetched agent goals successfully"

        if action == "agent.get_goal":
            goal_id = str(params.get("goal_id") or params.get("id") or "").strip()
            if not goal_id:
                raise ValueError("agent.get_goal requires params.goal_id")
            data = self._get(f"{self.settings.control_plane_url}/agent/goals/{goal_id}")
            return self._wrap(action, prompt, params, {"goal": data}, strategic_context=strategic_context), "Fetched agent goal successfully"

        if action == "stats.get":
            normalized_params = {"interval": self._int_param(params, "interval", 60, minimum=1, maximum=24 * 60)}
            data = self._get(f"{self.settings.insight_service_url}/stats", params=normalized_params)
            return self._wrap(action, prompt, normalized_params, data, strategic_context=strategic_context), "Fetched stats successfully"

        if action == "insights.get_brief":
            normalized_params = {"interval": self._int_param(params, "interval", 60, minimum=1, maximum=24 * 60)}
            data = self._get(f"{self.settings.insight_service_url}/insights/brief", params=normalized_params)
            return self._wrap(action, prompt, normalized_params, data, strategic_context=strategic_context), "Fetched insights brief successfully"

        if action == "insights.ask":
            normalized_params = {
                "question": str(params.get("question") or prompt or "").strip(),
                "interval": self._int_param(params, "interval", 60, minimum=1, maximum=24 * 60),
                "use_llm": 1 if params.get("use_llm", True) not in {False, 0, "0"} else 0,
                "cache": 1,
            }
            if not normalized_params["question"]:
                raise ValueError("insights.ask requires params.question or a trigger prompt")
            data = self._post(f"{self.settings.insight_service_url}/insights/ask", json=normalized_params)
            return self._wrap(action, prompt, normalized_params, data, strategic_context=strategic_context), "Answered insight question successfully"

        if action == "search.structured":
            normalized_params = params.get("query") if isinstance(params.get("query"), dict) else params
            data = self._post(f"{self.settings.search_service_url}/search", json=normalized_params)
            return self._wrap(action, prompt, normalized_params, data, strategic_context=strategic_context), "Structured search completed"

        if action == "search.nl":
            query = str(params.get("query") or params.get("question") or prompt or "").strip()
            if not query:
                raise ValueError("search.nl requires params.query or a trigger prompt")
            normalized_params = {
                "query": query,
                "use_llm": 1 if params.get("use_llm", True) not in {False, 0, "0"} else 0,
                "cache": 1,
                "dedup_person": 1,
                "max_results": self._int_param(params, "max_results", 100, minimum=1, maximum=500),
            }
            data = self._post(f"{self.settings.search_service_url}/search/nl", json=normalized_params)
            return self._wrap(action, prompt, normalized_params, data, strategic_context=strategic_context), "Natural language search completed"

        if action == "analysis.get_task":
            task_id = params.get("task_id")
            if not task_id:
                raise ValueError("analysis.get_task requires params.task_id")
            data = self._get(f"{self.settings.analysis_service_url}/analyze/tasks/{task_id}")
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), "Fetched analysis task successfully"

        if action == "agent.chat":
            data, result_summary = self._run_agent_chat(prompt=prompt, params=params, claim=claim or {})
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), result_summary

        if action == "patrol.analysis_backlog":
            data, result_summary = self._run_analysis_backlog_patrol(params)
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), result_summary

        if action == "patrol.analysis_failures":
            data, result_summary = self._run_analysis_failure_patrol(params)
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), result_summary

        if action == "patrol.approval_timeout":
            data, result_summary = self._run_approval_timeout_patrol(params)
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), result_summary

        if action == "memory.get_context":
            days = self._int_param(params, "days", 3, minimum=1, maximum=30)
            data = {
                "workspace_dir": str(self.memory.workspace_dir),
                "context": self.memory.get_context(days=days),
                "days": days,
            }
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), "Fetched memory context successfully"

        if action == "memory.read_long_term":
            data = {
                "workspace_dir": str(self.memory.workspace_dir),
                "content": self.memory.read_long_term(),
            }
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), "Read long-term memory successfully"

        if action == "memory.write_long_term":
            content = str(params.get("content") or "").strip()
            if not content:
                raise ValueError("memory.write_long_term requires params.content")
            self.memory.write_long_term(content)
            data = {
                "workspace_dir": str(self.memory.workspace_dir),
                "path": str(self.memory.long_term_path),
            }
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), "Updated long-term memory successfully"

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
            return self._wrap(action, prompt, params, data, strategic_context=strategic_context), "Appended daily memory note successfully"

        raise ValueError(f"Action is registered but not implemented by executor: {action}")

    def _run_agent_chat(
        self,
        *,
        prompt: str,
        params: dict[str, Any],
        claim: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        question = str(params.get("question") or prompt or "").strip()
        if not question:
            raise ValueError("agent.chat requires a prompt or params.question")

        run = claim.get("run") or {}
        session = claim.get("session") or {}
        session_id = str(run.get("session_id") or session.get("id") or "").strip()
        run_id = str(run.get("id") or "").strip()

        history_messages = self._get_session_messages(session_id, limit=40) if session_id else []
        if session_id and not session:
            session = self._get_session(session_id)
        state_patch = session.get("state_patch") if isinstance(session, dict) else None
        summary_text = self.summary_manager.get_summary_text(state_patch)
        strategic_context = self._resolve_strategic_context(
            session=session if isinstance(session, dict) else {},
            run=run if isinstance(run, dict) else {},
            state_patch=state_patch,
        )

        projected_history = list(history_messages)
        if question and not self._messages_end_with_prompt(projected_history, question):
            projected_history.append({"role": "user", "content": {"text": question}, "text_preview": question})
        strategic_context = self._derive_tool_policy(question=question, strategic_context=strategic_context)

        available_tools = self._chat_tool_specs(question=question, strategic_context=strategic_context)
        conversation_history = self.summary_manager.history_for_prompt(projected_history)
        messages = self.context_builder.build_messages(
            session=session,
            summary_text=summary_text,
            history_messages=conversation_history,
            available_tools=available_tools,
            current_question=question,
            strategic_context=strategic_context,
        )
        system_prompt = str(messages[0].get("content") or "")
        conversation_messages = messages[1:]

        if not self.tool_loop.llm_client.is_configured():
            fallback_output, fallback_summary = self._run_agent_chat_fallback(
                question=question,
                session_id=session_id,
                strategic_context=strategic_context,
            )
            updated_summary = self._refresh_session_summary(
                session_id=session_id,
                state_patch=state_patch,
                projected_messages=projected_history
                + [{"role": "assistant", "content": {"text": fallback_summary}, "text_preview": fallback_summary}],
            )
            fallback_output["session_summary"] = updated_summary or summary_text
            return fallback_output, fallback_summary

        try:
            result = self.tool_loop.run(
                system_prompt=system_prompt,
                conversation_messages=conversation_messages,
                available_tools=available_tools,
                execute_tool=lambda action, arguments: self._execute_action_with_retry(
                    action,
                    prompt=question,
                    params=arguments,
                    run_id=run_id,
                    session_id=session_id,
                    claim=claim,
                    strategic_context=strategic_context,
                ),
                max_iterations=self._tool_loop_iteration_budget(strategic_context),
            )
            answer_text = result.answer.strip()
            if not answer_text:
                answer_text = "Agent completed the turn but did not return a textual answer."
            updated_summary = self._refresh_session_summary(
                session_id=session_id,
                state_patch=state_patch,
                projected_messages=projected_history
                + [{"role": "assistant", "content": {"text": answer_text}, "text_preview": answer_text}],
            )
            planner = self._llm_plan_follow_up_steps if self.tool_loop.llm_client.is_configured() else None
            plan = self.goal_planner.plan(
                question=question,
                answer=answer_text,
                tool_events=result.tool_events,
                available_tools=available_tools,
                strategic_context=strategic_context,
                planner=planner,
                force=params.get("auto_plan") is True,
                max_steps=self._planner_step_budget(strategic_context),
            )
            output = {
                "question": question,
                "answer": answer_text,
                "iterations": result.iterations,
                "tool_events": result.tool_events,
                "session_summary": updated_summary or summary_text,
                "llm_used": True,
                "goal_summary": plan.get("goal_summary") or "",
                "planned_steps": plan.get("steps") or [],
                "planning_mode": plan.get("planning_mode") or "unknown",
                "auto_dispatch_followups": bool(plan.get("auto_dispatch")),
                "strategic_context": strategic_context,
            }
            return output, answer_text
        except Exception:
            fallback_output, fallback_summary = self._run_agent_chat_fallback(
                question=question,
                session_id=session_id,
                strategic_context=strategic_context,
            )
            updated_summary = self._refresh_session_summary(
                session_id=session_id,
                state_patch=state_patch,
                projected_messages=projected_history
                + [{"role": "assistant", "content": {"text": fallback_summary}, "text_preview": fallback_summary}],
            )
            fallback_output["session_summary"] = updated_summary or summary_text
            return fallback_output, fallback_summary

    def _run_agent_chat_fallback(
        self,
        *,
        question: str,
        session_id: str,
        strategic_context: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], str]:
        sections: list[str] = []
        tool_events: list[dict[str, Any]] = []
        output: dict[str, Any] = {
            "question": question,
            "llm_used": False,
            "tool_events": tool_events,
            "strategic_context": strategic_context or {},
        }

        strategic_summary = self._summarize_strategic_context(strategic_context)
        if strategic_summary:
            sections.append(strategic_summary)

        overview, overview_summary = self._execute_action_with_retry(
            "agent.get_overview",
            prompt=question,
            params={},
            session_id=session_id,
            strategic_context=strategic_context,
        )
        output["agent_overview"] = overview.get("data")
        sections.append(self._summarize_agent_overview(overview.get("data") or {}))
        tool_events.append({"action": "agent.get_overview", "ok": True, "result_summary": overview_summary})

        runtime, runtime_summary = self._execute_action_with_retry(
            "agent.get_runtime_status",
            prompt=question,
            params={},
            session_id=session_id,
            strategic_context=strategic_context,
        )
        output["runtime_status"] = runtime.get("data")
        sections.append(self._summarize_runtime_status(runtime.get("data") or {}))
        tool_events.append({"action": "agent.get_runtime_status", "ok": True, "result_summary": runtime_summary})

        alerts, alerts_summary = self._execute_action_with_retry(
            "agent.list_alerts",
            prompt=question,
            params={"status": "open", "limit": 10},
            session_id=session_id,
            strategic_context=strategic_context,
        )
        output["alerts"] = alerts.get("data")
        sections.append(self._summarize_alerts((alerts.get("data") or {}).get("alerts") or []))
        tool_events.append({"action": "agent.list_alerts", "ok": True, "result_summary": alerts_summary})

        normalized = question.lower()
        if any(keyword in normalized for keyword in ("traffic", "stats", "insight", "analysis", "report")):
            try:
                insight, insight_summary = self._execute_action_with_retry(
                    "insights.ask",
                    prompt=question,
                    params={"question": question, "interval": 60, "use_llm": 1},
                    session_id=session_id,
                    strategic_context=strategic_context,
                )
                output["insight_answer"] = insight.get("data")
                answer = str((insight.get("data") or {}).get("answer") or "").strip()
                if answer:
                    sections.append(answer)
                tool_events.append({"action": "insights.ask", "ok": True, "result_summary": insight_summary})
            except Exception:
                tool_events.append({"action": "insights.ask", "ok": False, "error": "fallback insight request failed"})

        plan = self.goal_planner.plan(
            question=question,
            answer="\n\n".join(section for section in sections if section).strip(),
            tool_events=tool_events,
            available_tools=self._chat_tool_specs(question=question, strategic_context=strategic_context),
            strategic_context=strategic_context,
            planner=None,
            force=False,
            max_steps=self._planner_step_budget(strategic_context),
        )
        answer_text = "\n\n".join(section for section in sections if section).strip()
        if not answer_text:
            answer_text = "Agent accepted the request but could not produce a detailed answer."
        output["answer"] = answer_text
        output["goal_summary"] = plan.get("goal_summary") or ""
        output["planned_steps"] = plan.get("steps") or []
        output["planning_mode"] = plan.get("planning_mode") or "unknown"
        output["auto_dispatch_followups"] = bool(plan.get("auto_dispatch"))
        return output, answer_text

    def _refresh_session_summary(
        self,
        *,
        session_id: str,
        state_patch: dict[str, Any] | None,
        projected_messages: list[dict[str, Any]],
    ) -> str:
        if not session_id:
            return self.summary_manager.get_summary_text(state_patch)

        existing_summary = self.summary_manager.get_summary_text(state_patch)
        if not self.summary_manager.should_refresh(projected_messages, state_patch):
            return existing_summary

        summarizer = self._llm_summarize_summary_text if self.tool_loop.llm_client.is_configured() else None
        new_summary, strategy = self.summary_manager.build_summary(
            projected_messages,
            existing_summary=existing_summary,
            summarizer=summarizer,
        )
        if not new_summary:
            return existing_summary

        new_state_patch = self.summary_manager.build_state_patch(
            existing_state_patch=state_patch,
            messages=projected_messages,
            summary_text=new_summary,
            strategy=strategy,
        )
        self._patch_session(session_id, {"state_patch": new_state_patch})
        return new_summary

    def _get_session(self, session_id: str) -> dict[str, Any]:
        return self._get(f"{self.settings.control_plane_url}/agent/sessions/{session_id}")

    def _get_session_messages(self, session_id: str, *, limit: int = 40) -> list[dict[str, Any]]:
        return self._get(
            f"{self.settings.control_plane_url}/agent/sessions/{session_id}/messages",
            params={"limit": max(1, min(500, limit)), "tail": True},
        )

    def _patch_session(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.patch(f"{self.settings.control_plane_url}/agent/sessions/{session_id}", json=payload)
        response.raise_for_status()
        return response.json()

    def _resolve_strategic_context(
        self,
        *,
        session: dict[str, Any],
        run: dict[str, Any],
        state_patch: dict[str, Any] | None,
    ) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        if isinstance(state_patch, dict):
            payload = state_patch.get("proactive_distillation")
            if isinstance(payload, dict):
                candidates.append(payload)
        input_payload = run.get("input_payload") if isinstance(run, dict) else None
        if isinstance(input_payload, dict):
            payload = input_payload.get("proactive_distillation")
            if isinstance(payload, dict):
                candidates.append(payload)
        if isinstance(session, dict):
            config_snapshot = session.get("config_snapshot")
            if isinstance(config_snapshot, dict):
                payload = config_snapshot.get("proactive_distillation")
                if isinstance(payload, dict):
                    candidates.append(payload)

        merged = self._merge_strategic_context(candidates)
        if merged.get("strategy_summary") or merged.get("risk_clusters") or merged.get("priority_tier"):
            return merged

        goal_key = str((run.get("goal_key") if isinstance(run, dict) else "") or "").strip()
        if goal_key:
            try:
                goal = self._get_goal(goal_key)
            except Exception:
                goal = {}
            if isinstance(goal, dict):
                meta = goal.get("meta")
                if isinstance(meta, dict):
                    payload = meta.get("distillation_context")
                    if isinstance(payload, dict):
                        candidates.append(payload)
                    last_strategy_context = meta.get("last_strategy_context")
                    if isinstance(last_strategy_context, dict):
                        candidates.append(last_strategy_context)
                    proactive_meta = meta.get("proactive_goal_meta")
                    if isinstance(proactive_meta, dict):
                        candidates.append(
                            {
                                "priority_tier": proactive_meta.get("priority_tier"),
                                "priority_score": proactive_meta.get("priority_score"),
                                "risk_clusters": [],
                                "strategy_summary": "",
                                "strategy_directives": [],
                            }
                        )
        return self._merge_strategic_context(candidates)

    def _get_goal(self, goal_id: str) -> dict[str, Any]:
        return self._get(f"{self.settings.control_plane_url}/agent/goals/{goal_id}")

    @staticmethod
    def _merge_strategic_context(candidates: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        directives: list[str] = []
        risk_clusters: list[dict[str, Any]] = []
        seen_directives: set[str] = set()
        seen_clusters: set[str] = set()

        for item in candidates:
            if not isinstance(item, dict):
                continue
            for key in (
                "distillation_summary",
                "strategy_summary",
                "strategy_feedback_summary",
                "priority_tier",
                "priority_score",
                "priority_boost",
                "feedback_priority_boost",
            ):
                value = item.get(key)
                if value not in (None, "", []):
                    merged[key] = value

            for directive in item.get("strategy_directives") or []:
                text = " ".join(str(directive or "").split()).strip()
                if not text:
                    continue
                dedup_key = text.lower()
                if dedup_key in seen_directives:
                    continue
                seen_directives.add(dedup_key)
                directives.append(text)

            for cluster in item.get("risk_clusters") or []:
                if not isinstance(cluster, dict):
                    continue
                label = " ".join(str(cluster.get("label") or "").split()).strip()
                summary = " ".join(str(cluster.get("summary") or "").split()).strip()
                if not label and not summary:
                    continue
                dedup_key = f"{label.lower()}::{summary.lower()}"
                if dedup_key in seen_clusters:
                    continue
                seen_clusters.add(dedup_key)
                risk_clusters.append(dict(cluster))

        if directives:
            merged["strategy_directives"] = directives[:6]
        if risk_clusters:
            merged["risk_clusters"] = risk_clusters[:6]
        feedback_status_counts: dict[str, int] = {}
        for item in candidates:
            if not isinstance(item, dict):
                continue
            counts = item.get("feedback_status_counts")
            if not isinstance(counts, dict):
                continue
            for key, value in counts.items():
                try:
                    feedback_status_counts[str(key)] = feedback_status_counts.get(str(key), 0) + int(value)
                except (TypeError, ValueError):
                    continue
        if feedback_status_counts:
            merged["feedback_status_counts"] = feedback_status_counts
        return merged

    @staticmethod
    def _summarize_strategic_context(strategic_context: dict[str, Any] | None) -> str:
        if not isinstance(strategic_context, dict):
            return ""
        lines: list[str] = []
        priority_tier = str(strategic_context.get("priority_tier") or "").strip()
        if priority_tier:
            lines.append(f"Strategic priority: {priority_tier}.")
        strategy_summary = str(strategic_context.get("strategy_summary") or "").strip()
        if strategy_summary:
            lines.append(strategy_summary)
        strategy_feedback_summary = str(strategic_context.get("strategy_feedback_summary") or "").strip()
        if strategy_feedback_summary:
            lines.append("Recent strategy feedback: " + strategy_feedback_summary)
        risk_clusters = strategic_context.get("risk_clusters")
        if isinstance(risk_clusters, list) and risk_clusters:
            cluster = risk_clusters[0] if isinstance(risk_clusters[0], dict) else {}
            label = str(cluster.get("label") or "").strip()
            severity = str(cluster.get("severity") or "").strip()
            summary = str(cluster.get("summary") or "").strip()
            if label or summary:
                lines.append(f"Top risk cluster: [{severity or 'medium'}] {label} {summary}".strip())
        directives = strategic_context.get("strategy_directives")
        if isinstance(directives, list) and directives:
            lines.append("Active strategy directives:")
            for item in directives[:3]:
                text = " ".join(str(item or "").split()).strip()
                if text:
                    lines.append(f"- {text}")
        feedback_status_counts = strategic_context.get("feedback_status_counts")
        if isinstance(feedback_status_counts, dict) and feedback_status_counts:
            lines.append(
                "Strategy feedback counts: "
                + ", ".join(f"{key}={value}" for key, value in sorted(feedback_status_counts.items()))
            )
        return "\n".join(lines).strip()

    def _chat_tool_specs(
        self,
        *,
        question: str = "",
        strategic_context: dict[str, Any] | None = None,
    ) -> list[AgentToolSpec]:
        allowed_actions = {
            "agent.get_overview",
            "agent.get_runtime_status",
            "agent.list_alerts",
            "agent.list_goals",
            "agent.get_goal",
            "stats.get",
            "insights.get_brief",
            "insights.ask",
            "search.nl",
            "analysis.get_task",
            "patrol.analysis_backlog",
            "patrol.analysis_failures",
            "patrol.approval_timeout",
            "memory.get_context",
            "memory.read_long_term",
            "memory.append_daily_note",
        }
        specs = [spec for spec in list_tool_specs() if spec.action in allowed_actions]
        preferred_actions = [str(item or "").strip() for item in (strategic_context or {}).get("preferred_tool_actions") or []]
        preferred_rank = {action: index for index, action in enumerate(preferred_actions) if action}
        focus_categories = {
            str(item or "").strip().lower()
            for item in (strategic_context or {}).get("focus_categories") or []
            if str(item or "").strip()
        }
        question_text = (question or "").lower()

        def sort_key(spec: AgentToolSpec) -> tuple[int, int, int, str]:
            preferred = preferred_rank.get(spec.action, 999)
            category_bonus = 0 if spec.category.lower() in focus_categories else 1
            question_bonus = 0 if spec.category.lower() in question_text else 1
            return (preferred, category_bonus, question_bonus, spec.action)

        return sorted(specs, key=sort_key)

    def _derive_tool_policy(
        self,
        *,
        question: str,
        strategic_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base = dict(strategic_context or {})
        combined_text = " ".join(
            str(part or "")
            for part in [
                question,
                base.get("strategy_summary"),
                " ".join(str(item or "") for item in base.get("strategy_directives") or []),
                " ".join(
                    f"{item.get('label', '')} {item.get('summary', '')} {item.get('recommended_strategy', '')}"
                    for item in (base.get("risk_clusters") or [])
                    if isinstance(item, dict)
                ),
            ]
        ).lower()
        priority_tier = str(base.get("priority_tier") or "").strip().lower()

        preferred_actions: list[str] = []
        focus_categories: list[str] = []

        def prefer(*actions: str) -> None:
            for action in actions:
                item = action.strip()
                if item and item not in preferred_actions:
                    preferred_actions.append(item)

        def focus(*categories: str) -> None:
            for category in categories:
                item = category.strip().lower()
                if item and item not in focus_categories:
                    focus_categories.append(item)

        if priority_tier in {"elevated", "urgent"}:
            prefer("agent.list_alerts", "agent.get_overview", "agent.get_runtime_status")
            focus("orchestration")

        if any(keyword in combined_text for keyword in ("backlog", "capacity", "analysis", "nightly backlog")):
            prefer("patrol.analysis_backlog", "patrol.analysis_failures", "stats.get", "insights.ask", "analysis.get_task")
            focus("patrol", "insight", "analysis")

        if any(keyword in combined_text for keyword in ("approval", "escalation", "operator", "handoff")):
            prefer("patrol.approval_timeout", "agent.list_alerts", "agent.list_goals", "memory.append_daily_note")
            focus("patrol", "orchestration", "memory")

        if any(keyword in combined_text for keyword in ("investigate", "search", "camera", "person", "incident", "failure")):
            prefer("search.nl", "insights.ask", "analysis.get_task", "agent.get_goal")
            focus("search", "insight", "analysis")

        if any(keyword in combined_text for keyword in ("memory", "strategy", "long-term", "长期", "策略")):
            prefer("memory.get_context", "memory.read_long_term", "memory.append_daily_note")
            focus("memory")

        if not preferred_actions:
            prefer("agent.get_overview", "agent.list_alerts", "agent.get_runtime_status")
            focus("orchestration")

        verification_mode = "strict" if priority_tier in {"elevated", "urgent"} else "standard"
        tool_loop_max_iterations = 8 if priority_tier == "urgent" else 7 if priority_tier == "elevated" else 6
        planner_step_budget = 4 if priority_tier == "urgent" else 3
        tool_retry_limit = 3 if priority_tier == "urgent" else 2 if priority_tier == "elevated" else 2
        max_tool_fallbacks = 2 if priority_tier == "urgent" else 1 if priority_tier == "elevated" else 0
        fallback_actions = self._fallback_actions_for_policy(
            priority_tier=priority_tier,
            preferred_actions=preferred_actions,
            focus_categories=focus_categories,
        )
        base["preferred_tool_actions"] = preferred_actions
        base["focus_categories"] = focus_categories
        base["verification_mode"] = verification_mode
        base["tool_loop_max_iterations"] = tool_loop_max_iterations
        base["planner_step_budget"] = planner_step_budget
        base["tool_retry_limit"] = tool_retry_limit
        base["max_tool_fallbacks"] = max_tool_fallbacks
        base["fallback_actions"] = fallback_actions
        return base

    def _fallback_actions_for_policy(
        self,
        *,
        priority_tier: str,
        preferred_actions: list[str],
        focus_categories: list[str],
    ) -> dict[str, list[str]]:
        mapping: dict[str, list[str]] = {
            "agent.get_overview": ["agent.list_alerts", "agent.get_runtime_status"],
            "agent.list_alerts": ["agent.get_overview"],
            "agent.get_runtime_status": ["agent.get_overview"],
            "insights.ask": ["insights.get_brief", "stats.get"],
            "insights.get_brief": ["stats.get"],
            "patrol.analysis_backlog": ["agent.get_overview", "stats.get"],
            "patrol.analysis_failures": ["agent.get_overview", "stats.get"],
            "patrol.approval_timeout": ["agent.list_alerts", "agent.get_overview"],
            "search.nl": ["insights.ask", "agent.list_alerts"],
        }
        if priority_tier == "urgent":
            mapping.setdefault("analysis.get_task", ["agent.get_overview"])
        if "memory" in focus_categories:
            mapping.setdefault("memory.get_context", ["memory.read_long_term"])
        if any(action.startswith("patrol.") for action in preferred_actions):
            mapping.setdefault("stats.get", ["agent.get_overview"])
        return mapping

    @staticmethod
    def _tool_loop_iteration_budget(strategic_context: dict[str, Any] | None) -> int:
        try:
            return max(3, min(10, int((strategic_context or {}).get("tool_loop_max_iterations") or 6)))
        except (TypeError, ValueError):
            return 6

    @staticmethod
    def _planner_step_budget(strategic_context: dict[str, Any] | None) -> int:
        try:
            return max(1, min(6, int((strategic_context or {}).get("planner_step_budget") or 3)))
        except (TypeError, ValueError):
            return 3

    @staticmethod
    def _tool_retry_attempts(tool_spec: AgentToolSpec | None, strategic_context: dict[str, Any] | None) -> int:
        if tool_spec is None or not tool_spec.idempotent:
            return 1
        try:
            requested = int((strategic_context or {}).get("tool_retry_limit") or 2)
        except (TypeError, ValueError):
            requested = 2
        return max(1, min(4, requested))

    def _try_fallback_actions(
        self,
        action: str,
        *,
        prompt: str,
        params: dict[str, Any],
        run_id: str,
        session_id: str,
        claim: dict[str, Any] | None,
        strategic_context: dict[str, Any] | None,
        primary_error: Exception | None,
    ) -> tuple[dict[str, Any], str] | None:
        if not isinstance(strategic_context, dict):
            return None

        try:
            fallback_limit = max(0, min(3, int(strategic_context.get("max_tool_fallbacks") or 0)))
        except (TypeError, ValueError):
            fallback_limit = 0
        if fallback_limit <= 0:
            return None

        fallback_actions = strategic_context.get("fallback_actions")
        if not isinstance(fallback_actions, dict):
            return None
        chain = fallback_actions.get(action)
        if not isinstance(chain, list) or not chain:
            return None

        fallback_errors: list[str] = []
        for fallback_action in chain[:fallback_limit]:
            fallback_name = str(fallback_action or "").strip()
            if not fallback_name or fallback_name == action:
                continue
            fallback_params = self._adapt_fallback_params(
                fallback_action=fallback_name,
                primary_action=action,
                prompt=prompt,
                params=params,
            )
            try:
                output_payload, result_summary = self._execute_action_with_retry(
                    fallback_name,
                    prompt=prompt,
                    params=fallback_params,
                    run_id=run_id,
                    session_id=session_id,
                    claim=claim,
                    strategic_context=strategic_context,
                    allow_fallback=False,
                )
                wrapped_payload = dict(output_payload or {})
                wrapped_payload["fallback"] = {
                    "primary_action": action,
                    "fallback_action": fallback_name,
                    "primary_error": str(primary_error) if primary_error else "",
                }
                summary = (
                    f"Primary action {action} failed; fallback {fallback_name} succeeded. "
                    f"Original error: {primary_error}"
                ).strip()
                if result_summary:
                    summary = f"{summary} | {result_summary}"
                return wrapped_payload, summary
            except Exception as exc:
                fallback_errors.append(f"{fallback_name}: {exc}")

        if primary_error is not None and fallback_errors:
            raise RuntimeError(f"{primary_error}; fallback chain failed -> {' | '.join(fallback_errors)}")
        return None

    @staticmethod
    def _adapt_fallback_params(
        *,
        fallback_action: str,
        primary_action: str,
        prompt: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        interval = params.get("interval", 60)
        if fallback_action == "insights.get_brief":
            return {"interval": interval}
        if fallback_action == "stats.get":
            return {"interval": interval}
        if fallback_action == "agent.list_alerts":
            return {
                "status": params.get("status", "open"),
                "severity": params.get("severity"),
                "limit": params.get("limit", 10),
            }
        if fallback_action == "agent.get_overview":
            return {}
        if fallback_action == "agent.get_runtime_status":
            return {}
        if fallback_action in {"patrol.analysis_backlog", "patrol.analysis_failures", "patrol.approval_timeout"}:
            return dict(params or {})
        if fallback_action == "insights.ask":
            return {"question": str(params.get("query") or params.get("question") or prompt or "").strip(), "interval": interval, "use_llm": 1}
        if fallback_action == "search.nl":
            return {"query": str(params.get("question") or params.get("query") or prompt or "").strip()}
        if fallback_action == "memory.read_long_term":
            return {}
        return dict(params or {})

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
            (
                f"- Active goals: {counts.get('active_goals', 0)}, blocked goals: {counts.get('blocked_goals', 0)}"
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

    @staticmethod
    def _summarize_runtime_status(runtime_status: dict[str, Any]) -> str:
        loops = runtime_status.get("loops") or {}
        lines = ["Runtime status:"]
        for key in ("runtime", "scheduler", "email"):
            item = loops.get(key) or {}
            lines.append(
                f"- {key}: {item.get('health') or 'unknown'}, "
                f"last_seen={item.get('last_seen_at') or '--'}, restarts={item.get('restart_count', 0)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _summarize_alerts(alerts: list[dict[str, Any]]) -> str:
        if not alerts:
            return "Active alerts: none."
        lines = [f"Active alerts: {len(alerts)}"]
        for alert in alerts[:5]:
            lines.append(
                f"- [{alert.get('severity')}] {alert.get('summary')} ({alert.get('scope_id') or alert.get('scope_type') or 'global'})"
            )
        return "\n".join(lines)

    @staticmethod
    def _messages_end_with_prompt(messages: list[dict[str, Any]], prompt: str) -> bool:
        if not messages:
            return False
        return _extract_message_text(messages[-1]) == prompt.strip()

    def _get(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _post(self, url: str, *, json: dict[str, Any] | None = None) -> Any:
        response = self.client.post(url, json=json)
        response.raise_for_status()
        return response.json()

    def _wrap(
        self,
        action: str,
        prompt: str,
        params: dict[str, Any],
        data: Any,
        *,
        strategic_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        verified_data = self._verify_tool_data(action, data, strategic_context=strategic_context)
        payload = {
            "executor_mode": "api_only",
            "action": action,
            "trigger_prompt": prompt,
            "params": params,
            "data": verified_data,
        }
        if isinstance(strategic_context, dict) and strategic_context:
            payload["verification_policy"] = {
                "mode": strategic_context.get("verification_mode") or "standard",
                "priority_tier": strategic_context.get("priority_tier") or "normal",
                "preferred_tool_actions": list(strategic_context.get("preferred_tool_actions") or [])[:5],
                "focus_categories": list(strategic_context.get("focus_categories") or [])[:5],
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

    def _llm_summarize_summary_text(self, summary_prompt: str) -> str:
        response = self.tool_loop.llm_client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Compress prior session history for an always-on operations agent. "
                        "Return plain text only. Keep durable facts, operator intent, unresolved work, "
                        "and concrete constraints."
                    ),
                },
                {"role": "user", "content": summary_prompt},
            ],
            tools=[],
            temperature=0.1,
            max_tokens=500,
        )
        choices = response.get("choices") or []
        message = (choices[0] or {}).get("message") or {}
        content = self._stringify_llm_content(message.get("content"))
        if not content.strip():
            raise ValueError("LLM summary response did not contain text")
        return content.strip()

    def _llm_plan_follow_up_steps(self, planning_prompt: str) -> str:
        response = self.tool_loop.llm_client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Plan follow-up steps for an autonomous operations agent. "
                        "Return JSON only."
                    ),
                },
                {"role": "user", "content": planning_prompt},
            ],
            tools=[],
            temperature=0.1,
            max_tokens=700,
        )
        choices = response.get("choices") or []
        message = (choices[0] or {}).get("message") or {}
        return self._stringify_llm_content(message.get("content")).strip()

    def _llm_extract_long_term_fact(self, extraction_prompt: str) -> str:
        response = self.tool_loop.llm_client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract one durable fact or operator instruction for long-term memory. "
                        "Return plain text only, or an empty string if nothing should be stored."
                    ),
                },
                {"role": "user", "content": extraction_prompt},
            ],
            tools=[],
            temperature=0.0,
            max_tokens=120,
        )
        choices = response.get("choices") or []
        message = (choices[0] or {}).get("message") or {}
        return self._stringify_llm_content(message.get("content")).strip()

    def _verify_tool_data(
        self,
        action: str,
        data: Any,
        *,
        strategic_context: dict[str, Any] | None = None,
    ) -> Any:
        def require_dict(value: Any, *, context: str) -> dict[str, Any]:
            if not isinstance(value, dict):
                raise ValueError(f"{context} must return an object")
            return value

        def require_list(value: Any, *, context: str) -> list[Any]:
            if not isinstance(value, list):
                raise ValueError(f"{context} must return a list")
            return value

        def require_key(mapping: dict[str, Any], key: str, *, context: str) -> None:
            if key not in mapping:
                raise ValueError(f"{context} must include `{key}`")

        if action == "search.structured":
            return require_list(data, context=action)

        payload = require_dict(data, context=action)

        if action == "agent.get_overview":
            require_key(payload, "counts", context=action)
            if self._is_strict_verification(strategic_context):
                counts = require_dict(payload.get("counts"), context=f"{action}.counts")
                if not any(key in counts for key in ("active_runs", "queued_runs", "active_goals", "blocked_goals")):
                    raise ValueError(f"{action}.counts missing strategic workload keys")
            return payload
        if action == "agent.get_runtime_status":
            require_key(payload, "loops", context=action)
            if self._is_strict_verification(strategic_context):
                loops = require_dict(payload.get("loops"), context=f"{action}.loops")
                for key in ("runtime", "scheduler", "email"):
                    if key not in loops:
                        raise ValueError(f"{action}.loops must include `{key}` in strict mode")
            return payload
        if action == "agent.list_alerts":
            alerts = payload.get("alerts")
            require_list(alerts, context=f"{action}.alerts")
            return payload
        if action == "agent.list_goals":
            goals = payload.get("goals")
            require_list(goals, context=f"{action}.goals")
            return payload
        if action == "agent.get_goal":
            goal = payload.get("goal")
            require_dict(goal, context=f"{action}.goal")
            return payload
        if action == "stats.get":
            if "total_analyses" not in payload and "traffic_trend" not in payload:
                raise ValueError(f"{action} returned an unexpected payload")
            if self._focuses_on(strategic_context, "capacity", "analysis", "insight"):
                if not any(key in payload for key in ("peak_hour", "traffic_trend", "total_analyses", "today_total")):
                    raise ValueError(f"{action} missing capacity-oriented indicators")
            return payload
        if action == "insights.get_brief":
            if "summary" not in payload and "brief" not in payload:
                raise ValueError(f"{action} must include `summary` or `brief`")
            return payload
        if action == "insights.ask":
            require_key(payload, "answer", context=action)
            answer = str(payload.get("answer") or "").strip()
            if self._is_strict_verification(strategic_context) and len(answer) < 20:
                raise ValueError(f"{action} answer too short under strict verification")
            return payload
        if action == "search.nl":
            require_key(payload, "results", context=action)
            results = payload.get("results")
            require_list(results, context=f"{action}.results")
            return payload
        if action == "analysis.get_task":
            require_key(payload, "task_id", context=action)
            require_key(payload, "status", context=action)
            return payload
        if action == "agent.chat":
            require_key(payload, "answer", context=action)
            require_key(payload, "tool_events", context=action)
            return payload
        if action.startswith("patrol."):
            require_key(payload, "breached", context=action)
            if payload.get("breached") is True:
                detail_keys = {
                    "patrol.analysis_backlog": "stale_tasks",
                    "patrol.analysis_failures": "failed_tasks",
                    "patrol.approval_timeout": "timed_out_approvals",
                }
                detail_key = detail_keys.get(action)
                if detail_key:
                    details = payload.get(detail_key)
                    if not isinstance(details, list) or not details:
                        raise ValueError(f"{action} breached payload must include non-empty `{detail_key}`")
            return payload
        if action == "memory.get_context":
            require_key(payload, "context", context=action)
            return payload
        if action == "memory.read_long_term":
            require_key(payload, "content", context=action)
            return payload
        if action == "memory.write_long_term":
            require_key(payload, "path", context=action)
            return payload
        if action == "memory.append_daily_note":
            require_key(payload, "path", context=action)
            require_key(payload, "heading", context=action)
            return payload

        return payload

    @staticmethod
    def _is_strict_verification(strategic_context: dict[str, Any] | None) -> bool:
        return str((strategic_context or {}).get("verification_mode") or "").strip().lower() == "strict"

    @staticmethod
    def _focuses_on(strategic_context: dict[str, Any] | None, *keywords: str) -> bool:
        haystack = " ".join(
            str(part or "")
            for part in [
                (strategic_context or {}).get("strategy_summary"),
                " ".join(str(item or "") for item in (strategic_context or {}).get("strategy_directives") or []),
                " ".join(str(item or "") for item in (strategic_context or {}).get("focus_categories") or []),
                " ".join(str(item or "") for item in (strategic_context or {}).get("preferred_tool_actions") or []),
            ]
        ).lower()
        return any(keyword.lower() in haystack for keyword in keywords)

    @staticmethod
    def _is_transient_exception(exc: Exception) -> bool:
        if isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.TimeoutException,
                httpx.ReadError,
                httpx.RemoteProtocolError,
            ),
        ):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code if exc.response is not None else 0
            return status_code in {408, 429, 500, 502, 503, 504}
        return False

    @staticmethod
    def _stringify_llm_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            return "\n".join(parts)
        return ""

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
