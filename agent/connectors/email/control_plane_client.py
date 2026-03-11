from __future__ import annotations

from typing import Any

import httpx


class EmailControlPlaneClient:
    def __init__(self, base_url: str, *, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(f"{self.base_url}/agent/sessions", json=payload)
        response.raise_for_status()
        return response.json()

    def get_session(self, session_id: str) -> dict[str, Any]:
        response = self.client.get(f"{self.base_url}/agent/sessions/{session_id}")
        response.raise_for_status()
        return response.json()

    def create_message(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(f"{self.base_url}/agent/sessions/{session_id}/messages", json=payload)
        response.raise_for_status()
        return response.json()

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(f"{self.base_url}/agent/runs", json=payload)
        response.raise_for_status()
        return response.json()

    def list_runs(self, **params: Any) -> list[dict[str, Any]]:
        response = self.client.get(f"{self.base_url}/agent/runs", params=params)
        response.raise_for_status()
        return response.json()

    def get_run(self, run_id: str) -> dict[str, Any]:
        response = self.client.get(f"{self.base_url}/agent/runs/{run_id}")
        response.raise_for_status()
        return response.json()

    def list_approvals(self, **params: Any) -> list[dict[str, Any]]:
        response = self.client.get(f"{self.base_url}/agent/approvals", params=params)
        response.raise_for_status()
        return response.json()

    def answer_approval(self, approval_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(f"{self.base_url}/agent/approvals/{approval_id}/answer", json=payload)
        response.raise_for_status()
        return response.json()

    def list_deliveries(self, **params: Any) -> list[dict[str, Any]]:
        response = self.client.get(f"{self.base_url}/agent/deliveries", params=params)
        response.raise_for_status()
        return response.json()

    def create_delivery(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(f"{self.base_url}/agent/deliveries", json=payload)
        response.raise_for_status()
        return response.json()
