from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from sqlalchemy.orm import Session

from agent.models import AgentDedupEvent, AgentGoal, AgentMessage, AgentRun, AgentScheduledTask, AgentSession


ACTIVE_RUN_STATUSES = {"queued", "claimed", "running", "waiting_approval", "waiting_input", "replanning"}
GOAL_ACTIVE_STATUSES = {"planned", "running", "replanning", "blocked", "pending_verification", "verifying", "recovering"}


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
    session = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if session is not None:
        session.updated_at = utcnow()
    return message


def create_run(
    db: Session,
    *,
    session_id: str,
    trigger_message_id: str | None = None,
    scheduled_task_id: str | None = None,
    parent_run_id: str | None = None,
    goal_key: str | None = None,
    step_index: int | None = None,
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
        parent_run_id=parent_run_id,
        goal_key=goal_key,
        step_index=step_index,
        created_by_user_id=created_by_user_id,
        schedule_mode=schedule_mode,
        permission_mode=permission_mode,
        config_snapshot=config_snapshot,
        input_payload=input_payload,
        scheduled_at=scheduled_at or utcnow(),
    )
    db.add(run)
    db.flush()
    session = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    if session is not None:
        session.last_run_at = run.scheduled_at
        session.updated_at = utcnow()
    return run


def ensure_goal(
    db: Session,
    *,
    root_run: AgentRun,
    title: str | None = None,
    summary: str | None = None,
    auto_replan: bool = True,
    meta: dict | None = None,
) -> AgentGoal:
    goal_key = str(root_run.goal_key or root_run.id)
    goal = db.query(AgentGoal).filter(AgentGoal.id == goal_key).first()
    if goal is None:
        goal = AgentGoal(
            id=goal_key,
            session_id=root_run.session_id,
            root_run_id=root_run.id,
            latest_run_id=root_run.id,
            title=title,
            summary=summary,
            status="planned",
            auto_replan=auto_replan,
            last_planned_at=utcnow(),
            meta=meta or {},
        )
        db.add(goal)
    else:
        goal.latest_run_id = root_run.id
        if title:
            goal.title = title
        if summary:
            goal.summary = summary
        goal.auto_replan = auto_replan
        if meta:
            merged = dict(goal.meta or {})
            merged.update(meta)
            goal.meta = merged
        goal.last_planned_at = utcnow()

    root_run.goal_key = goal_key
    db.flush()
    return goal


def _next_goal_step_index(db: Session, *, goal_key: str) -> int:
    current_max_step = (
        db.query(AgentRun.step_index)
        .filter(AgentRun.goal_key == goal_key, AgentRun.step_index != None)  # noqa: E711
        .order_by(AgentRun.step_index.desc())
        .first()
    )
    return int(current_max_step[0]) + 1 if current_max_step and current_max_step[0] is not None else 1


def _parse_meta_datetime(meta: dict | None, key: str) -> datetime.datetime | None:
    if not isinstance(meta, dict):
        return None
    raw = meta.get(key)
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is not None:
            value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value
    except ValueError:
        return None


def _set_meta_datetime(meta: dict | None, key: str, value: datetime.datetime | None) -> dict:
    updated = dict(meta or {})
    if value is None:
        updated.pop(key, None)
    else:
        updated[key] = value.isoformat()
    return updated


def register_dedup_event(
    db: Session,
    *,
    dedup_key: str | None,
    category: str,
    scope: str | None,
    payload: dict | None,
    ttl_seconds: int = 600,
) -> bool:
    key = str(dedup_key or "").strip()
    if not key:
        return True

    now = utcnow()
    expires_at = now + datetime.timedelta(seconds=max(30, int(ttl_seconds)))
    existing = db.query(AgentDedupEvent).filter(AgentDedupEvent.key == key).first()
    if existing and (existing.expires_at is None or existing.expires_at > now):
        return False
    if existing is None:
        existing = AgentDedupEvent(key=key, category=category)
        db.add(existing)
    existing.category = category
    existing.scope = scope
    existing.payload = payload
    existing.expires_at = expires_at
    db.flush()
    return True


def create_follow_up_runs(
    db: Session,
    *,
    parent_run: AgentRun,
    steps: list[dict],
    goal_summary: str | None = None,
    auto_replan: bool = True,
) -> list[AgentRun]:
    if not steps:
        return []

    goal = ensure_goal(
        db,
        root_run=parent_run,
        title=(parent_run.result_summary or parent_run.id)[:255] if parent_run.result_summary else parent_run.id,
        summary=goal_summary,
        auto_replan=auto_replan,
        meta={"planned_step_count": len(steps)},
    )
    goal_key = goal.id
    next_step_index = _next_goal_step_index(db, goal_key=goal_key)

    created_runs: list[AgentRun] = []
    for offset, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").strip()
        if not action:
            continue

        title = str(step.get("title") or action).strip()
        rationale = str(step.get("rationale") or "").strip()
        text_lines = [f"Planned follow-up: {title}", f"Action: {action}"]
        if rationale:
            text_lines.append(f"Rationale: {rationale}")
        trigger_message = create_message(
            db,
            session_id=parent_run.session_id,
            role="system",
            content={
                "text": "\n".join(text_lines),
                "planned_step": step,
                "parent_run_id": parent_run.id,
                "goal_key": goal_key,
            },
            text_preview=title[:500],
        )

        input_payload = {
            "action": action,
            "params": step.get("params") if isinstance(step.get("params"), dict) else {},
            "goal_key": goal_key,
            "step_title": title,
            "step_rationale": rationale,
        }
        created_runs.append(
            create_run(
                db,
                session_id=parent_run.session_id,
                trigger_message_id=trigger_message.id,
                parent_run_id=parent_run.id,
                goal_key=goal_key,
                step_index=next_step_index + offset,
                created_by_user_id=parent_run.created_by_user_id,
                schedule_mode="immediate",
                permission_mode=parent_run.permission_mode,
                config_snapshot={"planned_from_run_id": parent_run.id, "goal_key": goal_key},
                input_payload=input_payload,
                scheduled_at=utcnow(),
            )
        )

    return created_runs


def create_replan_run(
    db: Session,
    *,
    failed_run: AgentRun,
    error_message: str,
) -> AgentRun | None:
    goal_key = str(failed_run.goal_key or "").strip()
    if not goal_key:
        return None

    goal = db.query(AgentGoal).filter(AgentGoal.id == goal_key).first()
    if goal is None or not goal.auto_replan:
        return None

    existing = (
        db.query(AgentRun)
        .filter(
            AgentRun.parent_run_id == failed_run.id,
            AgentRun.schedule_mode == "replan",
        )
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    if existing is not None:
        return existing

    next_step_index = _next_goal_step_index(db, goal_key=goal_key)

    prompt = (
        "A goal step failed. Re-evaluate the current goal, summarize the failure, and decide the next safe follow-up steps.\n\n"
        f"Failed action: {((failed_run.input_payload or {}).get('action') or 'unknown')}\n"
        f"Error: {error_message.strip()}\n"
        f"Goal key: {goal_key}"
    ).strip()
    message = create_message(
        db,
        session_id=failed_run.session_id,
        role="system",
        content={
            "text": prompt,
            "goal_key": goal_key,
            "replan_of_run_id": failed_run.id,
        },
        text_preview=prompt[:500],
    )
    run = create_run(
        db,
        session_id=failed_run.session_id,
        trigger_message_id=message.id,
        parent_run_id=failed_run.id,
        goal_key=goal_key,
        step_index=next_step_index,
        created_by_user_id=failed_run.created_by_user_id,
        schedule_mode="replan",
        permission_mode=failed_run.permission_mode,
        config_snapshot={"auto_replan": True, "replan_of_run_id": failed_run.id},
        input_payload={
            "action": "agent.chat",
            "params": {
                "question": prompt,
                "auto_plan": True,
            },
            "goal_key": goal_key,
            "replan_of_run_id": failed_run.id,
            "auto_dispatch_followups": True,
        },
        scheduled_at=utcnow(),
    )
    goal.status = "replanning"
    goal.latest_run_id = run.id
    goal.last_error = error_message
    goal.last_replanned_at = utcnow()
    db.flush()
    return run


def create_goal_verification_run(db: Session, *, goal: AgentGoal) -> AgentRun | None:
    existing = (
        db.query(AgentRun)
        .filter(
            AgentRun.goal_key == goal.id,
            AgentRun.schedule_mode == "verification",
            AgentRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    if existing is not None:
        return existing

    prompt = (
        "Verify whether the current goal is actually complete. "
        "If the goal is complete, explain why and return no further steps. "
        "If the goal is not complete, propose the next safe follow-up steps.\n\n"
        f"Goal: {goal.summary or goal.title or goal.id}\n"
        f"Goal key: {goal.id}\n"
        f"Completed steps: {goal.completed_steps}/{goal.step_count}"
    ).strip()
    message = create_message(
        db,
        session_id=goal.session_id,
        role="system",
        content={"text": prompt, "goal_key": goal.id, "verification": True},
        text_preview=prompt[:500],
    )
    run = create_run(
        db,
        session_id=goal.session_id,
        trigger_message_id=message.id,
        parent_run_id=goal.latest_run_id,
        goal_key=goal.id,
        step_index=_next_goal_step_index(db, goal_key=goal.id),
        schedule_mode="verification",
        config_snapshot={"goal_verification": True},
        input_payload={
            "action": "agent.chat",
            "params": {"question": prompt, "auto_plan": True},
            "goal_key": goal.id,
            "auto_dispatch_followups": True,
            "goal_verification": True,
        },
        scheduled_at=utcnow(),
    )
    goal.latest_run_id = run.id
    goal.status = "verifying"
    goal.meta = _set_meta_datetime(goal.meta, "last_verification_requested_at", utcnow())
    db.flush()
    return run


def create_goal_recovery_run(db: Session, *, goal: AgentGoal) -> AgentRun | None:
    existing = (
        db.query(AgentRun)
        .filter(
            AgentRun.goal_key == goal.id,
            AgentRun.schedule_mode == "goal_recovery",
            AgentRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(AgentRun.created_at.desc())
        .first()
    )
    if existing is not None:
        return existing

    prompt = (
        "Resume the long-running goal using current workspace memory and recent goal history. "
        "Summarize what is still unresolved, then decide the next safe steps.\n\n"
        f"Goal: {goal.summary or goal.title or goal.id}\n"
        f"Goal key: {goal.id}\n"
        f"Status: {goal.status}\n"
        f"Last error: {goal.last_error or '--'}"
    ).strip()
    message = create_message(
        db,
        session_id=goal.session_id,
        role="system",
        content={"text": prompt, "goal_key": goal.id, "goal_recovery": True},
        text_preview=prompt[:500],
    )
    run = create_run(
        db,
        session_id=goal.session_id,
        trigger_message_id=message.id,
        parent_run_id=goal.latest_run_id,
        goal_key=goal.id,
        step_index=_next_goal_step_index(db, goal_key=goal.id),
        schedule_mode="goal_recovery",
        config_snapshot={"goal_recovery": True},
        input_payload={
            "action": "agent.chat",
            "params": {"question": prompt, "auto_plan": True},
            "goal_key": goal.id,
            "auto_dispatch_followups": True,
            "goal_recovery": True,
        },
        scheduled_at=utcnow(),
    )
    goal.latest_run_id = run.id
    goal.status = "recovering"
    goal.meta = _set_meta_datetime(goal.meta, "last_recovery_requested_at", utcnow())
    db.flush()
    return run


def ingest_event(
    db: Session,
    *,
    event_type: str,
    summary: str,
    payload: dict | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    session_id: str | None = None,
    goal_id: str | None = None,
    dedup_key: str | None = None,
    ttl_seconds: int = 600,
) -> tuple[AgentSession | None, AgentRun | None, AgentGoal | None, bool]:
    deduped = not register_dedup_event(
        db,
        dedup_key=dedup_key,
        category="agent_event",
        scope=scope_id or scope_type,
        payload=payload,
        ttl_seconds=ttl_seconds,
    )

    goal = None
    session = None
    if goal_id:
        goal = db.query(AgentGoal).filter(AgentGoal.id == goal_id).first()
        if goal is None:
            raise ValueError(f"Goal not found: {goal_id}")
        session = db.query(AgentSession).filter(AgentSession.id == goal.session_id).first()
    elif session_id:
        session = db.query(AgentSession).filter(AgentSession.id == session_id, AgentSession.is_deleted == False).first()  # noqa: E712
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

    if deduped:
        return session, None, goal, True

    if session is None:
        session = AgentSession(
            kind="event",
            title=summary[:255],
            status="active",
            source="event",
            site_id=scope_id if scope_type == "site" else None,
            camera_id=scope_id if scope_type == "camera" else None,
            state_patch={"event_type": event_type},
        )
        db.add(session)
        db.flush()

    prompt = (
        f"New event received: {event_type}\n"
        f"Summary: {summary.strip()}\n"
        "Assess operational impact, update the current goal if there is one, and decide the next safe steps."
    ).strip()
    message = create_message(
        db,
        session_id=session.id,
        role="system",
        content={
            "text": prompt,
            "event_type": event_type,
            "summary": summary,
            "payload": payload,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "goal_id": goal.id if goal else None,
        },
        text_preview=summary[:500],
    )
    goal_key = goal.id if goal is not None else None
    run = create_run(
        db,
        session_id=session.id,
        trigger_message_id=message.id,
        parent_run_id=goal.latest_run_id if goal is not None else None,
        goal_key=goal_key,
        step_index=_next_goal_step_index(db, goal_key=goal_key) if goal_key else None,
        schedule_mode="event",
        input_payload={
            "action": "agent.chat",
            "params": {"question": prompt, "auto_plan": True},
            "event_type": event_type,
            "event_payload": payload or {},
            "goal_key": goal_key,
            "auto_dispatch_followups": True,
        },
        scheduled_at=utcnow(),
    )
    if goal is not None:
        goal.latest_run_id = run.id
        goal.status = "running"
    db.flush()
    return session, run, goal, deduped


def sync_goal_state(db: Session, goal_key: str) -> AgentGoal | None:
    goal = db.query(AgentGoal).filter(AgentGoal.id == goal_key).first()
    if goal is None:
        return None

    runs = (
        db.query(AgentRun)
        .filter(AgentRun.goal_key == goal_key)
        .order_by(AgentRun.created_at.asc())
        .all()
    )
    if not runs:
        return goal

    child_runs = [run for run in runs if run.step_index is not None]
    active_steps = sum(1 for run in child_runs if run.status in ACTIVE_RUN_STATUSES)
    completed_steps = sum(1 for run in child_runs if run.status == "completed")
    failed_steps = sum(1 for run in child_runs if run.status == "failed")
    active_replans = any(run.status in ACTIVE_RUN_STATUSES and run.schedule_mode == "replan" for run in child_runs)
    active_verifications = any(run.status in ACTIVE_RUN_STATUSES and run.schedule_mode == "verification" for run in child_runs)
    active_recoveries = any(run.status in ACTIVE_RUN_STATUSES and run.schedule_mode == "goal_recovery" for run in child_runs)
    verified_at = _parse_meta_datetime(goal.meta, "verified_at")
    goal.step_count = len(child_runs)
    goal.active_steps = active_steps
    goal.completed_steps = completed_steps
    goal.failed_steps = failed_steps
    goal.latest_run_id = runs[-1].id

    root_run = next((run for run in runs if run.id == goal.root_run_id), runs[0])
    if active_replans:
        goal.status = "replanning"
    elif active_recoveries:
        goal.status = "recovering"
    elif active_verifications:
        goal.status = "verifying"
    elif active_steps > 0:
        goal.status = "running"
    elif failed_steps > 0:
        goal.status = "blocked"
    elif goal.step_count > 0 and completed_steps >= goal.step_count and root_run.status == "completed" and verified_at is None:
        goal.status = "pending_verification"
    elif goal.step_count > 0 and completed_steps >= goal.step_count and root_run.status == "completed":
        goal.status = "completed"
    elif root_run.status == "failed":
        goal.status = "failed"
    elif goal.step_count > 0:
        goal.status = "planned"
    else:
        goal.status = "planned"

    latest_failed = next((run for run in reversed(runs) if run.status == "failed" and run.last_error), None)
    goal.last_error = latest_failed.last_error if latest_failed is not None else None
    db.flush()
    return goal


def sweep_goals(
    db: Session,
    *,
    limit: int = 20,
    verification_cooldown_minutes: int = 10,
    goal_recovery_minutes: int = 180,
    goal_memory=None,
) -> dict[str, object]:
    goals = (
        db.query(AgentGoal)
        .filter(AgentGoal.status.in_(GOAL_ACTIVE_STATUSES))
        .order_by(AgentGoal.updated_at.asc(), AgentGoal.created_at.asc())
        .limit(limit)
        .all()
    )
    run_ids: list[str] = []
    synced = 0
    replanned = 0
    verified = 0
    recovered = 0

    for goal in goals:
        synced_goal = sync_goal_state(db, goal.id)
        synced += 1
        if synced_goal is None:
            continue

        if synced_goal.status == "blocked" and synced_goal.auto_replan:
            latest_failed = (
                db.query(AgentRun)
                .filter(AgentRun.goal_key == goal.id, AgentRun.status == "failed")
                .order_by(AgentRun.finished_at.desc(), AgentRun.created_at.desc())
                .first()
            )
            if latest_failed is not None:
                replan_run = create_replan_run(db, failed_run=latest_failed, error_message=latest_failed.last_error or "step failed")
                if replan_run is not None:
                    if goal_memory is not None:
                        goal_memory.record_goal_snapshot(synced_goal, reason="replanned")
                    replanned += 1
                    run_ids.append(replan_run.id)
                    continue

        if synced_goal.status == "pending_verification":
            last_requested = _parse_meta_datetime(synced_goal.meta, "last_verification_requested_at")
            now = utcnow()
            if last_requested is None or (now - last_requested).total_seconds() >= verification_cooldown_minutes * 60:
                verification_run = create_goal_verification_run(db, goal=synced_goal)
                if verification_run is not None:
                    if goal_memory is not None:
                        goal_memory.record_goal_snapshot(synced_goal, reason="verification")
                    verified += 1
                    run_ids.append(verification_run.id)
                    continue

        if synced_goal.status in {"planned", "running", "blocked"}:
            last_recovery = _parse_meta_datetime(synced_goal.meta, "last_recovery_requested_at")
            age_minutes = int((utcnow() - synced_goal.updated_at).total_seconds() // 60)
            if age_minutes >= max(15, goal_recovery_minutes) and (
                last_recovery is None or (utcnow() - last_recovery).total_seconds() >= goal_recovery_minutes * 60
            ):
                recovery_run = create_goal_recovery_run(db, goal=synced_goal)
                if recovery_run is not None:
                    if goal_memory is not None:
                        goal_memory.record_goal_snapshot(synced_goal, reason="recovery")
                        if age_minutes >= 24 * 60:
                            goal_memory.promote_persistent_goal(synced_goal)
                    recovered += 1
                    run_ids.append(recovery_run.id)

    db.flush()
    return {
        "inspected": len(goals),
        "synced": synced,
        "replanned": replanned,
        "verified": verified,
        "recovered": recovered,
        "run_ids": run_ids,
    }


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
