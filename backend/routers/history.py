from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db, AnalysisRecord, AnalysisReport
from pydantic import BaseModel
import datetime

from ..services.llm_insights import generate_record_report

router = APIRouter()

class HistoryItem(BaseModel):
    id: int
    filename: str
    upload_time: datetime.datetime
    pedestrian_count: int

@router.get("/history", response_model=List[HistoryItem])
def get_history(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    records = db.query(AnalysisRecord).order_by(AnalysisRecord.upload_time.desc()).offset(skip).limit(limit).all()
    return records

@router.delete("/history/{record_id}")
def delete_history(record_id: int, db: Session = Depends(get_db)):
    record = db.query(AnalysisRecord).filter(AnalysisRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    db.delete(record)
    db.commit()
    return {"ok": True}


class ReportResponse(BaseModel):
    record_id: int
    llm_used: bool
    cached: bool = False
    report: dict


@router.get("/history/{record_id}/report", response_model=ReportResponse)
def get_history_report(
    record_id: int,
    use_llm: int = Query(1, description="是否使用LLM(1/0)，未配置key时自动降级"),
    refresh: int = Query(0, description="强制刷新(1/0)，忽略已存报告"),
    db: Session = Depends(get_db),
):
    record = db.query(AnalysisRecord).filter(AnalysisRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    existing = db.query(AnalysisReport).filter(AnalysisReport.record_id == record_id).first()
    if existing and not refresh:
        return {
            "record_id": record_id,
            "llm_used": bool(existing.llm_used),
            "cached": True,
            "report": existing.report or {},
        }

    # Build lightweight summary (avoid sending full results to LLM)
    peds = record.results or []
    gender_counts = {}
    age_counts = {}
    colors = {}
    for ped in peds[:1000]:
        attrs = (ped or {}).get("attributes", {}) or {}
        g = attrs.get("gender")
        a = attrs.get("age_group")
        c = attrs.get("upper_color")
        if g:
            gender_counts[g] = gender_counts.get(g, 0) + 1
        if a:
            age_counts[a] = age_counts.get(a, 0) + 1
        if c:
            colors[c] = colors.get(c, 0) + 1

    highlights = []
    if gender_counts:
        top_g = max(gender_counts.items(), key=lambda kv: kv[1])[0]
        highlights.append(f"性别最多：{top_g}")
    if age_counts:
        top_a = max(age_counts.items(), key=lambda kv: kv[1])[0]
        highlights.append(f"年龄层最多：{top_a}")
    if colors:
        top_c = max(colors.items(), key=lambda kv: kv[1])[0]
        highlights.append(f"上衣颜色最多：{top_c}")

    summary = {
        "meta": {
            "record_id": record.id,
            "filename": record.filename,
            "upload_time": record.upload_time.isoformat() if record.upload_time else None,
            "pedestrian_count": record.pedestrian_count or 0,
            "camera_location": record.camera_location,
            "is_video": bool(record.is_video),
            "duration": record.duration,
        },
        "counts": {
            "gender": gender_counts,
            "age_group": age_counts,
            "upper_color": colors,
        },
        "highlights": highlights,
    }

    report_payload = generate_record_report(summary, allow_llm=bool(use_llm))
    to_store = {
        "summary": report_payload.get("summary", ""),
        "key_findings": report_payload.get("key_findings", []) or [],
        "anomalies": report_payload.get("anomalies", []) or [],
        "recommendations": report_payload.get("recommendations", []) or [],
        "meta": summary["meta"],
        "counts": summary["counts"],
    }

    if existing:
        existing.report = to_store
        existing.llm_used = 1 if report_payload.get("llm_used") else 0
    else:
        db.add(
            AnalysisReport(
                record_id=record_id,
                report=to_store,
                llm_used=1 if report_payload.get("llm_used") else 0,
            )
        )
    db.commit()

    return {
        "record_id": record_id,
        "llm_used": bool(report_payload.get("llm_used")),
        "cached": False,
        "report": to_store,
    }

