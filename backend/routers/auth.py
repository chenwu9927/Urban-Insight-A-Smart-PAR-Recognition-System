from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from ..database import get_db, User, hash_password
import datetime
import secrets

router = APIRouter()

# 简单的 session 存储（生产环境应使用 Redis）
sessions = {}

class LoginRequest(BaseModel):
    username: str
    password: str

class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime.datetime

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"

@router.post("/auth/login")
def login(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(User).filter(User.username == request.username).first()
    if not user or user.password_hash != hash_password(request.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    # 创建 session token
    token = secrets.token_hex(32)
    sessions[token] = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role
    }
    
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400)
    
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role
        }
    }

@router.post("/auth/logout")
def logout(response: Response):
    """登出"""
    response.delete_cookie("session_token")
    return {"ok": True}

@router.get("/auth/me")
def get_current_user(token: Optional[str] = None, db: Session = Depends(get_db)):
    """获取当前登录用户，通过 query param token"""
    if not token or token not in sessions:
        raise HTTPException(status_code=401, detail="未登录")
    
    session = sessions[token]
    return {
        "id": session["user_id"],
        "username": session["username"],
        "role": session["role"]
    }

# 用户管理 API
@router.get("/users", response_model=List[UserInfo])
def list_users(db: Session = Depends(get_db)):
    """获取所有用户"""
    users = db.query(User).all()
    return users

@router.post("/users", response_model=UserInfo)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """创建新用户"""
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    new_user = User(
        username=user.username,
        password_hash=hash_password(user.password),
        role=user.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """删除用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.username == "admin":
        raise HTTPException(status_code=400, detail="不能删除管理员账户")
    
    db.delete(user)
    db.commit()
    return {"ok": True}

@router.put("/users/{user_id}/password")
def change_password(user_id: int, request: LoginRequest, db: Session = Depends(get_db)):
    """修改密码"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    user.password_hash = hash_password(request.password)
    db.commit()
    return {"ok": True}
