from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from agent.control_plane.schemas import (
    AgentMessageResponse,
    AgentRunClaimRequest,
    AgentRunClaimResponse,
    AgentRunCompleteRequest,
    AgentRunCreate,
    AgentRunFailRequest,
    AgentRunHeartbeatRequest,
    AgentRunResponse,
    AgentSessionResponse,
)
from agent.control_plane.services import create_message, create_run, utcnow
from agent.models import AgentMessage, AgentRun, AgentSession
from backend.database import get_db

router = APIRouter()


@router.get("/agent/runs", response_model=list[AgentRunResponse])
def list_runs(
    status: str | None = None,
    session_id: str | None = None,
    schedule_mode: str | None = None,
    claimed_by: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AgentRun)
    if status:
        query = query.filter(AgentRun.status == status)
    if session_id:
        query = query.filter(AgentRun.session_id == session_id)
    if schedule_mode:
        query = query.filter(AgentRun.schedule_mode == schedule_mode)
    if claimed_by:
        query = query.filter(AgentRun.claimed_by == claimed_by)
    return query.order_by(AgentRun.created_at.desc()).limit(limit).all()


@router.post("/agent/runs", response_model=AgentRunResponse)
def create_agent_run(payload: AgentRunCreate, db: Session = Depends(get_db)):
    session = (
        db.query(AgentSession)
        .filter(AgentSession.id == payload.session_id, AgentSession.is_deleted == False)  # noqa: E712
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Agent session not found")

    trigger_message_id = payload.trigger_message_id
    if payload.prompt and not trigger_message_id:
        message = create_message(
            db,
            session_id=session.id,
            role="user",
            content={"text": payload.prompt},
            text_preview=payload.prompt[:500],
        )
        trigger_message_id = message.id

    run = create_run(
        db,
        session_id=session.id,
        trigger_message_id=trigger_message_id,
        created_by_user_id=payload.created_by_user_id,
        schedule_mode=payload.schedule_mode,
        permission_mode=payload.permission_mode,
        config_snapshot=payload.config_snapshot,
        input_payload=payload.input_payload,
        scheduled_at=payload.scheduled_at,
    )
    db.commit()
    db.refresh(run)
    return run


@router.get("/agent/runs/{run_id}", response_model=AgentRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@router.post("/agent/runs/claim", response_model=AgentRunClaimResponse)
def claim_run(payload: AgentRunClaimRequest, db: Session = Depends(get_db)):
    now = utcnow()
    lease_until = now + datetime.timedelta(seconds=max(5, payload.lease_seconds))

    query = db.query(AgentRun).filter(
        or_(
            AgentRun.status == "queued",
            (AgentRun.status == "claimed") & (AgentRun.lease_expires_at != None) & (AgentRun.lease_expires_at < now),  # noqa: E711
        )
    )
    if payload.schedule_modes:
        query = query.filter(AgentRun.schedule_mode.in_(payload.schedule_modes))

    run = query.order_by(AgentRun.scheduled_at.asc(), AgentRun.created_at.asc()).first()
    if not run:
        return AgentRunClaimResponse(claimed=False, run=None, trigger_message=None, session=None)

    run.status = "claimed"
    run.claimed_by = payload.worker_id
    run.lease_expires_at = lease_until
    run.last_heartbeat_at = now
    run.attempts = int(run.attempts or 0) + 1
    if run.started_at is None:
        run.started_at = now

    session = db.query(AgentSession).filter(AgentSession.id == run.session_id).first()
    trigger_message = None
    if run.trigger_message_id:
        trigger_message = db.query(AgentMessage).filter(AgentMessage.id == run.trigger_message_id).first()

    db.commit()
    db.refresh(run)
    if session:
        db.refresh(session)
    if trigger_message:
        db.refresh(trigger_message)

    return AgentRunClaimResponse(
        claimed=True,
        run=AgentRunResponse.model_validate(run),
        trigger_message=AgentMessageResponse.model_validate(trigger_message) if trigger_message else None,
        session=AgentSessionResponse.model_validate(session) if session else None,
    )


@router.post("/agent/runs/{run_id}/heartbeat", response_model=AgentRunResponse)
def heartbeat_run(
    run_id: str,
    payload: AgentRunHeartbeatRequest,
    db: Session = Depends(get_db),
):
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    if run.claimed_by and run.claimed_by != payload.worker_id:
        raise HTTPException(status_code=409, detail="Run is claimed by another worker")

    run.status = "running"
    run.claimed_by = payload.worker_id
    run.last_heartbeat_at = utcnow()
    run.lease_expires_at = utcnow() + datetime.timedelta(seconds=max(5, payload.lease_seconds))
    if payload.progress is not None:
        run.progress = max(0, min(100, payload.progress))
    db.commit()
    db.refresh(run)
    return run


@router.post("/agent/runs/{run_id}/complete", response_model=AgentRunResponse)
def complete_run(
    run_id: str,
    payload: AgentRunCompleteRequest,
    db: Session = Depends(get_db),
):
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    if payload.worker_id and run.claimed_by and run.claimed_by != payload.worker_id:
        raise HTTPException(status_code=409, detail="Run is claimed by another worker")

    run.status = "completed"
    run.progress = 100
    run.output_payload = payload.output_payload
    run.result_summary = payload.result_summary
    run.finished_at = utcnow()
    run.lease_expires_at = None
    run.last_error = None

    session = db.query(AgentSession).filter(AgentSession.id == run.session_id).first()
    if session:
        session.last_run_at = run.finished_at

    db.commit()
    db.refresh(run)
    return run


@router.post("/agent/runs/{run_id}/fail", response_model=AgentRunResponse)
def fail_run(
    run_id: str,
    payload: AgentRunFailRequest,
    db: Session = Depends(get_db),
):
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    if payload.worker_id and run.claimed_by and run.claimed_by != payload.worker_id:
        raise HTTPException(status_code=409, detail="Run is claimed by another worker")

    run.status = "failed"
    run.last_error = payload.error_message
    run.finished_at = utcnow()
    run.lease_expires_at = None
    db.commit()
    db.refresh(run)
    return run
