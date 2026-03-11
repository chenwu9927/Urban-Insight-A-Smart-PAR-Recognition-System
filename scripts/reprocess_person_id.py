import argparse
import os
import sys

from backend.database import get_db, MediaFile, AnalysisRecord
from backend.services.real_recognition import RealPedestrianRecognizer
from backend.services.recognition import MockPedestrianRecognizer


def get_recognizer():
    try:
        return RealPedestrianRecognizer()
    except Exception as exc:
        print(f"[warn] RealPedestrianRecognizer unavailable, using MockPedestrianRecognizer: {exc}")
        return MockPedestrianRecognizer()


def fetch_files(db, args):
    query = db.query(MediaFile).filter(MediaFile.file_type == "video")
    if args.file_id:
        query = query.filter(MediaFile.id.in_(args.file_id))
    if args.limit:
        query = query.limit(args.limit)
    return query.all()


def update_record(db, recognizer, media_file, dry_run=False):
    if not os.path.exists(media_file.file_path):
        print(f"[skip] file missing: {media_file.file_path}")
        return False

    results_data = recognizer.analyze_video(media_file.file_path)
    pedestrians = results_data.get("pedestrians", [])

    record = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.media_file_id == media_file.id)
        .order_by(AnalysisRecord.upload_time.desc())
        .first()
    )

    if record:
        record.pedestrian_count = len(pedestrians)
        record.results = pedestrians
        record.is_video = 1
        record.duration = results_data.get("duration", record.duration)
        record.camera_location = results_data.get("camera_location", record.camera_location)
    else:
        record = AnalysisRecord(
            media_file_id=media_file.id,
            filename=media_file.filename,
            pedestrian_count=len(pedestrians),
            results=pedestrians,
            is_video=1,
            duration=results_data.get("duration", 0),
            camera_location=results_data.get("camera_location", "Unknown"),
        )
        db.add(record)

    media_file.status = "analyzed"

    if not dry_run:
        db.commit()
    return True


def main():
    parser = argparse.ArgumentParser(description="Reprocess video analyses to generate person_id.")
    parser.add_argument("--all", action="store_true", help="Process all video files")
    parser.add_argument("--file-id", action="append", type=int, help="Process specific file IDs (repeatable)")
    parser.add_argument("--limit", type=int, help="Limit number of files")
    parser.add_argument("--dry-run", action="store_true", help="Run without DB commit")
    args = parser.parse_args()

    if not args.all and not args.file_id:
        print("Please provide --all or --file-id.")
        return 1

    db = next(get_db())
    recognizer = get_recognizer()

    try:
        files = fetch_files(db, args)
        print(f"[info] processing {len(files)} files")
        success = 0
        for media_file in files:
            ok = update_record(db, recognizer, media_file, dry_run=args.dry_run)
            if ok:
                success += 1
                print(f"[ok] file_id={media_file.id} filename={media_file.filename}")
        print(f"[done] updated {success} files")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
