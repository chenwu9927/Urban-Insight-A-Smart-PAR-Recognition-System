from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db, MediaFile
from pydantic import BaseModel
import shutil
import os
import datetime

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class MediaFileResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    upload_time: datetime.datetime
    status: str
    start_time: Optional[datetime.datetime] = None
    file_size: int = 0

    class Config:
        orm_mode = True

@router.post("/files/upload", response_model=MediaFileResponse)
async def upload_file(
    file: UploadFile = File(...), 
    start_time: Optional[str] = Form(None, description="视频开始时间，格式：YYYY-MM-DDTHH:MM"),
    db: Session = Depends(get_db)
):
    file_location = f"{UPLOAD_DIR}/{file.filename}"
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
        
    # Attempt to delete physical file
    if os.path.exists(db_file.file_path):
        os.remove(db_file.file_path)
        
    db.delete(db_file)
    db.commit()
    return {"ok": True}
