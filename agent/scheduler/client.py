from __future__ import annotations

from typing import Any

import httpx


class SchedulerControlPlaneClient:
    def __init__(self, base_url: str, *, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def dispatch_due(self, *, limit: int) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/agent/scheduled-tasks/dispatch-due",
            params={"limit": limit},
        )
        response.raise_for_status()
        return response.json()
