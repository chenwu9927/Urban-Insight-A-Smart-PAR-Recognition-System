from __future__ import annotations

from typing import Any

import httpx


class ControlPlaneClient:
    def __init__(self, base_url: str, *, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def claim_run(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        schedule_modes: list[str] | None = None,
    ) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/agent/runs/claim",
            json={
                "worker_id": worker_id,
                "lease_seconds": lease_seconds,
                "schedule_modes": schedule_modes or [],
            },
        )
        response.raise_for_status()
        return response.json()

    def heartbeat_run(
        self,
        *,
        run_id: str,
        worker_id: str,
        lease_seconds: int,
        progress: int | None = None,
    ) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/agent/runs/{run_id}/heartbeat",
            json={
                "worker_id": worker_id,
                "lease_seconds": lease_seconds,
                "progress": progress,
            },
        )
        response.raise_for_status()
        return response.json()

    def complete_run(
        self,
        *,
        run_id: str,
        worker_id: str,
        output_payload: dict[str, Any] | None = None,
        result_summary: str | None = None,
    ) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/agent/runs/{run_id}/complete",
            json={
                "worker_id": worker_id,
                "output_payload": output_payload,
                "result_summary": result_summary,
            },
        )
        response.raise_for_status()
        return response.json()

    def fail_run(
        self,
        *,
        run_id: str,
        worker_id: str,
        error_message: str,
    ) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/agent/runs/{run_id}/fail",
            json={
                "worker_id": worker_id,
                "error_message": error_message,
            },
        )
        response.raise_for_status()
        return response.json()
