from __future__ import annotations

from typing import Any

import httpx

from agent.executor.config import ExecutorSettings


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

    def close(self) -> None:
        self.client.close()

    def execute(self, claim: dict[str, Any]) -> tuple[dict[str, Any], str]:
        run = claim.get("run") or {}
        trigger_message = claim.get("trigger_message") or {}
        action = ((run.get("input_payload") or {}).get("action") or "").strip()
        prompt = extract_prompt(trigger_message)
        params = (run.get("input_payload") or {}).get("params") or {}

        if not action:
            output_payload = {
                "executor_mode": "api_only",
                "action": None,
                "status": "accepted",
                "trigger_prompt": prompt,
                "message": "Run was accepted by executor. No explicit action was provided yet.",
            }
            return output_payload, "Accepted run without explicit action"

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

        raise ValueError(f"Unsupported action: {action}")

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
        return {
            "executor_mode": "api_only",
            "action": action,
            "trigger_prompt": prompt,
            "params": params,
            "data": data,
        }
