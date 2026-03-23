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

    def sweep_goals(
        self,
        *,
        limit: int,
        verification_cooldown_minutes: int,
        goal_recovery_minutes: int,
    ) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/agent/goals/sweep",
            params={
                "limit": limit,
                "verification_cooldown_minutes": verification_cooldown_minutes,
                "goal_recovery_minutes": goal_recovery_minutes,
            },
        )
        response.raise_for_status()
        return response.json()

    def boost_patrols_from_memory(
        self,
        *,
        lookback_days: int,
        boost_cooldown_minutes: int,
    ) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/agent/scheduled-tasks/boost-from-memory",
            params={
                "lookback_days": lookback_days,
                "boost_cooldown_minutes": boost_cooldown_minutes,
            },
        )
        response.raise_for_status()
        return response.json()

    def create_proactive_goals_from_memory(
        self,
        *,
        lookback_days: int,
        recurrence_threshold: int,
        use_llm_distillation: bool,
        distilled_limit: int,
        max_memory_chars: int,
        min_distilled_confidence: float,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/agent/goals/proactive-from-memory",
            params={
                "lookback_days": lookback_days,
                "recurrence_threshold": recurrence_threshold,
                "use_llm_distillation": int(bool(use_llm_distillation)),
                "distilled_limit": distilled_limit,
                "max_memory_chars": max_memory_chars,
                "min_distilled_confidence": min_distilled_confidence,
                "ttl_seconds": ttl_seconds,
            },
        )
        response.raise_for_status()
        return response.json()
