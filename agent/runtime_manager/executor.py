from __future__ import annotations

from typing import Any

import httpx

from agent.runtime_manager.config import RuntimeManagerSettings


class ExecutorClient:
    def __init__(self, settings: RuntimeManagerSettings) -> None:
        self.settings = settings
        self.client = httpx.Client(timeout=settings.timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def execute(self, claim: dict[str, Any]) -> tuple[dict[str, Any], str]:
        response = self.client.post(
            f"{self.settings.executor_url}/execute",
            json={"claim": claim},
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload.get("output_payload") or {}, str(payload.get("result_summary") or "")
