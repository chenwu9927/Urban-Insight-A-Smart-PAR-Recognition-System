from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..services.stats_service import compute_stats

router = APIRouter()

@router.get("/stats")
def get_stats(
    file_id: Optional[int] = Query(None, description="可选：指定文件ID进行过滤"),
    interval: int = Query(60, description="时间间隔（分钟），可选 1, 5, 30, 60"),
    date: Optional[str] = Query(None, description="可选：指定日期过滤，格式YYYY-MM-DD"),
    dedup: int = Query(1, description="是否按 person_id 去重(1/0)"),
    db: Session = Depends(get_db)
):
    """
    获取客流统计数据。
    - file_id: 可选，指定文件ID过滤
    - interval: 时间间隔（分钟），支持 1, 5, 30, 60
    - date: 可选，指定日期过滤（格式 YYYY-MM-DD）
    """
    return compute_stats(db, file_id=file_id, interval=interval, date=date, dedup=bool(dedup))
