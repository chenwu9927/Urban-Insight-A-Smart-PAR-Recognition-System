from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agent.control_plane.schemas import (
    AgentMessageCreate,
    AgentMessageResponse,
    AgentSessionCreate,
    AgentSessionResponse,
    AgentSessionUpdate,
)
from agent.control_plane.services import create_message
from agent.models import AgentMessage, AgentSession
from backend.database import get_db

router = APIRouter()
OPERATOR_SESSION_SOURCES = ("web", "email", "manual")


def _normalize_title(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if set(text) <= {"?"}:
        return None
    return text


def _serialize_session_summary(session: AgentSession) -> AgentSessionResponse:
    return AgentSessionResponse(
        id=session.id,
        kind=session.kind,
        title=_normalize_title(session.title),
        status=session.status,
        owner_user_id=session.owner_user_id,
        site_id=session.site_id,
        camera_id=session.camera_id,
        source=session.source,
        config_snapshot=None,
        state_patch=None,
        last_run_at=session.last_run_at,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get("/agent/sessions", response_model=list[AgentSessionResponse])
def list_sessions(
    kind: str | None = None,
    status: str | None = None,
    source: str | None = None,
    site_id: str | None = None,
    camera_id: str | None = None,
    operator_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AgentSession).filter(AgentSession.is_deleted == False)  # noqa: E712
    if kind:
        query = query.filter(AgentSession.kind == kind)
    if status:
        query = query.filter(AgentSession.status == status)
    if source:
        query = query.filter(AgentSession.source == source)
    elif operator_only:
        query = query.filter(AgentSession.source.in_(OPERATOR_SESSION_SOURCES))
    if site_id:
        query = query.filter(AgentSession.site_id == site_id)
    if camera_id:
        query = query.filter(AgentSession.camera_id == camera_id)
    sessions = query.order_by(AgentSession.created_at.desc()).limit(limit).all()
    return [_serialize_session_summary(session) for session in sessions]


@router.post("/agent/sessions", response_model=AgentSessionResponse)
def create_session(payload: AgentSessionCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["title"] = _normalize_title(data.get("title"))
    session = AgentSession(**data)
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
    return _serialize_session_summary(session)


@router.get("/agent/sessions/{session_id}/messages", response_model=list[AgentMessageResponse])
def list_session_messages(
    session_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    tail: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    session = (
        db.query(AgentSession)
        .filter(AgentSession.id == session_id, AgentSession.is_deleted == False)  # noqa: E712
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Agent session not found")
    query = (
        db.query(AgentMessage)
        .filter(AgentMessage.session_id == session_id)
    )
    if tail:
        rows = query.order_by(AgentMessage.created_at.desc()).limit(limit).all()
        return list(reversed(rows))
    return query.order_by(AgentMessage.created_at.asc()).limit(limit).all()


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


@router.patch("/agent/sessions/{session_id}", response_model=AgentSessionResponse)
def update_session(
    session_id: str,
    payload: AgentSessionUpdate,
    db: Session = Depends(get_db),
):
    session = (
        db.query(AgentSession)
        .filter(AgentSession.id == session_id, AgentSession.is_deleted == False)  # noqa: E712
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Agent session not found")

    if payload.title is not None:
        session.title = _normalize_title(payload.title)
    if payload.status is not None:
        session.status = payload.status
    if payload.config_snapshot is not None:
        session.config_snapshot = payload.config_snapshot
    if payload.state_patch is not None:
        session.state_patch = payload.state_patch
    if payload.last_run_at is not None:
        session.last_run_at = payload.last_run_at

    db.commit()
    db.refresh(session)
    return session
