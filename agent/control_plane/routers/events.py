from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent.control_plane.schemas import AgentEventIngestRequest, AgentEventIngestResponse
from agent.control_plane.services import ingest_event
from backend.database import get_db

router = APIRouter()


@router.post("/agent/events", response_model=AgentEventIngestResponse)
def ingest_agent_event(payload: AgentEventIngestRequest, db: Session = Depends(get_db)):
    try:
        session, run, goal, deduped = ingest_event(
            db,
            event_type=payload.event_type,
            summary=payload.summary,
            payload=payload.payload,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            session_id=payload.session_id,
            goal_id=payload.goal_id,
            dedup_key=payload.dedup_key,
            ttl_seconds=payload.ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    db.commit()
    return AgentEventIngestResponse(
        accepted=True,
        deduped=deduped,
        session_id=session.id if session else None,
        goal_id=goal.id if goal else None,
        run_id=run.id if run else None,
    )
