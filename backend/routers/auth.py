import base64
import datetime
import hashlib
import hmac
import json
import os
import time
from typing import List, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import User, get_db, hash_password

router = APIRouter()

SESSION_COOKIE_NAME = "session_token"
SESSION_TTL_SECONDS = int(os.getenv("AUTH_SESSION_TTL_SECONDS", "86400"))
SESSION_SECRET = (
    os.getenv("AUTH_SESSION_SECRET")
    or os.getenv("SECRET_KEY")
    or "urban-insight-session-secret"
).encode("utf-8")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(payload_segment: str) -> str:
    signature = hmac.new(SESSION_SECRET, payload_segment.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(signature)


def _build_session_token(user: User) -> str:
    payload = {
        "uid": user.id,
        "usr": user.username,
        "rol": user.role,
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    payload_segment = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature_segment = _sign(payload_segment)
    return f"{payload_segment}.{signature_segment}"


def _decode_session_payload(session_token: Optional[str]) -> Optional[dict[str, object]]:
    if not session_token or "." not in session_token:
        return None

    payload_segment, signature_segment = session_token.split(".", 1)
    expected_signature = _sign(payload_segment)
    if not hmac.compare_digest(signature_segment, expected_signature):
        return None

    try:
        payload = json.loads(_b64decode(payload_segment).decode("utf-8"))
    except Exception:
        return None

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at <= int(time.time()):
        return None

    return payload


def _load_session_user(
    db: Session,
    session_token: Optional[str],
) -> User:
    payload = _decode_session_payload(session_token)
    if not payload:
        raise HTTPException(status_code=401, detail="未登录")

    user_id = payload.get("uid")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=401, detail="会话无效")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="会话已失效")
    return user


def require_current_session_user(
    session_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    return _load_session_user(db, session_token)


def require_admin_session_user(user: User = Depends(require_current_session_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
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
    user = db.query(User).filter(User.username == request.username).first()
    if not user or user.password_hash != hash_password(request.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = _build_session_token(user)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=SESSION_TTL_SECONDS,
        samesite="lax",
    )

    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
        },
    }


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, samesite="lax")
    return {"ok": True}


@router.get("/auth/me")
def get_current_user(
    token: Optional[str] = None,
    session_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = _load_session_user(db, token or session_token)
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
    }


@router.get("/users", response_model=List[UserInfo])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_session_user),
):
    return db.query(User).all()


@router.post("/users", response_model=UserInfo)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_session_user),
):
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    new_user = User(
        username=user.username,
        password_hash=hash_password(user.password),
        role=user.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_session_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.username == "admin":
        raise HTTPException(status_code=400, detail="不能删除管理员账户")

    db.delete(user)
    db.commit()
    return {"ok": True}


@router.put("/users/{user_id}/password")
def change_password(
    user_id: int,
    request: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_session_user),
):
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="无权修改其他用户密码")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.password_hash = hash_password(request.password)
    db.commit()
    return {"ok": True}
