from __future__ import annotations

from typing import Any, Callable

from agent.memory_store import AgentMemoryStore
from agent.strategy_feedback import AgentStrategyFeedbackEngine


class AgentMemoryWritebackPolicy:
    def __init__(self, memory_store: AgentMemoryStore) -> None:
        self.memory = memory_store
        self.strategy_feedback = AgentStrategyFeedbackEngine()

    def apply(
        self,
        *,
        action: str,
        params: dict[str, Any],
        output_payload: dict[str, Any],
        result_summary: str,
        session_id: str = "",
        run_id: str = "",
        long_term_extractor: Callable[[str], str] | None = None,
    ) -> dict[str, Any]:
        artifacts: dict[str, Any] = {
            "daily_note_path": None,
            "long_term_path": None,
            "long_term_promoted": False,
            "strategy_note_path": None,
            "strategy_long_term_path": None,
            "strategy_feedback_status": None,
            "strategy_feedback_summary": None,
        }

        if action == "agent.chat":
            question = str(params.get("question") or output_payload.get("question") or "").strip()
            answer = str(output_payload.get("answer") or result_summary or "").strip()
            if question or answer:
                body = self._chat_note_body(
                    question=question,
                    answer=answer,
                    planned_steps=output_payload.get("planned_steps"),
                )
                note_path = self.memory.append_daily_note(
                    body,
                    heading=self._heading("agent chat", run_id=run_id, session_id=session_id),
                )
                artifacts["daily_note_path"] = str(note_path)

            if self._should_promote_chat_memory(question=question, params=params):
                durable_fact = self._extract_durable_fact(
                    question=question,
                    answer=answer,
                    long_term_extractor=long_term_extractor,
                )
                if durable_fact:
                    long_term_path = self.memory.append_long_term_fact(durable_fact)
                    artifacts["long_term_path"] = str(long_term_path)
                    artifacts["long_term_promoted"] = True

            strategy_feedback = self.strategy_feedback.evaluate_chat_feedback(
                output_payload=output_payload,
                result_summary=result_summary,
                run_id=run_id,
                session_id=session_id,
            )
            if strategy_feedback is not None:
                note_path = self.memory.append_daily_note(
                    strategy_feedback.note_body,
                    heading=strategy_feedback.heading,
                )
                artifacts["strategy_note_path"] = str(note_path)
                artifacts["strategy_feedback_status"] = strategy_feedback.status
                artifacts["strategy_feedback_summary"] = strategy_feedback.summary
                if strategy_feedback.long_term_fact:
                    long_term_path = self.memory.append_long_term_fact(strategy_feedback.long_term_fact)
                    artifacts["strategy_long_term_path"] = str(long_term_path)
            return artifacts

        if action.startswith("patrol."):
            payload = output_payload.get("data") if isinstance(output_payload.get("data"), dict) else output_payload
            breached = bool((payload or {}).get("breached"))
            if breached:
                note_text = str(result_summary or "").strip() or f"{action} reported a breached condition."
                note_path = self.memory.append_daily_note(
                    note_text,
                    heading=self._heading(action, run_id=run_id, session_id=session_id),
                )
                artifacts["daily_note_path"] = str(note_path)
            return artifacts

        return artifacts

    @staticmethod
    def _heading(prefix: str, *, run_id: str, session_id: str) -> str:
        parts = [prefix]
        if run_id:
            parts.append(f"run={run_id}")
        if session_id:
            parts.append(f"session={session_id}")
        return " | ".join(parts)

    @staticmethod
    def _chat_note_body(*, question: str, answer: str, planned_steps: Any) -> str:
        lines = []
        if question:
            lines.extend(["Question:", question.strip(), ""])
        if answer:
            lines.extend(["Answer:", answer.strip(), ""])
        if isinstance(planned_steps, list) and planned_steps:
            lines.append("Planned follow-up steps:")
            for step in planned_steps[:5]:
                if not isinstance(step, dict):
                    continue
                title = str(step.get("title") or step.get("action") or "follow-up").strip()
                rationale = str(step.get("rationale") or "").strip()
                if rationale:
                    lines.append(f"- {title}: {rationale}")
                else:
                    lines.append(f"- {title}")
        return "\n".join(lines).strip()

    @staticmethod
    def _should_promote_chat_memory(*, question: str, params: dict[str, Any]) -> bool:
        if params.get("promote_memory") is True:
            return True
        normalized = question.lower()
        keywords = ("remember", "long-term", "长期", "记住", "以后都", "默认", "always")
        return any(keyword in normalized for keyword in keywords)

    @staticmethod
    def _extract_durable_fact(
        *,
        question: str,
        answer: str,
        long_term_extractor: Callable[[str], str] | None = None,
    ) -> str:
        prompt = (
            "Extract one durable operator instruction or platform fact suitable for long-term memory.\n"
            "Return plain text only. If there is nothing durable, return an empty string.\n\n"
            f"Question:\n{question.strip()}\n\nAnswer:\n{answer.strip()}"
        ).strip()
        if long_term_extractor is not None:
            try:
                extracted = (long_term_extractor(prompt) or "").strip()
            except Exception:
                extracted = ""
            if extracted:
                return " ".join(extracted.split()).strip()
        if not question.strip():
            return ""
        return " ".join(question.split()).strip()
