from __future__ import annotations

import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from agent.control_plane.services import create_run_from_task, utcnow
from agent.memory_store import AgentMemoryStore
from agent.models import AgentRun, AgentScheduledTask


ACTIVE_RUN_STATUSES = {"queued", "claimed", "running", "waiting_approval", "waiting_input", "replanning"}


class MemoryDrivenPatrolPriority:
    KEYWORD_TASK_MAP = (
        ("analysis backlog alert", "Patrol: Analysis Backlog"),
        ("analysis failure alert", "Patrol: Analysis Failures"),
        ("approval timeout alert", "Patrol: Approval Timeout"),
    )

    def __init__(self, workspace_dir: str | Path) -> None:
        self.memory = AgentMemoryStore(workspace_dir)

    def trigger_boosts(
        self,
        db: Session,
        *,
        lookback_days: int = 2,
        boost_cooldown_minutes: int = 30,
    ) -> dict[str, object]:
        context = self.memory.get_recent_daily_notes(days=lookback_days).lower()
        if not context.strip():
            return {"scanned": 0, "triggered": 0, "run_ids": [], "task_ids": []}

        run_ids: list[str] = []
        task_ids: list[str] = []
        scanned = 0

        for keyword, task_name in self.KEYWORD_TASK_MAP:
            if keyword not in context:
                continue
            task = db.query(AgentScheduledTask).filter(AgentScheduledTask.name == task_name, AgentScheduledTask.enabled == True).first()  # noqa: E712
            if task is None:
                continue
            scanned += 1
            if self._is_recently_boosted(task, cooldown_minutes=boost_cooldown_minutes):
                continue
            existing = (
                db.query(AgentRun)
                .filter(AgentRun.scheduled_task_id == task.id, AgentRun.status.in_(ACTIVE_RUN_STATUSES))
                .order_by(AgentRun.created_at.desc())
                .first()
            )
            if existing is not None:
                continue
            session, _, run = create_run_from_task(db, task)
            config_snapshot = dict(task.config_snapshot or {})
            config_snapshot["last_memory_boost_at"] = utcnow().isoformat()
            config_snapshot["last_memory_boost_reason"] = keyword
            task.config_snapshot = config_snapshot
            session.last_run_at = run.scheduled_at
            run_ids.append(run.id)
            task_ids.append(task.id)

        return {
            "scanned": scanned,
            "triggered": len(run_ids),
            "run_ids": run_ids,
            "task_ids": task_ids,
        }

    @staticmethod
    def _is_recently_boosted(task: AgentScheduledTask, *, cooldown_minutes: int) -> bool:
        config_snapshot = task.config_snapshot or {}
        raw = config_snapshot.get("last_memory_boost_at")
        if not isinstance(raw, str) or not raw.strip():
            return False
        try:
            value = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if value.tzinfo is not None:
                value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        except ValueError:
            return False
        return (utcnow() - value).total_seconds() < max(60, cooldown_minutes * 60)
