from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from sqlalchemy.orm import Session

from agent.models import AgentMessage, AgentRun, AgentScheduledTask, AgentSession


def utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


def validate_cron(expr: str) -> str:
    value = (expr or "").strip()
    if not value:
        raise ValueError("cron cannot be empty")
    if not croniter.is_valid(value):
        raise ValueError(f"invalid cron expression: {value}")
    return value


def validate_timezone(tz_name: str | None) -> str:
    value = (tz_name or "").strip() or "Asia/Shanghai"
    ZoneInfo(value)
    return value


def compute_next_run_at(
    *,
    cron_expr: str,
    timezone_name: str,
    now_utc: datetime.datetime | None = None,
) -> datetime.datetime:
    now_utc = now_utc or utcnow()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=datetime.timezone.utc)
    tz = ZoneInfo(validate_timezone(timezone_name))
    base = now_utc.astimezone(tz)
    next_local = croniter(validate_cron(cron_expr), base).get_next(datetime.datetime)
    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=tz)
    return next_local.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def create_message(
    db: Session,
    *,
    session_id: str,
    role: str,
    content: dict,
    run_id: str | None = None,
    text_preview: str | None = None,
    connector: str | None = None,
    connector_message_id: str | None = None,
    thread_key: str | None = None,
) -> AgentMessage:
    message = AgentMessage(
        session_id=session_id,
        run_id=run_id,
        role=role,
        content=content,
        text_preview=text_preview,
        connector=connector,
        connector_message_id=connector_message_id,
        thread_key=thread_key,
    )
    db.add(message)
    db.flush()
    return message


def create_run(
    db: Session,
    *,
    session_id: str,
    trigger_message_id: str | None = None,
    scheduled_task_id: str | None = None,
    created_by_user_id: int | None = None,
    schedule_mode: str = "immediate",
    permission_mode: str = "default",
    config_snapshot: dict | None = None,
    input_payload: dict | None = None,
    scheduled_at: datetime.datetime | None = None,
) -> AgentRun:
    run = AgentRun(
        session_id=session_id,
        trigger_message_id=trigger_message_id,
        scheduled_task_id=scheduled_task_id,
        created_by_user_id=created_by_user_id,
        schedule_mode=schedule_mode,
        permission_mode=permission_mode,
        config_snapshot=config_snapshot,
        input_payload=input_payload,
        scheduled_at=scheduled_at or utcnow(),
    )
    db.add(run)
    db.flush()
    return run


def ensure_task_session(db: Session, task: AgentScheduledTask) -> AgentSession:
    if task.session_id:
        session = db.query(AgentSession).filter(AgentSession.id == task.session_id).first()
        if session:
            return session

    session = AgentSession(
        kind="patrol",
        title=task.name,
        status="active",
        owner_user_id=task.created_by_user_id,
        source="scheduled_task",
        site_id=task.scope_id if task.scope_type == "site" else None,
        camera_id=task.scope_id if task.scope_type == "camera" else None,
        config_snapshot=task.config_snapshot,
    )
    db.add(session)
    db.flush()
    task.session_id = session.id
    return session


def create_ephemeral_task_session(db: Session, task: AgentScheduledTask) -> AgentSession:
    session = AgentSession(
        kind="patrol",
        title=task.name,
        status="active",
        owner_user_id=task.created_by_user_id,
        source="scheduled_task",
        site_id=task.scope_id if task.scope_type == "site" else None,
        camera_id=task.scope_id if task.scope_type == "camera" else None,
        config_snapshot=task.config_snapshot,
    )
    db.add(session)
    db.flush()
    return session


def create_run_from_task(db: Session, task: AgentScheduledTask) -> tuple[AgentSession, AgentMessage, AgentRun]:
    session = ensure_task_session(db, task) if task.reuse_session else create_ephemeral_task_session(db, task)
    message = create_message(
        db,
        session_id=session.id,
        role="user",
        content={"text": task.prompt_template},
        text_preview=task.prompt_template[:500],
    )
    input_payload = {"scheduled_task_id": task.id}
    config_snapshot = dict(task.config_snapshot or {})
    if isinstance(config_snapshot.get("input_payload"), dict):
        merged_payload = dict(config_snapshot.get("input_payload") or {})
        merged_payload["scheduled_task_id"] = task.id
        input_payload = merged_payload
    run = create_run(
        db,
        session_id=session.id,
        trigger_message_id=message.id,
        scheduled_task_id=task.id,
        created_by_user_id=task.created_by_user_id,
        schedule_mode="scheduled",
        config_snapshot=config_snapshot or None,
        input_payload=input_payload,
        scheduled_at=utcnow(),
    )
    task.last_run_id = run.id
    task.last_run_status = run.status
    task.last_error = None
    session.last_run_at = run.scheduled_at
    return session, message, run


def dispatch_due_scheduled_tasks(
    db: Session,
    *,
    limit: int = 20,
    now_utc: datetime.datetime | None = None,
) -> tuple[int, int, list[str]]:
    now_utc = now_utc or utcnow()
    due_tasks = (
        db.query(AgentScheduledTask)
        .filter(
            AgentScheduledTask.enabled == True,  # noqa: E712
            AgentScheduledTask.next_run_at <= now_utc,
        )
        .order_by(AgentScheduledTask.next_run_at.asc())
        .limit(limit)
        .all()
    )

    dispatched = 0
    skipped = 0
    run_ids: list[str] = []

    active_statuses = ["queued", "claimed", "running", "waiting_approval", "waiting_input"]

    for task in due_tasks:
        existing_run = (
            db.query(AgentRun)
            .filter(
                AgentRun.scheduled_task_id == task.id,
                AgentRun.status.in_(active_statuses),
            )
            .order_by(AgentRun.created_at.desc())
            .first()
        )
        if existing_run:
            skipped += 1
            task.next_run_at = compute_next_run_at(
                cron_expr=task.cron,
                timezone_name=task.timezone,
                now_utc=now_utc.replace(tzinfo=datetime.timezone.utc),
            )
            continue

        _, _, run = create_run_from_task(db, task)
        task.next_run_at = compute_next_run_at(
            cron_expr=task.cron,
            timezone_name=task.timezone,
            now_utc=now_utc.replace(tzinfo=datetime.timezone.utc),
        )
        dispatched += 1
        run_ids.append(run.id)

    db.commit()
    return dispatched, skipped, run_ids
