import sys
sys.path.insert(0, '.')
from backend.database import get_db, MediaFile, AnalysisRecord
from backend.services.real_recognition import RealPedestrianRecognizer
import traceback
import json

db = next(get_db())
file = db.query(MediaFile).filter(MediaFile.id == 1).first()
print(f'File: {file.filename}, Type: {file.file_type}, Path: {file.file_path}')

try:
    recognizer = RealPedestrianRecognizer()
    print("Recognizer loaded, starting analysis...")
    results_data = recognizer.analyze_video(file.file_path)
    pedestrians = results_data['pedestrians']
    print(f'Results: {len(pedestrians)} pedestrians found')
    if pedestrians:
        print(f'First pedestrian: {json.dumps(pedestrians[0], indent=2)}')
    
    # 测试 JSON 序列化
    json_str = json.dumps(pedestrians)
    print(f'JSON serialization successful, length: {len(json_str)}')
    
    # 尝试保存到数据库
    db_record = AnalysisRecord(
        media_file_id=file.id,
        filename=file.filename,
        pedestrian_count=len(pedestrians),
        results=pedestrians,
        is_video=1,
        duration=results_data['duration'],
        camera_location=results_data['camera_location']
    )
    db.add(db_record)
    file.status = "analyzed"
    db.commit()
    print("Database save successful!")
    
except Exception as e:
    print(f'Error: {e}')
    traceback.print_exc()
finally:
    db.close()
