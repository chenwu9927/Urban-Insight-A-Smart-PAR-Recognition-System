from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from pydantic import BaseModel

from ..database import get_db, InsightCache
from ..services.stats_service import compute_stats
from ..services.llm_insights import (
    answer_question,
    generate_insights,
    generate_brief,
    is_cache_fresh,
    make_cache_key,
)


router = APIRouter()


@router.get("/insights")
def get_insights(
    file_id: Optional[int] = Query(None, description="可选：指定文件ID进行过滤"),
    interval: int = Query(60, description="时间间隔（分钟），可选 1, 5, 30, 60"),
    date: Optional[str] = Query(None, description="可选：指定日期过滤，格式YYYY-MM-DD"),
    use_llm: int = Query(1, description="是否使用LLM(1/0)，未配置key时自动降级"),
    dedup: int = Query(1, description="是否按 person_id 去重(1/0)"),
    cache: int = Query(1, description="是否使用缓存(1/0)"),
    refresh: int = Query(0, description="强制刷新(1/0)，忽略缓存"),
    db: Session = Depends(get_db),
):
    stats = compute_stats(db, file_id=file_id, interval=interval, date=date, dedup=bool(dedup))
    scope = {"file_id": file_id, "interval": interval, "date": date, "dedup": bool(dedup)}
    cache_key = make_cache_key("insights", scope, bool(use_llm), stats)

    if cache and not refresh:
        cached = db.query(InsightCache).filter(InsightCache.cache_key == cache_key).first()
        if cached and is_cache_fresh(cached.created_at):
            return {
                **(cached.response or {}),
                "cached": True,
            }

    payload = generate_insights(stats, scope=scope, allow_llm=bool(use_llm))
    to_store = {
        **payload,
        "cached": False,
    }

    if cache:
        existing = db.query(InsightCache).filter(InsightCache.cache_key == cache_key).first()
        if existing:
            existing.response = to_store
            existing.llm_used = 1 if payload.get("llm_used") else 0
        else:
            db.add(
                InsightCache(
                    cache_key=cache_key,
                    endpoint="insights",
                    scope=scope,
                    response=to_store,
                    llm_used=1 if payload.get("llm_used") else 0,
                )
            )
        db.commit()

    return to_store


class AskRequest(BaseModel):
    question: str
    file_id: Optional[int] = None
    interval: int = 60
    date: Optional[str] = None
    use_llm: int = 1
    dedup: int = 1
    cache: int = 1
    refresh: int = 0


@router.post("/insights/ask")
def ask_insights(req: AskRequest, db: Session = Depends(get_db)):
    stats = compute_stats(db, file_id=req.file_id, interval=req.interval, date=req.date, dedup=bool(req.dedup))
    scope = {"file_id": req.file_id, "interval": req.interval, "date": req.date, "dedup": bool(req.dedup)}
    cache_key = make_cache_key("ask", scope, bool(req.use_llm), req.question, stats)

    if req.cache and not req.refresh:
        cached = db.query(InsightCache).filter(InsightCache.cache_key == cache_key).first()
        if cached and is_cache_fresh(cached.created_at):
            return {
                **(cached.response or {}),
                "cached": True,
            }

    payload = answer_question(stats, scope=scope, question=req.question, allow_llm=bool(req.use_llm))
    to_store = {
        **payload,
        "cached": False,
    }

    if req.cache:
        existing = db.query(InsightCache).filter(InsightCache.cache_key == cache_key).first()
        if existing:
            existing.response = to_store
            existing.llm_used = 1 if payload.get("llm_used") else 0
        else:
            db.add(
                InsightCache(
                    cache_key=cache_key,
                    endpoint="ask",
                    scope={"scope": scope, "question": req.question},
                    response=to_store,
                    llm_used=1 if payload.get("llm_used") else 0,
                )
            )
        db.commit()

    return to_store


@router.get("/insights/brief")
def get_daily_brief(
    interval: int = Query(60, description="时间间隔（分钟），可选 1, 5, 30, 60"),
    date: Optional[str] = Query(None, description="可选：指定日期过滤，格式YYYY-MM-DD"),
    use_llm: int = Query(1, description="是否使用LLM(1/0)，未配置key时自动降级"),
    dedup: int = Query(1, description="是否按 person_id 去重(1/0)"),
    cache: int = Query(1, description="是否使用缓存(1/0)"),
    refresh: int = Query(0, description="强制刷新(1/0)，忽略缓存"),
    db: Session = Depends(get_db),
):
    stats = compute_stats(db, file_id=None, interval=interval, date=date, dedup=bool(dedup))
    scope = {"file_id": None, "interval": interval, "date": date, "dedup": bool(dedup)}
    cache_key = make_cache_key("brief", scope, bool(use_llm), stats)

    if cache and not refresh:
        cached = db.query(InsightCache).filter(InsightCache.cache_key == cache_key).first()
        if cached and is_cache_fresh(cached.created_at):
            return {**(cached.response or {}), "cached": True}

    payload = generate_brief(stats, scope=scope, allow_llm=bool(use_llm))
    to_store = {**payload, "cached": False}

    if cache:
        existing = db.query(InsightCache).filter(InsightCache.cache_key == cache_key).first()
        if existing:
            existing.response = to_store
            existing.llm_used = 1 if payload.get("llm_used") else 0
        else:
            db.add(
                InsightCache(
                    cache_key=cache_key,
                    endpoint="brief",
                    scope=scope,
                    response=to_store,
                    llm_used=1 if payload.get("llm_used") else 0,
                )
            )
        db.commit()

    return to_store
