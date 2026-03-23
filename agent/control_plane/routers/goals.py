from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agent.goal_memory import AgentGoalMemoryBridge
from agent.proactive_goals import ProactiveGoalPlanner
from agent.control_plane.schemas import AgentGoalResponse, AgentGoalSweepResponse, AgentProactiveGoalResponse, AgentRunResponse
from agent.control_plane.services import sweep_goals
from agent.models import AgentGoal, AgentRun
from backend.database import get_db

router = APIRouter()


@router.get("/agent/goals", response_model=list[AgentGoalResponse])
def list_goals(
    status: str | None = None,
    session_id: str | None = None,
    auto_replan: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AgentGoal)
    if status:
        query = query.filter(AgentGoal.status == status)
    if session_id:
        query = query.filter(AgentGoal.session_id == session_id)
    if auto_replan is not None:
        query = query.filter(AgentGoal.auto_replan == auto_replan)
    return query.order_by(AgentGoal.updated_at.desc(), AgentGoal.created_at.desc()).limit(limit).all()


@router.get("/agent/goals/{goal_id}", response_model=AgentGoalResponse)
def get_goal(goal_id: str, db: Session = Depends(get_db)):
    goal = db.query(AgentGoal).filter(AgentGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Agent goal not found")
    return goal


@router.get("/agent/goals/{goal_id}/runs", response_model=list[AgentRunResponse])
def list_goal_runs(goal_id: str, limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    goal = db.query(AgentGoal).filter(AgentGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Agent goal not found")
    return (
        db.query(AgentRun)
        .filter(AgentRun.goal_key == goal_id)
        .order_by(AgentRun.created_at.asc(), AgentRun.step_index.asc())
        .limit(limit)
        .all()
    )


@router.post("/agent/goals/sweep", response_model=AgentGoalSweepResponse)
def sweep_agent_goals(
    limit: int = Query(default=20, ge=1, le=200),
    verification_cooldown_minutes: int = Query(default=10, ge=1, le=24 * 60),
    goal_recovery_minutes: int = Query(default=180, ge=15, le=7 * 24 * 60),
    db: Session = Depends(get_db),
):
    memory_bridge = AgentGoalMemoryBridge(os.getenv("AGENT_WORKSPACE_DIR", "agent_workspace"))
    result = sweep_goals(
        db,
        limit=limit,
        verification_cooldown_minutes=verification_cooldown_minutes,
        goal_recovery_minutes=goal_recovery_minutes,
        goal_memory=memory_bridge,
    )
    db.commit()
    return result


@router.post("/agent/goals/proactive-from-memory", response_model=AgentProactiveGoalResponse)
def create_proactive_goals_from_memory(
    lookback_days: int = Query(default=3, ge=1, le=14),
    recurrence_threshold: int = Query(default=2, ge=2, le=20),
    use_llm_distillation: bool = Query(default=True),
    distilled_limit: int = Query(default=3, ge=1, le=10),
    max_memory_chars: int = Query(default=12000, ge=2000, le=40000),
    min_distilled_confidence: float = Query(default=0.55, ge=0.0, le=1.0),
    ttl_seconds: int = Query(default=21600, ge=300, le=7 * 24 * 3600),
    db: Session = Depends(get_db),
):
    planner = ProactiveGoalPlanner(os.getenv("AGENT_WORKSPACE_DIR", "agent_workspace"))
    batch = planner.extract_candidate_batch(
        lookback_days=lookback_days,
        recurrence_threshold=recurrence_threshold,
        use_llm_distillation=use_llm_distillation,
        distilled_limit=distilled_limit,
        max_memory_chars=max_memory_chars,
        min_distilled_confidence=min_distilled_confidence,
    )
    result = planner.materialize_candidates(
        db,
        candidates=list(batch.candidates),
        ttl_seconds=ttl_seconds,
        batch=batch,
    )
    db.commit()
    return AgentProactiveGoalResponse(
        **result,
        rule_candidates=batch.rule_candidates,
        llm_candidates=batch.llm_candidates,
        llm_distillation_used=batch.llm_used,
        llm_error=batch.llm_error,
        distillation_summary=batch.distillation_summary,
        strategy_summary=batch.strategy_summary,
        strategy_directives=list(batch.strategy_directives),
        risk_clusters=[dict(cluster) for cluster in batch.risk_clusters],
        strategy_feedback_summary=batch.strategy_feedback_summary,
        feedback_status_counts=dict(batch.feedback_status_counts),
        feedback_priority_boost=batch.feedback_priority_boost,
        priority_tier=batch.priority_tier,
        priority_boost=batch.priority_boost,
        priority_score=batch.priority_score,
    )
