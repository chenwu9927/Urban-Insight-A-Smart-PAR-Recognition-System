import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import SystemConfig, get_db
from .auth import User, require_admin_session_user

router = APIRouter(prefix="/settings", tags=["settings"])


class LLMConfigRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


class LLMConfigResponse(BaseModel):
    api_key_set: bool
    api_key_preview: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


def get_config(db: Session, key: str) -> Optional[str]:
    config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    return config.config_value if config else None


def set_config(db: Session, key: str, value: Optional[str]) -> None:
    config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    if config:
        config.config_value = value
    else:
        db.add(SystemConfig(config_key=key, config_value=value))
    db.commit()


def apply_llm_config_to_env(db: Session) -> None:
    api_key = get_config(db, "llm_api_key")
    base_url = get_config(db, "llm_base_url")
    model = get_config(db, "llm_model")

    if api_key:
        os.environ["LLM_API_KEY"] = api_key
    else:
        os.environ.pop("LLM_API_KEY", None)

    if base_url:
        os.environ["LLM_BASE_URL"] = base_url
    else:
        os.environ.pop("LLM_BASE_URL", None)

    if model:
        os.environ["LLM_MODEL"] = model
    else:
        os.environ.pop("LLM_MODEL", None)


@router.get("/llm", response_model=LLMConfigResponse)
async def get_llm_config(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_session_user),
):
    api_key = get_config(db, "llm_api_key")
    base_url = get_config(db, "llm_base_url")
    model = get_config(db, "llm_model")

    if api_key and len(api_key) > 8:
        api_key_preview = f"{api_key[:7]}...{api_key[-4:]}"
    elif api_key:
        api_key_preview = "***"
    else:
        api_key_preview = None

    return LLMConfigResponse(
        api_key_set=bool(api_key),
        api_key_preview=api_key_preview,
        base_url=base_url or "https://api.longcat.chat/openai",
        model=model or "LongCat-Flash-Lite",
    )


@router.post("/llm")
async def save_llm_config(
    config: LLMConfigRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_session_user),
):
    if config.api_key is not None:
        set_config(db, "llm_api_key", config.api_key or None)

    if config.base_url is not None:
        set_config(db, "llm_base_url", config.base_url or None)

    if config.model is not None:
        set_config(db, "llm_model", config.model or None)

    apply_llm_config_to_env(db)
    return {"success": True, "message": "模型配置已保存"}


@router.post("/llm/test")
async def test_llm_connection(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_session_user),
):
    apply_llm_config_to_env(db)

    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        return {"success": False, "message": "未配置 API Key"}

    try:
        from ..services.llm_insights import call_chat_completions_json

        result = call_chat_completions_json(
            system_prompt='你是一个助手。请只返回 JSON：{"status":"ok"}',
            user_payload={"test": True},
            temperature=0.0,
        )
        return {"success": True, "message": "连接成功", "response": result}
    except Exception as exc:
        return {"success": False, "message": f"连接失败: {exc}"}
