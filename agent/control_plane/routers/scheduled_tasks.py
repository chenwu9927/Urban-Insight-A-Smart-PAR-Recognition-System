from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agent.control_plane.schemas import (
    AgentScheduledTaskCreate,
    AgentScheduledTaskDispatchResponse,
    AgentScheduledTaskResponse,
    AgentScheduledTaskTriggerResponse,
    AgentScheduledTaskUpdate,
)
from agent.control_plane.services import (
    compute_next_run_at,
    create_run_from_task,
    dispatch_due_scheduled_tasks,
    utcnow,
    validate_cron,
    validate_timezone,
)
from agent.models import AgentScheduledTask
from backend.database import get_db

router = APIRouter()


@router.get("/agent/scheduled-tasks", response_model=list[AgentScheduledTaskResponse])
def list_scheduled_tasks(
    enabled: bool | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AgentScheduledTask)
    if enabled is not None:
        query = query.filter(AgentScheduledTask.enabled == enabled)
    if scope_type:
        query = query.filter(AgentScheduledTask.scope_type == scope_type)
    if scope_id:
        query = query.filter(AgentScheduledTask.scope_id == scope_id)
    return query.order_by(AgentScheduledTask.next_run_at.asc()).limit(limit).all()


@router.post("/agent/scheduled-tasks", response_model=AgentScheduledTaskResponse)
def create_scheduled_task(payload: AgentScheduledTaskCreate, db: Session = Depends(get_db)):
    cron = validate_cron(payload.cron)
    timezone_name = validate_timezone(payload.timezone)
    next_run_at = payload.next_run_at or compute_next_run_at(
        cron_expr=cron,
        timezone_name=timezone_name,
        now_utc=utcnow().replace(tzinfo=datetime.timezone.utc),
    )
    task = AgentScheduledTask(
        **payload.model_dump(exclude={"cron", "timezone", "next_run_at"}, exclude_none=True),
        cron=cron,
        timezone=timezone_name,
        next_run_at=next_run_at,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/agent/scheduled-tasks/{task_id}", response_model=AgentScheduledTaskResponse)
def get_scheduled_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(AgentScheduledTask).filter(AgentScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return task


@router.put("/agent/scheduled-tasks/{task_id}", response_model=AgentScheduledTaskResponse)
def update_scheduled_task(
    task_id: str,
    payload: AgentScheduledTaskUpdate,
    db: Session = Depends(get_db),
):
    task = db.query(AgentScheduledTask).filter(AgentScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    updates = payload.model_dump(exclude_unset=True)
    recompute_next = False
    if "cron" in updates:
        updates["cron"] = validate_cron(updates["cron"])
        recompute_next = True
    if "timezone" in updates:
        updates["timezone"] = validate_timezone(updates["timezone"])
        recompute_next = True
    if "next_run_at" in updates:
        recompute_next = False

    for field, value in updates.items():
        setattr(task, field, value)
    if recompute_next and "next_run_at" not in updates:
        task.next_run_at = compute_next_run_at(
            cron_expr=task.cron,
            timezone_name=task.timezone,
            now_utc=utcnow().replace(tzinfo=datetime.timezone.utc),
        )
    db.commit()
    db.refresh(task)
    return task


@router.delete("/agent/scheduled-tasks/{task_id}")
def delete_scheduled_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(AgentScheduledTask).filter(AgentScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    db.delete(task)
    db.commit()
    return {"ok": True}


@router.post("/agent/scheduled-tasks/{task_id}/trigger", response_model=AgentScheduledTaskTriggerResponse)
def trigger_scheduled_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(AgentScheduledTask).filter(AgentScheduledTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")

    session, _, run = create_run_from_task(db, task)
    db.commit()
    return AgentScheduledTaskTriggerResponse(task_id=task.id, session_id=session.id, run_id=run.id)


@router.post("/agent/scheduled-tasks/dispatch-due", response_model=AgentScheduledTaskDispatchResponse)
def dispatch_due(limit: int = Query(default=20, ge=1, le=200), db: Session = Depends(get_db)):
    dispatched, skipped, run_ids = dispatch_due_scheduled_tasks(db, limit=limit)
    return AgentScheduledTaskDispatchResponse(dispatched=dispatched, skipped=skipped, run_ids=run_ids)
