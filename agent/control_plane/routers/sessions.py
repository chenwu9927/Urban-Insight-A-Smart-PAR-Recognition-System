from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agent.control_plane.schemas import (
    AgentMessageCreate,
    AgentMessageResponse,
    AgentSessionCreate,
    AgentSessionResponse,
)
from agent.control_plane.services import create_message
from agent.models import AgentMessage, AgentSession
from backend.database import get_db

router = APIRouter()


@router.get("/agent/sessions", response_model=list[AgentSessionResponse])
def list_sessions(
    kind: str | None = None,
    status: str | None = None,
    site_id: str | None = None,
    camera_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AgentSession).filter(AgentSession.is_deleted == False)  # noqa: E712
    if kind:
        query = query.filter(AgentSession.kind == kind)
    if status:
        query = query.filter(AgentSession.status == status)
    if site_id:
        query = query.filter(AgentSession.site_id == site_id)
    if camera_id:
        query = query.filter(AgentSession.camera_id == camera_id)
    return query.order_by(AgentSession.created_at.desc()).limit(limit).all()


@router.post("/agent/sessions", response_model=AgentSessionResponse)
def create_session(payload: AgentSessionCreate, db: Session = Depends(get_db)):
    session = AgentSession(**payload.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/agent/sessions/{session_id}", response_model=AgentSessionResponse)
def get_session(session_id: str, db: Session = Depends(get_db)):
    session = (
        db.query(AgentSession)
        .filter(AgentSession.id == session_id, AgentSession.is_deleted == False)  # noqa: E712
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Agent session not found")
    return session


@router.get("/agent/sessions/{session_id}/messages", response_model=list[AgentMessageResponse])
def list_session_messages(
    session_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    session = (
        db.query(AgentSession)
        .filter(AgentSession.id == session_id, AgentSession.is_deleted == False)  # noqa: E712
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Agent session not found")
    return (
        db.query(AgentMessage)
        .filter(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at.asc())
        .limit(limit)
        .all()
    )


@router.post("/agent/sessions/{session_id}/messages", response_model=AgentMessageResponse)
def create_session_message(
    session_id: str,
    payload: AgentMessageCreate,
    db: Session = Depends(get_db),
):
    session = (
        db.query(AgentSession)
        .filter(AgentSession.id == session_id, AgentSession.is_deleted == False)  # noqa: E712
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Agent session not found")

    message = create_message(db, session_id=session_id, **payload.model_dump())
    db.commit()
    db.refresh(message)
    return message
