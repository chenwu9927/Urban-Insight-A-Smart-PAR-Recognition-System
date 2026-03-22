from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agent.control_plane.schemas import (
    AgentSubscriptionCreate,
    AgentSubscriptionResponse,
    AgentSubscriptionUpdate,
)
from agent.models import AgentSubscription
from backend.database import get_db

router = APIRouter()


@router.get("/agent/subscriptions", response_model=list[AgentSubscriptionResponse])
def list_subscriptions(
    channel: str | None = None,
    enabled: bool | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    target: str | None = None,
    schedule_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(AgentSubscription)
    if channel:
        query = query.filter(AgentSubscription.channel == channel)
    if enabled is not None:
        query = query.filter(AgentSubscription.enabled == enabled)
    if scope_type:
        query = query.filter(AgentSubscription.scope_type == scope_type)
    if scope_id:
        query = query.filter(AgentSubscription.scope_id == scope_id)
    if target:
        query = query.filter(AgentSubscription.target == target)
    if schedule_type:
        query = query.filter(AgentSubscription.schedule_type == schedule_type)
    return query.order_by(AgentSubscription.created_at.desc()).limit(limit).all()


@router.post("/agent/subscriptions", response_model=AgentSubscriptionResponse)
def create_subscription(payload: AgentSubscriptionCreate, db: Session = Depends(get_db)):
    values = payload.model_dump()
    existing = (
        db.query(AgentSubscription)
        .filter(
            AgentSubscription.channel == values["channel"],
            AgentSubscription.target == values["target"],
            AgentSubscription.scope_type == values["scope_type"],
            AgentSubscription.scope_id == values["scope_id"],
            AgentSubscription.schedule_type == values["schedule_type"],
        )
        .first()
    )
    if existing:
        for field, value in values.items():
            setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return existing

    subscription = AgentSubscription(**values)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.get("/agent/subscriptions/{subscription_id}", response_model=AgentSubscriptionResponse)
def get_subscription(subscription_id: str, db: Session = Depends(get_db)):
    subscription = db.query(AgentSubscription).filter(AgentSubscription.id == subscription_id).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return subscription


@router.put("/agent/subscriptions/{subscription_id}", response_model=AgentSubscriptionResponse)
def update_subscription(
    subscription_id: str,
    payload: AgentSubscriptionUpdate,
    db: Session = Depends(get_db),
):
    subscription = db.query(AgentSubscription).filter(AgentSubscription.id == subscription_id).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(subscription, field, value)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.delete("/agent/subscriptions/{subscription_id}")
def delete_subscription(subscription_id: str, db: Session = Depends(get_db)):
    subscription = db.query(AgentSubscription).filter(AgentSubscription.id == subscription_id).first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    db.delete(subscription)
    db.commit()
    return {"ok": True}
