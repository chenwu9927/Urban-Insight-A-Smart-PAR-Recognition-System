from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from agent.control_plane.services import utcnow
from agent.models import AgentApprovalRequest, AgentMessage, AgentRun, AgentScheduledTask, AgentSession
from backend.database import get_db

router = APIRouter()


def _serialize_run(run: AgentRun, session: AgentSession | None, trigger_message: AgentMessage | None) -> dict:
    content = trigger_message.content if trigger_message else None
    text = ""
    if isinstance(content, dict):
        text = str(content.get("text") or "").strip()
    return {
        "id": run.id,
        "status": run.status,
        "progress": run.progress,
        "schedule_mode": run.schedule_mode,
        "permission_mode": run.permission_mode,
        "session_id": run.session_id,
        "session_title": session.title if session else None,
        "session_kind": session.kind if session else None,
        "trigger_text": text or (trigger_message.text_preview if trigger_message else None),
        "result_summary": run.result_summary,
        "input_payload": run.input_payload,
        "claimed_by": run.claimed_by,
        "last_error": run.last_error,
        "scheduled_at": run.scheduled_at.isoformat() if run.scheduled_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "last_heartbeat_at": run.last_heartbeat_at.isoformat() if run.last_heartbeat_at else None,
        "lease_expires_at": run.lease_expires_at.isoformat() if run.lease_expires_at else None,
    }


@router.get("/agent/overview")
def get_agent_overview(
    active_limit: int = Query(default=8, ge=1, le=50),
    recent_limit: int = Query(default=8, ge=1, le=50),
    session_limit: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    now = utcnow()
    day_ago = now - datetime.timedelta(hours=24)
    active_statuses = ["queued", "claimed", "running", "waiting_approval", "waiting_input"]

    counts = {
        "sessions": db.query(func.count(AgentSession.id)).filter(AgentSession.is_deleted == False).scalar() or 0,  # noqa: E712
        "active_runs": db.query(func.count(AgentRun.id)).filter(AgentRun.status.in_(active_statuses)).scalar() or 0,
        "queued_runs": db.query(func.count(AgentRun.id)).filter(AgentRun.status == "queued").scalar() or 0,
        "waiting_approval_runs": db.query(func.count(AgentRun.id)).filter(AgentRun.status == "waiting_approval").scalar() or 0,
        "completed_last_24h": (
            db.query(func.count(AgentRun.id))
            .filter(AgentRun.status == "completed", AgentRun.finished_at != None, AgentRun.finished_at >= day_ago)  # noqa: E711
            .scalar()
            or 0
        ),
        "failed_last_24h": (
            db.query(func.count(AgentRun.id))
            .filter(AgentRun.status == "failed", AgentRun.finished_at != None, AgentRun.finished_at >= day_ago)  # noqa: E711
            .scalar()
            or 0
        ),
        "pending_approvals": db.query(func.count(AgentApprovalRequest.id)).filter(AgentApprovalRequest.status == "pending").scalar() or 0,
        "enabled_scheduled_tasks": (
            db.query(func.count(AgentScheduledTask.id)).filter(AgentScheduledTask.enabled == True).scalar() or 0  # noqa: E712
        ),
    }

    active_rows = (
        db.query(AgentRun, AgentSession, AgentMessage)
        .outerjoin(AgentSession, AgentSession.id == AgentRun.session_id)
        .outerjoin(AgentMessage, AgentMessage.id == AgentRun.trigger_message_id)
        .filter(AgentRun.status.in_(active_statuses))
        .order_by(AgentRun.created_at.asc())
        .limit(active_limit)
        .all()
    )
    recent_rows = (
        db.query(AgentRun, AgentSession, AgentMessage)
        .outerjoin(AgentSession, AgentSession.id == AgentRun.session_id)
        .outerjoin(AgentMessage, AgentMessage.id == AgentRun.trigger_message_id)
        .order_by(AgentRun.created_at.desc())
        .limit(recent_limit)
        .all()
    )
    pending_approvals = (
        db.query(AgentApprovalRequest, AgentSession)
        .outerjoin(AgentSession, AgentSession.id == AgentApprovalRequest.session_id)
        .filter(AgentApprovalRequest.status == "pending")
        .order_by(AgentApprovalRequest.created_at.asc())
        .limit(10)
        .all()
    )
    recent_sessions = (
        db.query(AgentSession)
        .filter(AgentSession.is_deleted == False)  # noqa: E712
        .order_by(AgentSession.updated_at.desc())
        .limit(session_limit)
        .all()
    )

    return {
        "generated_at": now.isoformat(),
        "counts": counts,
        "active_runs": [_serialize_run(run, session, trigger_message) for run, session, trigger_message in active_rows],
        "recent_runs": [_serialize_run(run, session, trigger_message) for run, session, trigger_message in recent_rows],
        "pending_approvals": [
            {
                "id": approval.id,
                "run_id": approval.run_id,
                "session_id": approval.session_id,
                "session_title": session.title if session else None,
                "tool_name": approval.tool_name,
                "risk_level": approval.risk_level,
                "reason": approval.reason,
                "created_at": approval.created_at.isoformat() if approval.created_at else None,
                "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
            }
            for approval, session in pending_approvals
        ],
        "recent_sessions": [
            {
                "id": session.id,
                "title": session.title,
                "kind": session.kind,
                "status": session.status,
                "source": session.source,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None,
                "last_run_at": session.last_run_at.isoformat() if session.last_run_at else None,
            }
            for session in recent_sessions
        ],
    }
