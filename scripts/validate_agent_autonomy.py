from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.executor.service import ApiOnlyExecutionService
from agent.memory_store import AgentMemoryStore
from agent.memory_writeback import AgentMemoryWritebackPolicy
from agent.proactive_goals import ProactiveGoalPlanner
from agent.scheduler.config import SchedulerSettings
from agent.scheduler.worker import AgentScheduler


def validate_strategy_feedback_writeback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        memory = AgentMemoryStore(tmp)
        policy = AgentMemoryWritebackPolicy(memory)
        artifacts = policy.apply(
            action="agent.chat",
            params={"question": "Please remember that approval backlog must stay under 15 minutes."},
            output_payload={
                "question": "Please remember that approval backlog must stay under 15 minutes.",
                "answer": "Understood. I will keep approval backlog under 15 minutes.",
                "planned_steps": [],
                "strategic_context": {
                    "priority_tier": "elevated",
                    "verification_mode": "strict",
                    "strategy_summary": "Approval latency remains a recurring risk.",
                    "strategy_directives": ["Keep approval backlog under 15 minutes"],
                    "risk_clusters": [
                        {
                            "label": "approval latency",
                            "summary": "Approvals continue to stall during peak periods.",
                            "severity": "high",
                            "recommended_strategy": "tighten approval turnaround monitoring",
                        }
                    ],
                },
                "tool_events": [],
            },
            result_summary="Approval latency strategy validated successfully.",
            session_id="session-feedback",
            run_id="run-feedback",
        )
        assert artifacts["daily_note_path"], artifacts
        assert artifacts["strategy_note_path"], artifacts
        assert artifacts["strategy_feedback_status"] == "validated", artifacts


def validate_feedback_aware_proactive_planning() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        memory = AgentMemoryStore(tmp)
        memory.write_long_term(
            "# Long-term Memory\n\n"
            "- Goal: Reduce recurring approval timeouts\n"
            "- Long-term goal: Keep approval backlog under 15 minutes\n"
        )
        memory.append_daily_note(
            "Status: needs_adjustment\n\n"
            "Strategy directives:\n"
            "- Keep approval backlog under 15 minutes\n\n"
            "Risk clusters:\n"
            "- [high] approval latency: approvals continue to stall during peak periods\n\n"
            "Feedback summary:\n"
            "Repeated approval delays still require adjustment.",
            heading="strategy feedback | run=phase14",
        )
        planner = ProactiveGoalPlanner(tmp)
        batch = planner.extract_candidate_batch(use_llm_distillation=False)
        assert batch.candidates, batch
        assert batch.strategy_feedback_summary, batch
        assert batch.feedback_status_counts.get("needs_adjustment") == 1, batch.feedback_status_counts
        assert batch.feedback_priority_boost >= 1, batch.feedback_priority_boost
        assert batch.priority_tier in {"elevated", "urgent"}, batch.priority_tier


def validate_executor_context_merge() -> None:
    service = ApiOnlyExecutionService()
    try:
        merged = service._merge_strategic_context(
            [
                {
                    "strategy_summary": "Current strategy summary",
                    "strategy_feedback_summary": "Recent strategy feedback indicates recurring adjustment pressure.",
                    "feedback_status_counts": {"needs_adjustment": 2},
                    "priority_tier": "elevated",
                },
                {
                    "strategy_directives": ["Tighten approval latency monitoring"],
                    "risk_clusters": [{"label": "approval latency", "summary": "Delayed approvals", "severity": "high"}],
                    "feedback_status_counts": {"adapted": 1},
                },
            ]
        )
        assert merged["strategy_feedback_summary"], merged
        assert merged["feedback_status_counts"]["needs_adjustment"] == 2, merged
        assert merged["feedback_status_counts"]["adapted"] == 1, merged
    finally:
        service.close()


def validate_feedback_driven_scheduler() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.sweep_calls: list[int] = []

        def dispatch_due(self, *, limit: int) -> dict:
            return {"dispatched": 0, "skipped": 0, "run_ids": []}

        def sweep_goals(self, *, limit: int, verification_cooldown_minutes: int, goal_recovery_minutes: int) -> dict:
            self.sweep_calls.append(limit)
            return {
                "inspected": limit,
                "synced": limit,
                "replanned": 1 if len(self.sweep_calls) > 1 else 0,
                "verified": 0,
                "recovered": 0,
                "run_ids": ["feedback-run"] if len(self.sweep_calls) > 1 else [],
            }

        def boost_patrols_from_memory(self, *, lookback_days: int, boost_cooldown_minutes: int) -> dict:
            return {"scanned": 0, "triggered": 0, "run_ids": [], "task_ids": []}

        def create_proactive_goals_from_memory(self, **kwargs) -> dict:
            return {
                "created": 0,
                "candidates": 1,
                "rule_candidates": 1,
                "llm_candidates": 0,
                "llm_distillation_used": False,
                "priority_tier": "normal",
                "priority_boost": 0,
                "feedback_priority_boost": 1,
                "feedback_status_counts": {"needs_adjustment": 2},
                "risk_clusters": [],
                "goal_ids": [],
                "run_ids": [],
            }

        def close(self) -> None:
            pass

    settings = SchedulerSettings()
    settings.proactive_goal_feedback_sweep_enabled = True
    settings.proactive_goal_feedback_sweep_limit = 5
    scheduler = AgentScheduler(settings)
    scheduler.client = FakeClient()
    result = scheduler.run_once()
    assert result["feedback_sweep"]["replanned"] == 1, result
    assert scheduler.client.sweep_calls == [settings.goal_sweep_limit, 3], scheduler.client.sweep_calls


def main() -> None:
    validate_strategy_feedback_writeback()
    validate_feedback_aware_proactive_planning()
    validate_executor_context_merge()
    validate_feedback_driven_scheduler()
    print("[ok] agent autonomy validation passed")


if __name__ == "__main__":
    main()
