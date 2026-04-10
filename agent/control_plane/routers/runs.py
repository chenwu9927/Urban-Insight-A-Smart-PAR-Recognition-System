from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, or_
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
from agent.control_plane.services import create_follow_up_runs, create_message, create_replan_run, create_run, sync_goal_state, utcnow
from agent.models import AgentGoal, AgentMessage, AgentRun, AgentScheduledTask, AgentSession
from backend.database import get_db

router = APIRouter()


def _update_scheduled_task_from_run(
    db: Session,
    *,
    run: AgentRun,
    status: str,
    error_message: str | None = None,
) -> None:
    if not run.scheduled_task_id:
        return
    task = db.query(AgentScheduledTask).filter(AgentScheduledTask.id == run.scheduled_task_id).first()
    if not task:
        return
    task.last_run_id = run.id
    task.last_run_status = status
    task.last_error = error_message


def _record_goal_strategy_feedback(
    goal: AgentGoal | None,
    *,
    output_payload: dict[str, object] | None = None,
    error_message: str | None = None,
) -> None:
    if goal is None:
        return

    meta = dict(goal.meta or {})
    if isinstance(output_payload, dict):
        strategic_context = output_payload.get("strategic_context")
        if isinstance(strategic_context, dict):
            meta["last_strategy_context"] = strategic_context

        memory_writeback = output_payload.get("memory_writeback")
        if not isinstance(memory_writeback, dict):
            memory_writeback = {}
        strategy_feedback_status = output_payload.get("strategy_feedback_status") or memory_writeback.get("strategy_feedback_status")
        strategy_feedback_summary = output_payload.get("strategy_feedback_summary") or memory_writeback.get("strategy_feedback_summary")
        if strategy_feedback_status or strategy_feedback_summary:
            meta["last_strategy_feedback"] = {
                "status": strategy_feedback_status or "unknown",
                "summary": strategy_feedback_summary or "",
                "updated_at": utcnow().isoformat(),
            }

    if error_message:
        meta["last_strategy_feedback"] = {
            "status": "failed",
            "summary": error_message,
            "updated_at": utcnow().isoformat(),
        }
    goal.meta = meta


@router.get("/agent/runs", response_model=list[AgentRunResponse])
def list_runs(
    status: str | None = None,
    session_id: str | None = None,
    parent_run_id: str | None = None,
    goal_key: str | None = None,
    schedule_mode: str | None = None,
    claimed_by: str | None = None,
    source: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = (
        db.query(AgentRun)
        .join(AgentSession, AgentSession.id == AgentRun.session_id)
        .filter(AgentSession.is_deleted == False)  # noqa: E712
    )
    if status:
        query = query.filter(AgentRun.status == status)
    if session_id:
        query = query.filter(AgentRun.session_id == session_id)
    if parent_run_id:
        query = query.filter(AgentRun.parent_run_id == parent_run_id)
    if goal_key:
        query = query.filter(AgentRun.goal_key == goal_key)
    if schedule_mode:
        query = query.filter(AgentRun.schedule_mode == schedule_mode)
    if claimed_by:
        query = query.filter(AgentRun.claimed_by == claimed_by)
    if source:
        query = query.filter(AgentSession.source == source)
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

    input_payload = payload.input_payload
    if payload.action:
        normalized_input_payload = dict(input_payload or {})
        normalized_input_payload["action"] = payload.action
        if payload.params:
            params = dict(normalized_input_payload.get("params") or {})
            params.update(payload.params)
            if payload.action == "agent.chat" and not str(params.get("question") or "").strip():
                legacy_message = params.get("message")
                if isinstance(legacy_message, str) and legacy_message.strip():
                    params["question"] = legacy_message.strip()
            normalized_input_payload["params"] = params
        input_payload = normalized_input_payload
    if payload.prompt:
        normalized_input_payload = dict(input_payload or {})
        if not str(normalized_input_payload.get("action") or "").strip():
            params = dict(normalized_input_payload.get("params") or {})
            params.setdefault("question", payload.prompt)
            normalized_input_payload["action"] = "agent.chat"
            normalized_input_payload["params"] = params
        input_payload = normalized_input_payload

    run = create_run(
        db,
        session_id=session.id,
        trigger_message_id=trigger_message_id,
        parent_run_id=payload.parent_run_id,
        goal_key=payload.goal_key,
        step_index=payload.step_index,
        created_by_user_id=payload.created_by_user_id,
        schedule_mode=payload.schedule_mode,
        permission_mode=payload.permission_mode,
        config_snapshot=payload.config_snapshot,
        input_payload=input_payload,
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

    priority_rank = case(
        (
            (AgentSession.source == "web")
            & (AgentRun.schedule_mode == "immediate")
            & (AgentRun.parent_run_id == None),  # noqa: E711
            0,
        ),
        (AgentRun.schedule_mode == "event", 1),
        (AgentRun.schedule_mode == "immediate", 2),
        (AgentRun.schedule_mode == "verification", 3),
        (AgentRun.schedule_mode == "scheduled", 4),
        (AgentRun.schedule_mode == "goal_recovery", 5),
        (AgentRun.schedule_mode == "replan", 6),
        (AgentRun.schedule_mode == "proactive", 7),
        else_=8,
    )

    query = db.query(AgentRun).outerjoin(AgentSession, AgentSession.id == AgentRun.session_id).filter(
        or_(
            AgentRun.status == "queued",
            (AgentRun.status == "claimed") & (AgentRun.lease_expires_at != None) & (AgentRun.lease_expires_at < now),  # noqa: E711
            (AgentRun.status == "running") & (AgentRun.lease_expires_at != None) & (AgentRun.lease_expires_at < now),  # noqa: E711
        )
    )
    if payload.schedule_modes:
        query = query.filter(AgentRun.schedule_mode.in_(payload.schedule_modes))

    run = (
        query.order_by(
            priority_rank.asc(),
            AgentRun.scheduled_at.asc(),
            AgentRun.created_at.asc(),
        ).first()
    )
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
    run.claimed_by = None
    run.last_error = None
    spawned_follow_up_ids: list[str] = []

    session = db.query(AgentSession).filter(AgentSession.id == run.session_id).first()
    if session:
        session.last_run_at = run.finished_at
    _update_scheduled_task_from_run(db, run=run, status="completed")

    summary_text = (payload.result_summary or "").strip() or "Run completed successfully."
    create_message(
        db,
        session_id=run.session_id,
        run_id=run.id,
        role="assistant",
        content={
            "text": summary_text,
            "status": run.status,
            "output_payload": payload.output_payload,
        },
        text_preview=summary_text[:500],
    )

    existing_spawned = ((run.output_payload or {}).get("spawned_follow_up_run_ids") or []) if isinstance(run.output_payload, dict) else []
    auto_dispatch_followups = True
    if isinstance(run.input_payload, dict) and run.input_payload.get("auto_dispatch_followups") is False:
        auto_dispatch_followups = False
    planned_steps = (payload.output_payload or {}).get("planned_steps") if isinstance(payload.output_payload, dict) else None
    if isinstance(payload.output_payload, dict) and payload.output_payload.get("auto_dispatch_followups") is False:
        auto_dispatch_followups = False
    goal_summary = (payload.output_payload or {}).get("goal_summary") if isinstance(payload.output_payload, dict) else None
    auto_replan = True
    if isinstance(run.input_payload, dict) and run.input_payload.get("auto_replan") is False:
        auto_replan = False
    if isinstance(payload.output_payload, dict) and payload.output_payload.get("auto_replan") is False:
        auto_replan = False
    if auto_dispatch_followups and not existing_spawned and isinstance(planned_steps, list) and planned_steps:
        spawned_runs = create_follow_up_runs(
            db,
            parent_run=run,
            steps=planned_steps,
            goal_summary=goal_summary,
            auto_replan=auto_replan,
        )
        spawned_follow_up_ids = [item.id for item in spawned_runs]
        if spawned_follow_up_ids:
            run.output_payload = dict(run.output_payload or {})
            run.output_payload["spawned_follow_up_run_ids"] = spawned_follow_up_ids

    if run.goal_key and run.schedule_mode == "verification":
        goal = db.query(AgentGoal).filter(AgentGoal.id == run.goal_key).first()
        if goal is not None and not planned_steps:
            meta = dict(goal.meta or {})
            meta["verified_at"] = utcnow().isoformat()
            goal.meta = meta

    if run.goal_key:
        goal = db.query(AgentGoal).filter(AgentGoal.id == run.goal_key).first()
        _record_goal_strategy_feedback(goal, output_payload=payload.output_payload)

    if run.goal_key:
        sync_goal_state(db, run.goal_key)
    elif spawned_follow_up_ids:
        run.goal_key = run.id
        sync_goal_state(db, run.goal_key)

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
    run.progress = max(1, int(run.progress or 0))
    run.last_error = payload.error_message
    run.finished_at = utcnow()
    run.lease_expires_at = None
    run.claimed_by = None
    spawned_replan_run_id: str | None = None
    session = db.query(AgentSession).filter(AgentSession.id == run.session_id).first()
    if session:
        session.last_run_at = run.finished_at
    _update_scheduled_task_from_run(db, run=run, status="failed", error_message=payload.error_message)
    create_message(
        db,
        session_id=run.session_id,
        run_id=run.id,
        role="assistant",
        content={
            "text": payload.error_message,
            "status": run.status,
            "error_message": payload.error_message,
        },
        text_preview=payload.error_message[:500],
    )
    auto_replan = True
    if isinstance(run.input_payload, dict) and run.input_payload.get("auto_replan") is False:
        auto_replan = False
    if auto_replan and run.goal_key:
        replan_run = create_replan_run(db, failed_run=run, error_message=payload.error_message)
        if replan_run is not None:
            spawned_replan_run_id = replan_run.id
    if run.goal_key:
        goal = db.query(AgentGoal).filter(AgentGoal.id == run.goal_key).first()
        _record_goal_strategy_feedback(goal, error_message=payload.error_message)
    if run.goal_key:
        sync_goal_state(db, run.goal_key)
    if spawned_replan_run_id:
        run.output_payload = dict(run.output_payload or {})
        run.output_payload["spawned_replan_run_id"] = spawned_replan_run_id
    db.commit()
    db.refresh(run)
    return run
