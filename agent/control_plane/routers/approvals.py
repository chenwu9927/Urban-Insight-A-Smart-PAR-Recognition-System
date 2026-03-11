from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agent.control_plane.schemas import (
    AgentApprovalRequestAnswer,
    AgentApprovalRequestCreate,
    AgentApprovalRequestResponse,
)
from agent.control_plane.services import utcnow
from agent.models import AgentApprovalRequest, AgentRun, AgentSession
from backend.database import get_db

router = APIRouter()


@router.get("/agent/approvals", response_model=list[AgentApprovalRequestResponse])
def list_approvals(
    status: str | None = None,
    run_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AgentApprovalRequest)
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
    if run:
        if payload.status.lower() in {"approved", "approve", "accepted"}:
            run.status = "queued"
        elif payload.status.lower() in {"rejected", "reject", "denied"}:
            run.status = "failed"
            run.last_error = "Approval rejected"

    db.commit()
    db.refresh(approval)
    return approval
