from __future__ import annotations

import datetime
from typing import Any, Callable


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


class AgentSessionSummaryManager:
    STATE_KEY = "context_summary"

    def __init__(
        self,
        *,
        refresh_threshold: int = 10,
        keep_recent_messages: int = 8,
        max_source_messages: int = 14,
    ) -> None:
        self.refresh_threshold = max(6, int(refresh_threshold))
        self.keep_recent_messages = max(4, int(keep_recent_messages))
        self.max_source_messages = max(self.keep_recent_messages, int(max_source_messages))

    def get_summary_text(self, state_patch: dict[str, Any] | None) -> str:
        payload = self.get_summary_payload(state_patch)
        text = payload.get("text")
        return text.strip() if isinstance(text, str) else ""

    def get_summary_payload(self, state_patch: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(state_patch, dict):
            return {}
        payload = state_patch.get(self.STATE_KEY)
        return payload if isinstance(payload, dict) else {}

    def should_refresh(self, messages: list[dict[str, Any]], state_patch: dict[str, Any] | None) -> bool:
        total = len(messages)
        if total < self.refresh_threshold:
            return False
        payload = self.get_summary_payload(state_patch)
        summarized_count = int(payload.get("message_count") or 0)
        if summarized_count <= 0:
            return True
        return total - summarized_count >= max(2, self.keep_recent_messages // 2)

    def history_for_prompt(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(messages) <= self.keep_recent_messages:
            return list(messages)
        return list(messages[-self.keep_recent_messages :])

    def build_summary(
        self,
        messages: list[dict[str, Any]],
        *,
        existing_summary: str = "",
        summarizer: Callable[[str], str] | None = None,
    ) -> tuple[str, str]:
        normalized = self.summary_source_messages(messages)
        if not normalized:
            return existing_summary.strip(), "carry_forward"

        summary_prompt = self.build_summary_prompt(normalized, existing_summary=existing_summary)
        if summarizer is not None:
            try:
                candidate = (summarizer(summary_prompt) or "").strip()
            except Exception:
                candidate = ""
            if candidate:
                return candidate, "llm_v1"

        return self._heuristic_summary(normalized, existing_summary=existing_summary), "heuristic_v2"

    def summary_source_messages(self, messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
        if len(messages) <= self.keep_recent_messages:
            return []

        older_messages = messages[: -self.keep_recent_messages]
        normalized: list[tuple[str, str]] = []
        for message in older_messages:
            role = str(message.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            text = _extract_message_text(message)
            if not text:
                continue
            normalized.append((role, text))

        if len(normalized) > self.max_source_messages:
            normalized = normalized[-self.max_source_messages :]
        return normalized

    def build_summary_prompt(
        self,
        normalized_messages: list[tuple[str, str]],
        *,
        existing_summary: str = "",
    ) -> str:
        lines = [
            "Summarize the prior conversation for an always-on operations agent.",
            "Keep durable facts, unresolved tasks, operator intent, and any constraints.",
            "Do not restate obvious chatter. Keep the output concise and operational.",
        ]
        if existing_summary.strip():
            lines.extend(["", "Existing summary:", existing_summary.strip()])
        lines.extend(["", "Messages to compress:"])
        for role, text in normalized_messages:
            label = "User" if role == "user" else "Agent"
            compact = " ".join(text.split())
            lines.append(f"- {label}: {compact}")
        return "\n".join(lines).strip()

    def build_state_patch(
        self,
        *,
        existing_state_patch: dict[str, Any] | None,
        messages: list[dict[str, Any]],
        summary_text: str,
        strategy: str,
    ) -> dict[str, Any]:
        patch = dict(existing_state_patch or {})
        patch[self.STATE_KEY] = {
            "text": summary_text.strip(),
            "message_count": len(messages),
            "keep_recent_messages": self.keep_recent_messages,
            "compressed_message_count": max(0, len(messages) - self.keep_recent_messages),
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "strategy": strategy,
        }
        return patch

    def _heuristic_summary(
        self,
        normalized_messages: list[tuple[str, str]],
        *,
        existing_summary: str = "",
    ) -> str:
        lines: list[str] = []
        if existing_summary.strip():
            lines.append("Previous summary:")
            lines.append(existing_summary.strip())
            lines.append("")

        lines.append("Conversation summary:")
        for role, text in normalized_messages:
            label = "User" if role == "user" else "Agent"
            compact = " ".join(text.split())
            if len(compact) > 220:
                compact = compact[:217].rstrip() + "..."
            lines.append(f"- {label}: {compact}")

        return "\n".join(lines).strip()
