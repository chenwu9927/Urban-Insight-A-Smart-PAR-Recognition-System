from __future__ import annotations

import time

from agent.scheduler.client import SchedulerControlPlaneClient
from agent.scheduler.config import SchedulerSettings


class AgentScheduler:
    def __init__(self, settings: SchedulerSettings | None = None) -> None:
        self.settings = settings or SchedulerSettings()
        self.client = SchedulerControlPlaneClient(self.settings.control_plane_url)

    def close(self) -> None:
        self.client.close()

    def run_once(self) -> dict:
        result = self.client.dispatch_due(limit=self.settings.dispatch_limit)
        priority_dispatch_result = {"dispatched": 0, "skipped": 0, "run_ids": []}
        feedback_sweep_result = {"inspected": 0, "synced": 0, "replanned": 0, "verified": 0, "recovered": 0, "run_ids": []}
        goal_result = self.client.sweep_goals(
            limit=self.settings.goal_sweep_limit,
            verification_cooldown_minutes=self.settings.goal_verification_cooldown_minutes,
            goal_recovery_minutes=self.settings.goal_recovery_minutes,
        )
        memory_result = self.client.boost_patrols_from_memory(
            lookback_days=self.settings.memory_boost_lookback_days,
            boost_cooldown_minutes=self.settings.memory_boost_cooldown_minutes,
        )
        proactive_result = self.client.create_proactive_goals_from_memory(
            lookback_days=self.settings.proactive_goal_lookback_days,
            recurrence_threshold=self.settings.proactive_goal_recurrence_threshold,
            use_llm_distillation=self.settings.proactive_goal_llm_distillation_enabled,
            distilled_limit=self.settings.proactive_goal_llm_candidate_limit,
            max_memory_chars=self.settings.proactive_goal_memory_max_chars,
            min_distilled_confidence=self.settings.proactive_goal_min_distilled_confidence,
            ttl_seconds=self.settings.proactive_goal_ttl_seconds,
        )
        if result.get("dispatched") or result.get("skipped"):
            print(
                "[agent-scheduler] dispatch",
                {
                    "dispatched": result.get("dispatched"),
                    "skipped": result.get("skipped"),
                    "run_ids": result.get("run_ids"),
                },
            )
        if goal_result.get("replanned") or goal_result.get("verified") or goal_result.get("recovered"):
            print(
                "[agent-scheduler] goal sweep",
                {
                    "inspected": goal_result.get("inspected"),
                    "replanned": goal_result.get("replanned"),
                    "verified": goal_result.get("verified"),
                    "recovered": goal_result.get("recovered"),
                    "run_ids": goal_result.get("run_ids"),
                },
            )
        if memory_result.get("triggered"):
            print(
                "[agent-scheduler] memory patrol boost",
                {
                    "scanned": memory_result.get("scanned"),
                    "triggered": memory_result.get("triggered"),
                    "run_ids": memory_result.get("run_ids"),
                    "task_ids": memory_result.get("task_ids"),
                },
            )
        if proactive_result.get("created"):
            print(
                "[agent-scheduler] proactive goals",
                {
                    "candidates": proactive_result.get("candidates"),
                    "created": proactive_result.get("created"),
                    "rule_candidates": proactive_result.get("rule_candidates"),
                    "llm_candidates": proactive_result.get("llm_candidates"),
                    "llm_distillation_used": proactive_result.get("llm_distillation_used"),
                    "priority_tier": proactive_result.get("priority_tier"),
                    "priority_boost": proactive_result.get("priority_boost"),
                    "feedback_priority_boost": proactive_result.get("feedback_priority_boost"),
                    "risk_clusters": len(proactive_result.get("risk_clusters") or []),
                    "goal_ids": proactive_result.get("goal_ids"),
                    "run_ids": proactive_result.get("run_ids"),
                },
            )
        elif proactive_result.get("llm_error"):
            print(
                "[agent-scheduler] proactive goal distillation degraded",
                {
                    "rule_candidates": proactive_result.get("rule_candidates"),
                    "llm_candidates": proactive_result.get("llm_candidates"),
                    "llm_error": proactive_result.get("llm_error"),
                },
            )
        if (
            self.settings.proactive_goal_priority_dispatch_enabled
            and proactive_result.get("created")
            and int(proactive_result.get("priority_boost") or 0) > 0
        ):
            dispatch_limit = min(
                self.settings.proactive_goal_priority_dispatch_limit,
                max(
                    1,
                    int(proactive_result.get("created") or 0) + int(proactive_result.get("priority_boost") or 0),
                ),
            )
            priority_dispatch_result = self.client.dispatch_due(limit=dispatch_limit)
            if priority_dispatch_result.get("dispatched") or priority_dispatch_result.get("skipped"):
                print(
                    "[agent-scheduler] proactive priority dispatch",
                    {
                        "priority_tier": proactive_result.get("priority_tier"),
                        "dispatch_limit": dispatch_limit,
                        "dispatched": priority_dispatch_result.get("dispatched"),
                        "skipped": priority_dispatch_result.get("skipped"),
                    "run_ids": priority_dispatch_result.get("run_ids"),
                },
            )
        feedback_status_counts = proactive_result.get("feedback_status_counts") or {}
        needs_adjustment = int(feedback_status_counts.get("needs_adjustment") or 0)
        if (
            self.settings.proactive_goal_feedback_sweep_enabled
            and int(proactive_result.get("feedback_priority_boost") or 0) > 0
            and needs_adjustment > 0
        ):
            feedback_limit = min(
                self.settings.proactive_goal_feedback_sweep_limit,
                max(
                    1,
                    needs_adjustment + int(proactive_result.get("feedback_priority_boost") or 0),
                ),
            )
            feedback_sweep_result = self.client.sweep_goals(
                limit=feedback_limit,
                verification_cooldown_minutes=self.settings.goal_verification_cooldown_minutes,
                goal_recovery_minutes=self.settings.goal_recovery_minutes,
            )
            if (
                feedback_sweep_result.get("replanned")
                or feedback_sweep_result.get("verified")
                or feedback_sweep_result.get("recovered")
            ):
                print(
                    "[agent-scheduler] feedback-driven goal sweep",
                    {
                        "needs_adjustment": needs_adjustment,
                        "feedback_limit": feedback_limit,
                        "replanned": feedback_sweep_result.get("replanned"),
                        "verified": feedback_sweep_result.get("verified"),
                        "recovered": feedback_sweep_result.get("recovered"),
                        "run_ids": feedback_sweep_result.get("run_ids"),
                    },
                )
        return {
            "dispatch": result,
            "goal_sweep": goal_result,
            "memory_boost": memory_result,
            "proactive_goals": proactive_result,
            "priority_dispatch": priority_dispatch_result,
            "feedback_sweep": feedback_sweep_result,
        }

    def run_forever(self) -> None:
        print("[agent-scheduler] started")
        try:
            while True:
                self.run_once()
                time.sleep(self.settings.poll_seconds)
        finally:
            self.close()
