from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db, AnalysisRecord
from pydantic import BaseModel
import datetime

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

