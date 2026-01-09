from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import List
import shutil
import os
from .models import AnalysisResponse
from .services.recognition import MockPedestrianRecognizer
from .services.real_recognition import RealPedestrianRecognizer
from .database import init_db, get_db, AnalysisRecord, MediaFile
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException

from .routers import history, stats, search, files, auth

app = FastAPI(title="UrbanInsight API")

# Initialize DB
init_db()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(history.router)
app.include_router(stats.router)
app.include_router(search.router)
app.include_router(files.router)
app.include_router(auth.router)

# Initialize Services
# recognizer = MockPedestrianRecognizer()
recognizer = RealPedestrianRecognizer()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 缩略图静态文件服务
THUMBNAIL_DIR = "thumbnails"
os.makedirs(THUMBNAIL_DIR, exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails")

@app.get("/")
def read_root():
    return {"message": "UrbanInsight API is running"}

@app.post("/analyze/{file_id}", response_model=AnalysisResponse)
async def analyze_file(file_id: int, db: Session = Depends(get_db)):
    # 1. Fetch File
    db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")
        
    file_location = db_file.file_path
    
    # 2. Run Analysis
    if db_file.file_type == 'video':
        results_data = recognizer.analyze_video(file_location)
        pedestrians = results_data['pedestrians']
        is_video = 1
        duration = results_data['duration']
        camera_loc = results_data['camera_location']
    else:
        # Image
        pedestrians = recognizer.analyze(file_location)
        # Handle the extra attributes we patched in real_recognition.py
        # We need to flatten them into dictionary
        peds_output = []
        for p in pedestrians:
            d = p.dict()
            if hasattr(p, 'extra_attributes'):
                d['attributes'].update(p.extra_attributes)
            peds_output.append(d)
            
        pedestrians = peds_output
        is_video = 0
        duration = 0
        camera_loc = "Entrance A"

    # 3. Save Record
    db_record = AnalysisRecord(
        media_file_id=db_file.id,
        filename=db_file.filename,
        pedestrian_count=len(pedestrians),
        results=pedestrians,
        is_video=is_video,
        duration=duration,
        camera_location=camera_loc
    )
    db.add(db_record)
    
    # 4. Update File Status
    db_file.status = "analyzed"
    
    db.commit()
    db.refresh(db_record)
    
    return {
        "filename": db_file.filename,
        "pedestrians": pedestrians
    }
