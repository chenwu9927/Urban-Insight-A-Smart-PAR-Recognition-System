from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agent.control_plane.schemas import (
    AgentApprovalRequestAnswer,
    AgentApprovalRequestCreate,
    AgentApprovalRequestResponse,
)
from agent.control_plane.services import create_message, utcnow
from agent.models import AgentApprovalRequest, AgentRun, AgentScheduledTask, AgentSession
from backend.database import get_db

router = APIRouter()


@router.get("/agent/approvals", response_model=list[AgentApprovalRequestResponse])
def list_approvals(
    status: str | None = None,
    run_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = (
        db.query(AgentApprovalRequest)
        .join(AgentSession, AgentSession.id == AgentApprovalRequest.session_id)
        .filter(AgentSession.is_deleted == False)  # noqa: E712
    )
    if status:
        query = query.filter(AgentApprovalRequest.status == status)
    if run_id:
        query = query.filter(AgentApprovalRequest.run_id == run_id)
    return query.order_by(AgentApprovalRequest.created_at.desc()).limit(limit).all()


@router.post("/agent/approvals", response_model=AgentApprovalRequestResponse)
def create_approval_request(payload: AgentApprovalRequestCreate, db: Session = Depends(get_db)):
    run = db.query(AgentRun).filter(AgentRun.id == payload.run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    session = db.query(AgentSession).filter(AgentSession.id == payload.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Agent session not found")

    approval = AgentApprovalRequest(**payload.model_dump())
    db.add(approval)
    run.status = "waiting_approval"
    run.lease_expires_at = None
    run.claimed_by = None
    run.last_error = None
    db.commit()
    db.refresh(approval)
    return approval


@router.get("/agent/approvals/{approval_id}", response_model=AgentApprovalRequestResponse)
def get_approval_request(approval_id: str, db: Session = Depends(get_db)):
    approval = db.query(AgentApprovalRequest).filter(AgentApprovalRequest.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return approval


@router.post("/agent/approvals/{approval_id}/answer", response_model=AgentApprovalRequestResponse)
def answer_approval_request(
    approval_id: str,
    payload: AgentApprovalRequestAnswer,
    db: Session = Depends(get_db),
):
    approval = db.query(AgentApprovalRequest).filter(AgentApprovalRequest.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    approval.status = payload.status
    approval.answers = payload.answers
    approval.answered_by_user_id = payload.answered_by_user_id
    approval.answered_at = utcnow()

    run = db.query(AgentRun).filter(AgentRun.id == approval.run_id).first()
    session = db.query(AgentSession).filter(AgentSession.id == approval.session_id).first()
    task = None
    if run:
        task = (
            db.query(AgentScheduledTask)
            .filter(AgentScheduledTask.id == run.scheduled_task_id)
            .first()
            if run.scheduled_task_id
            else None
        )
        if payload.status.lower() in {"approved", "approve", "accepted"}:
            run.status = "queued"
            run.claimed_by = None
            run.lease_expires_at = None
            run.last_error = None
            if task:
                task.last_run_status = "queued"
                task.last_error = None
        elif payload.status.lower() in {"rejected", "reject", "denied"}:
            run.status = "failed"
            run.last_error = "Approval rejected"
            run.finished_at = utcnow()
            run.lease_expires_at = None
            run.claimed_by = None
            if task:
                task.last_run_status = "failed"
                task.last_error = run.last_error
            if session:
                session.last_run_at = run.finished_at

    create_message(
        db,
        session_id=approval.session_id,
        run_id=approval.run_id,
        role="assistant",
        content={
            "text": (
                "Approval approved. The agent run has been returned to the queue."
                if payload.status.lower() in {"approved", "approve", "accepted"}
                else "Approval rejected. The agent run has been stopped."
            ),
            "approval_id": approval.id,
            "status": approval.status,
            "answers": approval.answers,
        },
        text_preview=(
            "Approval approved. The agent run has been returned to the queue."
            if payload.status.lower() in {"approved", "approve", "accepted"}
            else "Approval rejected. The agent run has been stopped."
        )[:500],
    )

    db.commit()
    db.refresh(approval)
    return approval
