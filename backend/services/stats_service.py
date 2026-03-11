from __future__ import annotations

from collections import defaultdict
import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import AnalysisRecord, MediaFile


def compute_stats(
    db: Session,
    *,
    file_id: Optional[int] = None,
    interval: int = 60,
    date: Optional[str] = None,
    dedup: bool = True,
):
    """
    Compute traffic/attribute stats from AnalysisRecord results.
    Mirrors the output contract of `GET /stats`.
    """
    # 解析日期参数
    filter_date = None
    if date:
        try:
            filter_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            filter_date = None

    # 验证 interval 参数
    if interval not in [1, 5, 30, 60]:
        interval = 60

    # 构建查询
    query = db.query(AnalysisRecord)
    if file_id is not None:
        query = query.filter(AnalysisRecord.media_file_id == file_id)

    records = query.all()

    total_analyses = len(records)

    # 获取文件的开始时间映射
    file_start_times = {}
    if file_id:
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if media_file and media_file.start_time:
            file_start_times[file_id] = media_file.start_time
    else:
        file_ids = set(r.media_file_id for r in records if r.media_file_id)
        if file_ids:
            files = db.query(MediaFile).filter(MediaFile.id.in_(file_ids)).all()
            for f in files:
                if f.start_time:
                    file_start_times[f.id] = f.start_time

    # 收集所有行人数据
    all_pedestrians = []
    for record in records:
        if not record.results:
            continue

        start_time = file_start_times.get(record.media_file_id)
        for ped in record.results:
            ped_copy = dict(ped)
            ped_copy["_start_time"] = start_time
            ped_copy["_file_id"] = record.media_file_id

            # 如果有日期过滤，检查行人时间是否在指定日期
            if filter_date and start_time:
                timestamp = ped.get("timestamp", 0)
                real_time = start_time + datetime.timedelta(seconds=timestamp)
                if real_time.date() != filter_date:
                    continue
            elif filter_date:
                # 没有 start_time 但有日期过滤，跳过
                continue

            all_pedestrians.append(ped_copy)

    def _person_key(ped):
        return ped.get("person_id") or ped.get("pedestrian_id")

    def _time_rank(ped):
        rt = ped.get("_real_time")
        if isinstance(rt, datetime.datetime):
            return ("real", rt.timestamp())
        return ("ts", float(ped.get("timestamp", 0.0)))

    def _prefer(new_rank, old_rank):
        if new_rank[0] == old_rank[0]:
            return new_rank[1] < old_rank[1]
        return new_rank[0] == "real"

    unique_peds = []
    unique_persons = 0
    if dedup and all_pedestrians:
        best_by_person = {}
        for ped in all_pedestrians:
            key = _person_key(ped)
            if not key:
                key = f"anon_{len(best_by_person) + 1}"
            rank = _time_rank(ped)
            if key not in best_by_person or _prefer(rank, best_by_person[key]["rank"]):
                best_by_person[key] = {"ped": ped, "rank": rank}
        unique_peds = [v["ped"] for v in best_by_person.values()]
        unique_persons = len(unique_peds)
    else:
        unique_peds = all_pedestrians
        unique_persons = len(all_pedestrians)

    # 统计性别分布
    gender_counts = defaultdict(int)
    for ped in unique_peds:
        attrs = ped.get("attributes", {})
        gender = attrs.get("gender", "Unknown")
        gender_counts[gender] += 1

    gender_total = sum(gender_counts.values()) or 1
    gender_distribution = {k: round(v * 100 / gender_total, 1) for k, v in gender_counts.items()}

    # 统计年龄分布
    age_counts = defaultdict(int)
    for ped in unique_peds:
        attrs = ped.get("attributes", {})
        age_group = attrs.get("age_group", "Unknown")
        age_counts[age_group] += 1

    age_total = sum(age_counts.values()) or 1
    age_distribution = {k: round(v * 100 / age_total, 1) for k, v in age_counts.items()}

    # 统计时间流量趋势
    interval_seconds = interval * 60
    use_real_time = any(file_start_times.values())
    is_dashboard_mode = file_id is None

    if use_real_time:
        time_counts = defaultdict(int)
        for ped in unique_peds:
            timestamp = ped.get("timestamp", 0)
            start_time = ped.get("_start_time")
            if start_time:
                real_time = start_time + datetime.timedelta(seconds=timestamp)
            else:
                real_time = (
                    datetime.datetime.now()
                    .replace(hour=0, minute=0, second=0, microsecond=0)
                    + datetime.timedelta(seconds=timestamp)
                )

            day_start = real_time.replace(hour=0, minute=0, second=0, microsecond=0)
            seconds_since_day_start = (real_time - day_start).total_seconds()
            slot = int(seconds_since_day_start // interval_seconds)
            time_counts[slot] += 1

        traffic_trend = []
        if is_dashboard_mode:
            dashboard_slots = 24
            for slot in range(dashboard_slots):
                time_label = f"{slot:02d}:00"
                hour_count = 0
                slots_per_hour = 60 // interval
                for sub_slot in range(slot * slots_per_hour, (slot + 1) * slots_per_hour):
                    hour_count += time_counts.get(sub_slot, 0)
                traffic_trend.append({"time": time_label, "count": hour_count})
        else:
            if time_counts:
                min_slot = min(time_counts.keys())
                max_slot = max(time_counts.keys())
                for slot in range(min_slot, max_slot + 1):
                    total_minutes = slot * interval
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    time_label = f"{hours:02d}:{minutes:02d}"
                    traffic_trend.append({"time": time_label, "count": time_counts[slot]})
    else:
        time_counts = defaultdict(int)
        max_timestamp = 0

        for ped in unique_peds:
            timestamp = ped.get("timestamp", 0)
            max_timestamp = max(max_timestamp, timestamp)
            slot = int(timestamp // interval_seconds)
            time_counts[slot] += 1

        traffic_trend = []
        if max_timestamp > 0:
            total_slots = int(max_timestamp // interval_seconds) + 1
            for slot in range(total_slots):
                total_minutes = slot * interval
                hours = total_minutes // 60
                minutes = total_minutes % 60
                time_label = f"{hours:02d}:{minutes:02d}"
                traffic_trend.append({"time": time_label, "count": time_counts[slot]})

    if not unique_peds:
        gender_distribution = {}
        age_distribution = {}

    total_size = db.query(func.sum(MediaFile.file_size)).scalar() or 0
    if total_size >= 1024 * 1024 * 1024:
        storage_used = f"{total_size / (1024 * 1024 * 1024):.1f} GB"
    elif total_size >= 1024 * 1024:
        storage_used = f"{total_size / (1024 * 1024):.1f} MB"
    elif total_size >= 1024:
        storage_used = f"{total_size / 1024:.1f} KB"
    else:
        storage_used = f"{total_size} B"

    return {
        "total_analyses": total_analyses,
        "total_pedestrians": unique_persons,
        "unique_persons": unique_persons,
        "dedup": bool(dedup),
        "gender_distribution": gender_distribution,
        "age_distribution": age_distribution,
        "traffic_trend": traffic_trend,
        "interval_minutes": interval,
        "storage_used": storage_used,
        "storage_bytes": total_size,
    }
