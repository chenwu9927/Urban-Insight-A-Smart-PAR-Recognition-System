import datetime
import hashlib
import os

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./urban_insight.db")
SCHEMA_INIT_LOCK_ID = 2026032201

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
    role = Column(String, default="user")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class MediaFile(Base):
    __tablename__ = "media_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_path = Column(String)
    file_type = Column(String)
    upload_time = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="uploaded")
    start_time = Column(DateTime, nullable=True)
    file_size = Column(Integer, default=0)


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id = Column(Integer, primary_key=True, index=True)
    media_file_id = Column(Integer, index=True)
    filename = Column(String, index=True)
    upload_time = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    pedestrian_count = Column(Integer)
    results = Column(JSON)
    is_video = Column(Integer, default=0)
    duration = Column(Integer, default=0)
    camera_location = Column(String, default="Unknown")


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, index=True)
    status = Column(String, default="queued")
    result_record_id = Column(Integer, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class InsightCache(Base):
    __tablename__ = "insight_cache"

    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String, unique=True, index=True)
    endpoint = Column(String, index=True)
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
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String, unique=True, index=True)
    config_value = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def register_agent_models() -> None:
    """Import agent models lazily so shared metadata includes agent tables."""
    import agent.models  # noqa: F401


def _ensure_default_admin(db_session) -> None:
    admin = db_session.query(User).filter(User.username == "admin").first()
    if admin:
        return

    db_session.add(
        User(
            username="admin",
            password_hash=hash_password("123456"),
            role="admin",
        )
    )
    db_session.flush()
    print("Created default admin account")


def init_db():
    register_agent_models()

    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": SCHEMA_INIT_LOCK_ID},
            )
            try:
                Base.metadata.create_all(bind=connection)
                locked_session = sessionmaker(
                    autocommit=False,
                    autoflush=False,
                    bind=connection,
                )()
                try:
                    _ensure_default_admin(locked_session)
                    locked_session.flush()
                finally:
                    locked_session.close()
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": SCHEMA_INIT_LOCK_ID},
                )
        return

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _ensure_default_admin(db)
        db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
