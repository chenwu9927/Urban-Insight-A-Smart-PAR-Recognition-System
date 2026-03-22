from __future__ import annotations

import datetime
import queue
import threading
import traceback
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import AnalysisRecord, AnalysisTask, MediaFile, SessionLocal, get_db
from ..runtime import get_recognizer


router = APIRouter()

analysis_queue: queue.Queue[int] = queue.Queue()
analysis_worker_stop = threading.Event()
analysis_worker_thread: Optional[threading.Thread] = None
task_progress_lock = threading.Lock()
task_progress_map: Dict[int, Dict[str, Any]] = {}


def _normalize_image_results(pedestrians: Any):
    peds_output = []
    for ped in pedestrians or []:
        if hasattr(ped, "model_dump"):
            data = ped.model_dump()
        elif hasattr(ped, "dict"):
            data = ped.dict()
        elif isinstance(ped, dict):
            data = dict(ped)
        else:
            continue

        extra = getattr(ped, "extra_attributes", None)
        if isinstance(extra, dict) and isinstance(data.get("attributes"), dict):
            data["attributes"].update(extra)

        peds_output.append(data)
    return peds_output


def _set_task_progress(
    task_id: int,
    *,
    processed_units: Optional[int] = None,
    total_units: Optional[int] = None,
    status: Optional[str] = None,
):
    with task_progress_lock:
        current = task_progress_map.get(task_id, {})
        if processed_units is not None:
            current["processed_units"] = max(0, int(processed_units))
        if total_units is not None:
            current["total_units"] = max(0, int(total_units))
        if status is not None:
            current["status"] = status
        p = current.get("processed_units")
        t = current.get("total_units")
        if isinstance(p, int) and isinstance(t, int) and t > 0:
            current["progress_percent"] = max(0, min(100, round(p * 100 / t)))
        task_progress_map[task_id] = current


def _get_task_progress(task_id: int) -> Dict[str, Any]:
    with task_progress_lock:
        return dict(task_progress_map.get(task_id, {}))


def _clear_task_progress(task_id: int):
    with task_progress_lock:
        task_progress_map.pop(task_id, None)


def _to_iso(dt):
    if not dt:
        return None
    return dt.isoformat()


def _task_response_payload(task: AnalysisTask) -> Dict[str, Any]:
    progress = _get_task_progress(task.id)
    percent = progress.get("progress_percent")
    processed_units = progress.get("processed_units")
    total_units = progress.get("total_units")
    if task.status == "completed":
        percent = 100
    elif task.status == "queued" and percent is None:
        percent = 0
    elif percent is None:
        percent = 0

    eta_seconds = None
    if task.status == "running" and task.started_at and isinstance(percent, int) and percent > 0:
        elapsed = (datetime.datetime.utcnow() - task.started_at).total_seconds()
        if elapsed >= 0:
            eta = elapsed * (100 - percent) / percent
            eta_seconds = max(0, int(round(eta)))

    return {
        "task_id": task.id,
        "file_id": task.file_id,
        "status": task.status,
        "progress_percent": int(percent),
        "processed_units": int(processed_units) if isinstance(processed_units, int) else None,
        "total_units": int(total_units) if isinstance(total_units, int) else None,
        "eta_seconds": eta_seconds,
        "result_record_id": task.result_record_id,
        "error_message": task.error_message,
        "created_at": _to_iso(task.created_at),
        "started_at": _to_iso(task.started_at),
        "finished_at": _to_iso(task.finished_at),
    }


def _task_detail_payload(task: AnalysisTask, db_file: Optional[MediaFile] = None) -> Dict[str, Any]:
    payload = _task_response_payload(task)
    if db_file is not None:
        payload.update(
            {
                "filename": db_file.filename,
                "file_type": db_file.file_type,
                "file_status": db_file.status,
                "upload_time": _to_iso(db_file.upload_time),
                "file_size": db_file.file_size,
            }
        )
    else:
        payload.update(
            {
                "filename": None,
                "file_type": None,
                "file_status": None,
                "upload_time": None,
                "file_size": None,
            }
        )
    return payload


def _run_analysis_for_file(
    db_file: MediaFile,
    *,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Any]:
    recognizer = get_recognizer()

    if db_file.file_type == "video":
        try:
            results_data = recognizer.analyze_video(
                db_file.file_path,
                progress_callback=progress_callback,
            )
        except TypeError:
            results_data = recognizer.analyze_video(db_file.file_path)
        return {
            "pedestrians": results_data.get("pedestrians", []),
            "is_video": 1,
            "duration": int(results_data.get("duration", 0) or 0),
            "camera_location": results_data.get("camera_location") or "Camera 01",
        }

    if progress_callback:
        progress_callback(0, 1)
    pedestrians = _normalize_image_results(recognizer.analyze(db_file.file_path))
    if progress_callback:
        progress_callback(1, 1)
    return {
        "pedestrians": pedestrians,
        "is_video": 0,
        "duration": 0,
        "camera_location": "Entrance A",
    }


def _process_analysis_task(task_id: int):
    db = SessionLocal()
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
        if not task:
            return

        db_file = db.query(MediaFile).filter(MediaFile.id == task.file_id).first()
        if not db_file:
            task.status = "failed"
            task.error_message = "File not found"
            task.finished_at = datetime.datetime.utcnow()
            db.commit()
            return

        task.status = "running"
        task.started_at = datetime.datetime.utcnow()
        task.error_message = None
        db_file.status = "processing"
        db.commit()

        _set_task_progress(task_id, processed_units=0, total_units=100, status="running")

        def progress_callback(processed_units: int, total_units: int):
            _set_task_progress(
                task_id,
                processed_units=processed_units,
                total_units=total_units,
                status="running",
            )

        analysis = _run_analysis_for_file(db_file, progress_callback=progress_callback)
        pedestrians = analysis["pedestrians"]

        db_record = AnalysisRecord(
            media_file_id=db_file.id,
            filename=db_file.filename,
            pedestrian_count=len(pedestrians),
            results=pedestrians,
            is_video=analysis["is_video"],
            duration=analysis["duration"],
            camera_location=analysis["camera_location"],
        )
        db.add(db_record)
        db.flush()

        db_file.status = "analyzed"
        task.status = "completed"
        task.result_record_id = db_record.id
        task.finished_at = datetime.datetime.utcnow()
        _set_task_progress(task_id, processed_units=1, total_units=1, status="completed")
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = str(exc)[:1000]
                task.finished_at = datetime.datetime.utcnow()
                _set_task_progress(task_id, status="failed")

            if task and task.file_id:
                db_file = db.query(MediaFile).filter(MediaFile.id == task.file_id).first()
                if db_file:
                    db_file.status = "error"
            db.commit()
        except Exception:
            db.rollback()

        print(f"[error] Analysis task {task_id} failed: {exc}")
        traceback.print_exc()
    finally:
        _clear_task_progress(task_id)
        db.close()


def _analysis_worker_loop():
    while not analysis_worker_stop.is_set():
        try:
            task_id = analysis_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        try:
            _process_analysis_task(task_id)
        finally:
            analysis_queue.task_done()


@router.on_event("startup")
def startup_analysis_worker():
    global analysis_worker_thread
    if analysis_worker_thread and analysis_worker_thread.is_alive():
        return

    analysis_worker_stop.clear()
    analysis_worker_thread = threading.Thread(
        target=_analysis_worker_loop,
        name="analysis-worker",
        daemon=True,
    )
    analysis_worker_thread.start()
    print("Analysis worker started.")


@router.on_event("shutdown")
def shutdown_analysis_worker():
    analysis_worker_stop.set()


@router.post("/analyze/{file_id}")
async def analyze_file(file_id: int, db: Session = Depends(get_db)):
    db_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    active_task = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.file_id == file_id,
            AnalysisTask.status.in_(["queued", "running"]),
        )
        .order_by(AnalysisTask.id.desc())
        .first()
    )
    if active_task:
        return _task_response_payload(active_task)

    task = AnalysisTask(file_id=file_id, status="queued")
    db_file.status = "processing"
    db.add(task)
    db.commit()
    db.refresh(task)

    analysis_queue.put(task.id)
    _set_task_progress(task.id, processed_units=0, total_units=100, status="queued")
    return _task_response_payload(task)


@router.get("/analyze/tasks/{task_id}")
def get_analysis_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(AnalysisTask).filter(AnalysisTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return _task_response_payload(task)


@router.get("/analyze/tasks")
def list_analysis_tasks(
    status: str | None = None,
    statuses: str | None = None,
    file_id: int | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(AnalysisTask)
    if status:
        query = query.filter(AnalysisTask.status == status)
    if statuses:
        values = [item.strip() for item in statuses.split(",") if item.strip()]
        if values:
            query = query.filter(AnalysisTask.status.in_(values))
    if file_id is not None:
        query = query.filter(AnalysisTask.file_id == file_id)

    tasks = query.order_by(AnalysisTask.created_at.desc(), AnalysisTask.id.desc()).limit(max(1, min(200, limit))).all()
    if not tasks:
        return []

    file_ids = [task.file_id for task in tasks if task.file_id is not None]
    files = db.query(MediaFile).filter(MediaFile.id.in_(file_ids)).all() if file_ids else []
    files_by_id = {item.id: item for item in files}
    return [_task_detail_payload(task, files_by_id.get(task.file_id)) for task in tasks]
