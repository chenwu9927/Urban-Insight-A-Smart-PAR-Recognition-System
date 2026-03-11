import datetime
import hashlib
import os

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./urban_insight.db")

engine_kwargs = {"pool_pre_ping": True}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String, default="user")  # admin/user
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class MediaFile(Base):
    __tablename__ = "media_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_path = Column(String)
    file_type = Column(String) # image/video
    upload_time = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="uploaded") # uploaded, analyzed, error
    start_time = Column(DateTime, nullable=True)  # 视频实际开始时间
    file_size = Column(Integer, default=0)  # 文件大小（字节）

class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id = Column(Integer, primary_key=True, index=True)
    media_file_id = Column(Integer, index=True) # ForeignKey to MediaFile
    filename = Column(String, index=True)
    upload_time = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    pedestrian_count = Column(Integer)
    results = Column(JSON) # Store full JSON result
    
    # New fields for Phase 3
    is_video = Column(Integer, default=0) # 0=Image, 1=Video
    duration = Column(Integer, default=0) # Seconds
    camera_location = Column(String, default="Unknown") # e.g. "North Gate"


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, index=True)
    status = Column(String, default="queued")  # queued, running, completed, failed
    result_record_id = Column(Integer, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class InsightCache(Base):
    __tablename__ = "insight_cache"

    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String, unique=True, index=True)
    endpoint = Column(String, index=True)  # "insights" | "ask"
    scope = Column(JSON)
    response = Column(JSON)
    llm_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, unique=True, index=True)
    report = Column(JSON)
    llm_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class SystemConfig(Base):
    """系统配置表，用于存储 LLM API 等配置信息"""
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String, unique=True, index=True)  # e.g. "llm_api_key", "llm_base_url"
    config_value = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

def hash_password(password: str) -> str:
    """简单的密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()


def register_agent_models() -> None:
    """Import agent models lazily so shared metadata includes agent tables."""
    import agent.models  # noqa: F401

def init_db():
    register_agent_models()
    Base.metadata.create_all(bind=engine)
    # 初始化默认管理员账户
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                password_hash=hash_password("123456"),
                role="admin"
            )
            db.add(admin)
            db.commit()
            print("Created default admin account")
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

