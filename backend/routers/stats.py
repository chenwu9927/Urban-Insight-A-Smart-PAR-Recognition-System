from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db, AnalysisRecord, MediaFile
from sqlalchemy import func
from typing import Optional, Literal
from collections import defaultdict
import datetime

router = APIRouter()

@router.get("/stats")
def get_stats(
    file_id: Optional[int] = Query(None, description="可选：指定文件ID进行过滤"),
    interval: int = Query(60, description="时间间隔（分钟），可选 1, 5, 30, 60"),
    date: Optional[str] = Query(None, description="可选：指定日期过滤，格式YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    """
    获取客流统计数据。
    - file_id: 可选，指定文件ID过滤
    - interval: 时间间隔（分钟），支持 1, 5, 30, 60
    - date: 可选，指定日期过滤（格式 YYYY-MM-DD）
    """
    # 解析日期参数
    filter_date = None
    if date:
        try:
            filter_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    # 验证 interval 参数
    if interval not in [1, 5, 30, 60]:
        interval = 60
    
    # 构建查询
    query = db.query(AnalysisRecord)
    if file_id is not None:
        query = query.filter(AnalysisRecord.media_file_id == file_id)
    
    records = query.all()
    
    total_analyses = len(records)
    total_pedestrians = sum(r.pedestrian_count or 0 for r in records)
    
    # 获取文件的开始时间映射
    file_start_times = {}
    if file_id:
        media_file = db.query(MediaFile).filter(MediaFile.id == file_id).first()
        if media_file and media_file.start_time:
            file_start_times[file_id] = media_file.start_time
    else:
        # 获取所有相关文件的开始时间
        file_ids = set(r.media_file_id for r in records if r.media_file_id)
        if file_ids:
            files = db.query(MediaFile).filter(MediaFile.id.in_(file_ids)).all()
            for f in files:
                if f.start_time:
                    file_start_times[f.id] = f.start_time
    
    # 收集所有行人数据
    all_pedestrians = []
    for record in records:
        if record.results:
            # 附加文件开始时间信息
            start_time = file_start_times.get(record.media_file_id)
            for ped in record.results:
                ped_copy = dict(ped)
                ped_copy['_start_time'] = start_time
                ped_copy['_file_id'] = record.media_file_id
                
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
    
    # 统计性别分布
    gender_counts = defaultdict(int)
    for ped in all_pedestrians:
        attrs = ped.get("attributes", {})
        gender = attrs.get("gender", "Unknown")
        gender_counts[gender] += 1
    
    gender_total = sum(gender_counts.values()) or 1
    gender_distribution = {
        k: round(v * 100 / gender_total, 1) 
        for k, v in gender_counts.items()
    }
    
    # 统计年龄分布
    age_counts = defaultdict(int)
    for ped in all_pedestrians:
        attrs = ped.get("attributes", {})
        age_group = attrs.get("age_group", "Unknown")
        age_counts[age_group] += 1
    
    age_total = sum(age_counts.values()) or 1
    age_distribution = {
        k: round(v * 100 / age_total, 1)
        for k, v in age_counts.items()
    }
    
    # 统计时间流量趋势
    interval_seconds = interval * 60
    
    # 判断是否使用真实时间（任何有 start_time 的都用真实时间）
    use_real_time = any(file_start_times.values())
    
    # 仪表盘模式：无 file_id，显示全天24小时（1小时间隔）
    is_dashboard_mode = file_id is None
    
    if use_real_time:
        time_counts = defaultdict(int)
        
        for ped in all_pedestrians:
            timestamp = ped.get("timestamp", 0)
            start_time = ped.get('_start_time')
            if start_time:
                real_time = start_time + datetime.timedelta(seconds=timestamp)
            else:
                real_time = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(seconds=timestamp)
            
            # 按间隔分组（基于当天开始时间）
            day_start = real_time.replace(hour=0, minute=0, second=0, microsecond=0)
            seconds_since_day_start = (real_time - day_start).total_seconds()
            slot = int(seconds_since_day_start // interval_seconds)
            time_counts[slot] += 1
        
        traffic_trend = []
        
        if is_dashboard_mode:
            # 仪表盘：显示全天24小时（使用1小时间隔）
            dashboard_interval = 60  # 固定1小时
            dashboard_slots = 24
            for slot in range(dashboard_slots):
                time_label = f"{slot:02d}:00"
                # 聚合该小时内的所有数据
                hour_count = 0
                slots_per_hour = 60 // interval
                for sub_slot in range(slot * slots_per_hour, (slot + 1) * slots_per_hour):
                    hour_count += time_counts.get(sub_slot, 0)
                traffic_trend.append({
                    "time": time_label,
                    "count": hour_count
                })
        else:
            # 客流分析：显示实际数据范围
            if time_counts:
                min_slot = min(time_counts.keys())
                max_slot = max(time_counts.keys())
                for slot in range(min_slot, max_slot + 1):
                    total_minutes = slot * interval
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    time_label = f"{hours:02d}:{minutes:02d}"
                    traffic_trend.append({
                        "time": time_label,
                        "count": time_counts[slot]
                    })
    else:
        # 按视频相对时间分组
        time_counts = defaultdict(int)
        max_timestamp = 0
        
        for ped in all_pedestrians:
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
                traffic_trend.append({
                    "time": time_label,
                    "count": time_counts[slot]
                })
    
    # 如果没有数据，返回空状态
    if not all_pedestrians:
        gender_distribution = {}
        age_distribution = {}
    
    # 计算存储占用
    total_size = db.query(func.sum(MediaFile.file_size)).scalar() or 0
    # 格式化存储大小
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
        "total_pedestrians": total_pedestrians,
        "gender_distribution": gender_distribution,
        "age_distribution": age_distribution,
        "traffic_trend": traffic_trend,
        "interval_minutes": interval,
        "storage_used": storage_used,
        "storage_bytes": total_size
    }
