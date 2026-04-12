from fastapi import APIRouter, Depends, Query, Request, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..database import get_db, AnalysisRecord, MediaFile, InsightCache
import datetime
import os
import shutil
import tempfile

from ..services.llm_insights import is_cache_fresh, make_cache_key, parse_nl_search_query

router = APIRouter()

class SearchRequest(BaseModel):
    file_id: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    camera_location: Optional[str] = None
    gender: Optional[str] = None
    age_group: Optional[str] = None
    upper_color: Optional[str] = None
    orientation: Optional[str] = None
    has_backpack: Optional[bool] = None
    has_hat: Optional[bool] = None
    has_glasses: Optional[bool] = None
    has_bag: Optional[bool] = None
    dedup_person: bool = True
    max_results: int = 300

class SearchResult(BaseModel):
    record_id: int
    file_id: Optional[int] = None
    filename: str
    is_video: bool = False
    duration: Optional[int] = None
    camera_location: str
    upload_time: str
    real_time: Optional[str] = None  # 真实时间
    snippet_info: dict


def _to_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes", "y"}
    if isinstance(v, (int, float)):
        return bool(v)
    return None


def _normalize_recognition_item(item):
    if hasattr(item, "model_dump"):
        data = item.model_dump()
    elif hasattr(item, "dict"):
        data = item.dict()
    elif isinstance(item, dict):
        data = dict(item)
    else:
        return None

    extra = getattr(item, "extra_attributes", None)
    attrs = data.get("attributes")
    if isinstance(extra, dict) and isinstance(attrs, dict):
        attrs.update(extra)

    return data


def _compute_attr_similarity(query_attrs: dict, cand_attrs: dict) -> float:
    rules = [
        ("gender", 0.22, "eq"),
        ("age_group", 0.12, "eq"),
        ("upper_color", 0.22, "eq"),
        ("lower_color", 0.12, "eq"),
        ("has_backpack", 0.14, "bool"),
        ("orientation", 0.10, "eq"),
        ("has_hat", 0.04, "bool"),
        ("has_glasses", 0.04, "bool"),
    ]
    numerator = 0.0
    denominator = 0.0

    for key, weight, mode in rules:
        qv = query_attrs.get(key)
        cv = cand_attrs.get(key)
        if qv is None or cv is None:
            continue

        denominator += weight
        if mode == "bool":
            qb = _to_bool(qv)
            cb = _to_bool(cv)
            if qb is not None and cb is not None and qb == cb:
                numerator += weight
        else:
            if str(qv).strip().lower() == str(cv).strip().lower():
                numerator += weight

    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _parse_hhmm(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        parts = value.strip().split(":")
        if len(parts) != 2:
            return None
        h = int(parts[0])
        m = int(parts[1])
        if h < 0 or h > 23 or m < 0 or m > 59:
            return None
        return h * 60 + m
    except Exception:
        return None


def _search(criteria: SearchRequest, db: Session) -> List[SearchResult]:
    query = db.query(AnalysisRecord)

    if criteria.file_id is not None:
        query = query.filter(AnalysisRecord.media_file_id == criteria.file_id)

    if criteria.camera_location and criteria.camera_location != "All":
        query = query.filter(AnalysisRecord.camera_location == criteria.camera_location)

    candidate_records = query.order_by(AnalysisRecord.upload_time.desc()).limit(200).all()

    # 获取文件开始时间映射
    file_ids = set(r.media_file_id for r in candidate_records if r.media_file_id)
    file_start_times = {}
    if file_ids:
        files = db.query(MediaFile).filter(MediaFile.id.in_(file_ids)).all()
        for f in files:
            if f.start_time:
                file_start_times[f.id] = f.start_time

    start_min = _parse_hhmm(criteria.start_time)
    end_min = _parse_hhmm(criteria.end_time)
    if start_min is not None and end_min is not None and end_min < start_min:
        # treat as invalid
        start_min, end_min = None, None

    matches: List[SearchResult] = []

    for record in candidate_records:
        ped_list = record.results
        if not ped_list:
            continue

        file_start_time = file_start_times.get(record.media_file_id)

        for ped in ped_list:
            attrs = ped.get("attributes", {})

            match = True
            if criteria.gender and criteria.gender != "All" and attrs.get("gender") != criteria.gender:
                match = False
            if criteria.age_group and criteria.age_group != "All" and attrs.get("age_group") != criteria.age_group:
                match = False
            if criteria.upper_color and criteria.upper_color != "All" and attrs.get("upper_color") != criteria.upper_color:
                match = False
            if criteria.orientation and criteria.orientation != "All" and attrs.get("orientation") != criteria.orientation:
                match = False

            def _bool_eq(key: str, expected: Optional[bool]) -> bool:
                if expected is None:
                    return True
                v = attrs.get(key)
                if isinstance(v, bool):
                    return v is expected
                # tolerate "Yes"/"No" style
                if isinstance(v, str):
                    return (v.lower() in ["yes", "true", "1"]) is expected
                return False if expected else True

            if not _bool_eq("has_backpack", criteria.has_backpack):
                match = False
            if not _bool_eq("has_hat", criteria.has_hat):
                match = False
            if not _bool_eq("has_glasses", criteria.has_glasses):
                match = False
            if not _bool_eq("has_bag", criteria.has_bag):
                match = False

            # 计算真实时间 & time range filter
            real_time_str = None
            timestamp = ped.get("timestamp", 0)
            if file_start_time and timestamp is not None:
                real_time = file_start_time + datetime.timedelta(seconds=timestamp)
                real_time_str = real_time.strftime("%H:%M:%S")
                if start_min is not None and end_min is not None:
                    cur_min = real_time.hour * 60 + real_time.minute
                    if not (start_min <= cur_min <= end_min):
                        match = False

            if match:
                matches.append(
                    SearchResult(
                        record_id=record.id,
                        file_id=record.media_file_id,
                        filename=record.filename,
                        is_video=bool(record.is_video),
                        duration=record.duration,
                        camera_location=record.camera_location or "未设置",
                        upload_time=record.upload_time.isoformat(),
                        real_time=real_time_str,
                        snippet_info=ped,
                    )
                )

    if criteria.dedup_person:
        by_person = {}
        without_person: List[SearchResult] = []
        for item in matches:
            snippet = item.snippet_info or {}
            person_id = snippet.get("person_id") or snippet.get("pedestrian_id")
            if not person_id:
                without_person.append(item)
                continue

            dedup_key = f"{item.file_id}:{person_id}"
            ts_raw = snippet.get("timestamp")
            try:
                ts = float(ts_raw)
            except Exception:
                ts = float("inf")

            prev = by_person.get(dedup_key)
            if prev is None:
                by_person[dedup_key] = (ts, item)
            else:
                prev_ts, _prev_item = prev
                if ts < prev_ts:
                    by_person[dedup_key] = (ts, item)

        matches = [v[1] for v in by_person.values()] + without_person

    max_results = criteria.max_results if isinstance(criteria.max_results, int) else 300
    if max_results <= 0:
        max_results = 300
    max_results = min(max_results, 1000)
    if len(matches) > max_results:
        matches = matches[:max_results]

    return matches


@router.post("/search", response_model=List[SearchResult])
def search_pedestrians(criteria: SearchRequest, db: Session = Depends(get_db)):
    return _search(criteria, db)


class NLSearchRequest(BaseModel):
    query: str
    file_id: Optional[int] = None
    camera_location: Optional[str] = None
    use_llm: int = 1
    cache: int = 1
    refresh: int = 0
    dedup_person: int = 1
    max_results: int = 300


@router.post("/search/nl")
def search_pedestrians_nl(req: NLSearchRequest, db: Session = Depends(get_db)):
    parsed = parse_nl_search_query(req.query, allow_llm=bool(req.use_llm))
    criteria_dict = parsed.get("criteria") or {}
    scope = {
        "query": req.query,
        "file_id": req.file_id,
        "camera_location": req.camera_location,
        "use_llm": bool(req.use_llm),
        "dedup_person": bool(req.dedup_person),
        "max_results": int(req.max_results),
        "criteria": criteria_dict,
    }
    cache_key = make_cache_key("nl_search", scope)

    if req.cache and not req.refresh:
        cached = db.query(InsightCache).filter(InsightCache.cache_key == cache_key).first()
        if cached and is_cache_fresh(cached.created_at):
            return {**(cached.response or {}), "cached": True}

    criteria = SearchRequest(**criteria_dict)
    criteria.file_id = req.file_id
    criteria.dedup_person = bool(req.dedup_person)
    criteria.max_results = int(req.max_results)
    if req.camera_location:
        criteria.camera_location = req.camera_location

    results = _search(criteria, db)
    payload = {
        "llm_used": bool(parsed.get("llm_used")),
        "cached": False,
        "query": req.query,
        "criteria": criteria.model_dump(exclude_none=True),
        "explanation": parsed.get("explanation") or "",
        "results": [r.model_dump() for r in results],
    }

    if req.cache:
        existing = db.query(InsightCache).filter(InsightCache.cache_key == cache_key).first()
        if existing:
            existing.response = payload
            existing.llm_used = 1 if payload.get("llm_used") else 0
        else:
            db.add(
                InsightCache(
                    cache_key=cache_key,
                    endpoint="nl_search",
                    scope=scope,
                    response=payload,
                    llm_used=1 if payload.get("llm_used") else 0,
                )
            )
        db.commit()

    return payload


class ImageSearchResponse(BaseModel):
    query_attributes: dict
    results: List[SearchResult]


@router.post("/search/by-image", response_model=ImageSearchResponse)
async def search_pedestrians_by_image(
    request: Request,
    image: UploadFile = File(...),
    file_id: Optional[int] = Form(None),
    top_k: int = Form(50),
    min_score: float = Form(0.20),
    db: Session = Depends(get_db),
):
    recognizer = getattr(request.app.state, "recognizer", None)
    if recognizer is None:
        raise HTTPException(status_code=500, detail="Recognizer unavailable")

    suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            shutil.copyfileobj(image.file, tmp)
    finally:
        try:
            image.file.close()
        except Exception:
            pass

    try:
        raw_people = recognizer.analyze(tmp_path)
        people = [p for p in (_normalize_recognition_item(x) for x in raw_people or []) if p]
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    if not people:
        return {"query_attributes": {}, "results": []}

    def _area(person):
        bbox = (person or {}).get("bbox", {}) or {}
        return int(bbox.get("width", 0) or 0) * int(bbox.get("height", 0) or 0)

    query_person = max(people, key=_area)
    query_attrs = dict((query_person.get("attributes") or {}))

    query = db.query(AnalysisRecord)
    if file_id is not None:
        query = query.filter(AnalysisRecord.media_file_id == file_id)
    candidate_records = query.order_by(AnalysisRecord.upload_time.desc()).limit(200).all()

    file_ids = set(r.media_file_id for r in candidate_records if r.media_file_id)
    file_start_times = {}
    if file_ids:
        files = db.query(MediaFile).filter(MediaFile.id.in_(file_ids)).all()
        for f in files:
            if f.start_time:
                file_start_times[f.id] = f.start_time

    scored = []
    for record in candidate_records:
        ped_list = record.results or []
        start_time = file_start_times.get(record.media_file_id)
        for ped in ped_list:
            if not isinstance(ped, dict):
                continue
            attrs = (ped.get("attributes") or {})
            score = _compute_attr_similarity(query_attrs, attrs)
            if score < min_score:
                continue

            real_time_str = None
            ts = ped.get("timestamp")
            if start_time is not None and ts is not None:
                try:
                    real_time = start_time + datetime.timedelta(seconds=float(ts))
                    real_time_str = real_time.strftime("%H:%M:%S")
                except Exception:
                    pass

            snippet = dict(ped)
            snippet["match_score"] = score
            scored.append(
                SearchResult(
                    record_id=record.id,
                    file_id=record.media_file_id,
                    filename=record.filename,
                    is_video=bool(record.is_video),
                    duration=record.duration,
                    camera_location=record.camera_location or "未设置",
                    upload_time=record.upload_time.isoformat(),
                    real_time=real_time_str,
                    snippet_info=snippet,
                )
            )

    best_by_person = {}
    without_person = []
    for item in scored:
        snippet = item.snippet_info or {}
        pid = snippet.get("person_id") or snippet.get("pedestrian_id")
        if not pid:
            without_person.append(item)
            continue
        key = f"{item.file_id}:{pid}"
        prev = best_by_person.get(key)
        cur_score = float(snippet.get("match_score", 0))
        if prev is None:
            best_by_person[key] = item
        else:
            prev_score = float((prev.snippet_info or {}).get("match_score", 0))
            if cur_score > prev_score:
                best_by_person[key] = item

    merged = list(best_by_person.values()) + without_person
    merged.sort(key=lambda x: float((x.snippet_info or {}).get("match_score", 0)), reverse=True)

    top_k = max(1, min(int(top_k), 200))
    merged = merged[:top_k]

    return {
        "query_attributes": query_attrs,
        "results": merged,
    }

