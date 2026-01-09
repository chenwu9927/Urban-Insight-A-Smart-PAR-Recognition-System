from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import hashlib

SQLALCHEMY_DATABASE_URL = "sqlite:///./urban_insight.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
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

def hash_password(password: str) -> str:
    """简单的密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
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

