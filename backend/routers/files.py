from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import (
    get_db,
    MediaFile,
    AnalysisRecord,
    AnalysisReport,
    AnalysisTask,
    InsightCache,
)
from pydantic import BaseModel
import shutil
import os
import datetime

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
THUMBNAIL_DIR = os.getenv("THUMBNAIL_DIR", "thumbnails")
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

class MediaFileResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    upload_time: datetime.datetime
    status: str
    start_time: Optional[datetime.datetime] = None
    file_size: int = 0

    model_config = {
        "from_attributes": True,
    }

@router.post("/files/upload", response_model=MediaFileResponse)
async def upload_file(
    file: UploadFile = File(...), 
    start_time: Optional[str] = Form(None, description="视频开始时间，格式：YYYY-MM-DDTHH:MM"),
    db: Session = Depends(get_db)
):
    file_location = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
    
    # 获取文件大小
    file_size = os.path.getsize(file_location)
    
    file_type = "video" if file.filename.endswith(('.mp4', '.avi')) else "image"
    
    # 解析开始时间
    parsed_start_time = None
    if start_time:
        try:
            parsed_start_time = datetime.datetime.fromisoformat(start_time)
        except ValueError:
            pass  # 解析失败则忽略
    
    db_file = MediaFile(
        filename=file.filename,
        file_path=file_location,
        file_type=file_type,
        status="uploaded",
        start_time=parsed_start_time,
        file_size=file_size
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    
    return MediaFileResponse(
        id=db_file.id,
        filename=db_file.filename,
        file_type=db_file.file_type,
        upload_time=db_file.upload_time,
        status=db_file.status,
        start_time=db_file.start_time,
        file_size=db_file.file_size
    )

@router.get("/files", response_model=List[MediaFileResponse])
def get_files(db: Session = Depends(get_db)):
    return db.query(MediaFile).order_by(MediaFile.upload_time.desc()).all()

@router.delete("/files/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db)):
    db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Prevent deleting while processing to avoid inconsistent state.
    active_task = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.file_id == file_id,
            AnalysisTask.status.in_(["queued", "running"]),
        )
        .first()
    )
    if active_task:
        raise HTTPException(status_code=409, detail="File is being analyzed; please retry later")

    def _collect_thumbnail_names(results_payload):
        names = set()
        for ped in results_payload or []:
            if not isinstance(ped, dict):
                continue
            thumbnail = ped.get("thumbnail")
            if isinstance(thumbnail, str) and thumbnail.strip():
                names.add(thumbnail.strip())
        return names

    def _scope_contains_file_id(scope_obj, target_file_id):
        if isinstance(scope_obj, dict):
            for k, v in scope_obj.items():
                if k == "file_id":
                    try:
                        if int(v) == target_file_id:
                            return True
                    except Exception:
                        pass
                if _scope_contains_file_id(v, target_file_id):
                    return True
        elif isinstance(scope_obj, list):
            for item in scope_obj:
                if _scope_contains_file_id(item, target_file_id):
                    return True
        return False

    records = db.query(AnalysisRecord).filter(AnalysisRecord.media_file_id == file_id).all()
    record_ids = [r.id for r in records]

    thumbnail_names = set()
    for record in records:
        thumbnail_names.update(_collect_thumbnail_names(record.results))

    # Remove thumbnail files referenced by this file's analysis records.
    for name in thumbnail_names:
        thumbnail_path = os.path.join(THUMBNAIL_DIR, name)
        if os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
            except Exception:
                pass

    # Remove related analysis reports.
    if record_ids:
        reports = db.query(AnalysisReport).filter(AnalysisReport.record_id.in_(record_ids)).all()
        for report in reports:
            db.delete(report)

    # Remove related analysis records and tasks.
    for record in records:
        db.delete(record)
    tasks = db.query(AnalysisTask).filter(AnalysisTask.file_id == file_id).all()
    for task in tasks:
        db.delete(task)

    # Remove related cache entries with matching file_id in scope.
    caches = db.query(InsightCache).all()
    for cache in caches:
        if _scope_contains_file_id(cache.scope, file_id):
            db.delete(cache)

    # Attempt to delete physical media file.
    if os.path.exists(db_file.file_path):
        try:
            os.remove(db_file.file_path)
        except Exception:
            pass

    db.delete(db_file)
    db.commit()
    return {"ok": True}
