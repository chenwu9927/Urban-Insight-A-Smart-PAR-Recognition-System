"""
系统设置 API 路由
提供 LLM 配置等系统设置的读取和保存功能
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import os

from ..database import get_db, SystemConfig

router = APIRouter(prefix="/settings", tags=["settings"])


class LLMConfigRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


class LLMConfigResponse(BaseModel):
    api_key_set: bool  # 不返回实际密钥，只返回是否已设置
    api_key_preview: Optional[str] = None  # 密钥的脱敏预览
    base_url: Optional[str] = None
    model: Optional[str] = None


def get_config(db: Session, key: str) -> Optional[str]:
    """从数据库获取配置值"""
    config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    return config.config_value if config else None


def set_config(db: Session, key: str, value: Optional[str]):
    """设置或更新配置值"""
    config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    if config:
        config.config_value = value
    else:
        config = SystemConfig(config_key=key, config_value=value)
        db.add(config)
    db.commit()


def apply_llm_config_to_env(db: Session):
    """将数据库中的 LLM 配置应用到环境变量"""
    api_key = get_config(db, "llm_api_key")
    base_url = get_config(db, "llm_base_url")
    model = get_config(db, "llm_model")
    
    if api_key:
        os.environ["LLM_API_KEY"] = api_key
    if base_url:
        os.environ["LLM_BASE_URL"] = base_url
    if model:
        os.environ["LLM_MODEL"] = model


@router.get("/llm", response_model=LLMConfigResponse)
async def get_llm_config(db: Session = Depends(get_db)):
    """获取 LLM 配置（API Key 脱敏）"""
    api_key = get_config(db, "llm_api_key")
    base_url = get_config(db, "llm_base_url")
    model = get_config(db, "llm_model")
    
    # 生成密钥预览（如 sk-xxxx...xxxx）
    api_key_preview = None
    if api_key and len(api_key) > 8:
        api_key_preview = api_key[:7] + "..." + api_key[-4:]
    elif api_key:
        api_key_preview = "***"
    
    return LLMConfigResponse(
        api_key_set=bool(api_key),
        api_key_preview=api_key_preview,
        base_url=base_url or "https://api.longcat.chat/openai",
        model=model or "LongCat-Flash-Lite"
    )


@router.post("/llm")
async def save_llm_config(config: LLMConfigRequest, db: Session = Depends(get_db)):
    """保存 LLM 配置"""
    if config.api_key is not None:
        # 空字符串表示清除配置
        set_config(db, "llm_api_key", config.api_key if config.api_key else None)
    
    if config.base_url is not None:
        set_config(db, "llm_base_url", config.base_url if config.base_url else None)
    
    if config.model is not None:
        set_config(db, "llm_model", config.model if config.model else None)
    
    # 立即应用到环境变量
    apply_llm_config_to_env(db)
    
    return {"success": True, "message": "LLM 配置已保存"}


@router.post("/llm/test")
async def test_llm_connection(db: Session = Depends(get_db)):
    """测试 LLM 连接"""
    # 确保环境变量是最新的
    apply_llm_config_to_env(db)
    
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        return {"success": False, "message": "未配置 API Key"}
    
    try:
        from ..services.llm_insights import call_chat_completions_json
        # 简单测试调用
        result = call_chat_completions_json(
            system_prompt="你是一个助手。请回复一个简单的 JSON: {\"status\": \"ok\"}",
            user_payload={"test": True},
            temperature=0.0
        )
        return {"success": True, "message": "连接成功", "response": result}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)}"}
