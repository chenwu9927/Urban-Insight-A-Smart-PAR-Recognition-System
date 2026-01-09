from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db, AnalysisRecord, MediaFile
import json
import datetime

router = APIRouter()

class SearchRequest(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    camera_location: Optional[str] = None
    gender: Optional[str] = None
    age_group: Optional[str] = None
    upper_color: Optional[str] = None

class SearchResult(BaseModel):
    record_id: int
    filename: str
    camera_location: str
    upload_time: str
    real_time: Optional[str] = None  # 真实时间
    snippet_info: dict

@router.post("/search", response_model=List[SearchResult])
def search_pedestrians(criteria: SearchRequest, db: Session = Depends(get_db)):
    query = db.query(AnalysisRecord)
    
    if criteria.camera_location and criteria.camera_location != "All":
        query = query.filter(AnalysisRecord.camera_location == criteria.camera_location)
        
    candidate_records = query.order_by(AnalysisRecord.upload_time.desc()).limit(100).all()
    
    # 获取文件开始时间映射
    file_ids = set(r.media_file_id for r in candidate_records if r.media_file_id)
    file_start_times = {}
    if file_ids:
        files = db.query(MediaFile).filter(MediaFile.id.in_(file_ids)).all()
        for f in files:
            if f.start_time:
                file_start_times[f.id] = f.start_time
    
    matches = []
    
    for record in candidate_records:
        ped_list = record.results
        if not ped_list:
            continue
        
        # 获取该文件的开始时间
        file_start_time = file_start_times.get(record.media_file_id)
            
        for ped in ped_list:
            attrs = ped.get('attributes', {})
            
            match = True
            if criteria.gender and criteria.gender != "All" and attrs.get('gender') != criteria.gender:
                match = False
            if criteria.age_group and criteria.age_group != "All" and attrs.get('age_group') != criteria.age_group:
                match = False
            if criteria.upper_color and criteria.upper_color != "All" and attrs.get('upper_color') != criteria.upper_color:
                match = False
            
            if match:
                # 计算真实时间
                real_time_str = None
                timestamp = ped.get('timestamp', 0)
                if file_start_time and timestamp is not None:
                    real_time = file_start_time + datetime.timedelta(seconds=timestamp)
                    real_time_str = real_time.strftime("%H:%M:%S")
                
                matches.append(SearchResult(
                    record_id=record.id,
                    filename=record.filename,
                    camera_location=record.camera_location or "Unknown",
                    upload_time=record.upload_time.isoformat(),
                    real_time=real_time_str,
                    snippet_info=ped
                ))
    
    return matches

