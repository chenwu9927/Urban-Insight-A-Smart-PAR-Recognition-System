from __future__ import annotations

import datetime
from typing import Any

from agent.control_plane.services import compute_next_run_at, utcnow
from agent.models import AgentScheduledTask


PATROL_TEMPLATE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "Patrol: Analysis Backlog",
        "description": "Check queued/running analysis tasks for stale backlog.",
        "cron": "*/5 * * * *",
        "prompt_template": "巡检分析任务堆积情况，并识别长时间未完成的任务。",
        "risk_profile": "low",
        "config_snapshot": {
            "template_key": "analysis_backlog_patrol",
            "input_payload": {
                "action": "patrol.analysis_backlog",
                "params": {
                    "limit": 200,
                    "stale_minutes": 15,
                    "alert_threshold": 5,
                },
            },
        },
    },
    {
        "name": "Patrol: Analysis Failures",
        "description": "Check failed analysis tasks in the recent time window.",
        "cron": "*/10 * * * *",
        "prompt_template": "巡检最近失败的分析任务，并识别是否出现异常失败波动。",
        "risk_profile": "low",
        "config_snapshot": {
            "template_key": "analysis_failure_patrol",
            "input_payload": {
                "action": "patrol.analysis_failures",
                "params": {
                    "limit": 200,
                    "window_minutes": 60,
                    "alert_threshold": 3,
                },
            },
        },
    },
    {
        "name": "Patrol: Approval Timeout",
        "description": "Check pending approvals that have waited too long.",
        "cron": "*/5 * * * *",
        "prompt_template": "巡检待审批请求是否超时，避免高风险动作长期卡住。",
        "risk_profile": "low",
        "config_snapshot": {
            "template_key": "approval_timeout_patrol",
            "input_payload": {
                "action": "patrol.approval_timeout",
                "params": {
                    "limit": 200,
                    "older_than_minutes": 30,
                    "alert_threshold": 1,
                },
            },
        },
    },
]


def ensure_default_patrol_tasks(
    db,
    *,
    timezone_name: str = "Asia/Shanghai",
    owner_user_id: int | None = None,
    force_update: bool = False,
) -> tuple[list[AgentScheduledTask], list[AgentScheduledTask]]:
    created: list[AgentScheduledTask] = []
    updated: list[AgentScheduledTask] = []

    for template in PATROL_TEMPLATE_DEFINITIONS:
        task = db.query(AgentScheduledTask).filter(AgentScheduledTask.name == template["name"]).first()
        next_run_at = compute_next_run_at(
            cron_expr=template["cron"],
            timezone_name=timezone_name,
            now_utc=utcnow().replace(tzinfo=datetime.timezone.utc),
        )

        if task is None:
            task = AgentScheduledTask(
                name=template["name"],
                description=template["description"],
                enabled=True,
                reuse_session=True,
                created_by_user_id=owner_user_id,
                scope_type="system",
                scope_id="global",
                cron=template["cron"],
                timezone=timezone_name,
                prompt_template=template["prompt_template"],
                risk_profile=template["risk_profile"],
                config_snapshot=template["config_snapshot"],
                next_run_at=next_run_at,
                cooldown_minutes=0,
                dedup_window_minutes=0,
            )
            db.add(task)
            db.flush()
            created.append(task)
            continue

        if force_update:
            task.description = template["description"]
            task.enabled = True
            task.reuse_session = True
            task.scope_type = "system"
            task.scope_id = "global"
            task.cron = template["cron"]
            task.timezone = timezone_name
            task.prompt_template = template["prompt_template"]
            task.risk_profile = template["risk_profile"]
            task.config_snapshot = template["config_snapshot"]
            task.next_run_at = next_run_at
            updated.append(task)

    db.commit()
    for item in created + updated:
        db.refresh(item)
    return created, updated
