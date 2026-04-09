from __future__ import annotations

import json
import os
import hashlib
import datetime
import urllib.request
from typing import Any, Dict, Optional


def _post_json(url: str, *, headers: Dict[str, str], payload: Dict[str, Any], timeout_s: int = 30) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _chat_completions_url(base_url: str) -> str:
    normalized = (base_url or "https://api.openai.com/v1").rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    if normalized.endswith("/openai"):
        return f"{normalized}/v1/chat/completions"
    return f"{normalized}/chat/completions"


def call_chat_completions_json(
    *,
    system_prompt: str,
    user_payload: Dict[str, Any],
    temperature: float = 0.2,
    timeout_s: int = 45,
) -> Dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY not configured")

    base_url = (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL") or "gpt-4o-mini"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    resp = _post_json(
        _chat_completions_url(base_url),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        payload=payload,
        timeout_s=timeout_s,
    )
    content = resp["choices"][0]["message"]["content"]
    return json.loads(content)


def make_cache_key(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_ttl_seconds() -> int:
    try:
        return max(0, int(os.getenv("LLM_CACHE_TTL_SECONDS") or "3600"))
    except Exception:
        return 3600


def is_cache_fresh(created_at: Optional[datetime.datetime]) -> bool:
    if not created_at:
        return False
    ttl = cache_ttl_seconds()
    if ttl <= 0:
        return False
    return (datetime.datetime.utcnow() - created_at).total_seconds() <= ttl


def _derive_findings(stats: Dict[str, Any]) -> Dict[str, Any]:
    traffic = stats.get("traffic_trend") or []
    top_periods = sorted(
        [{"time": t.get("time"), "count": t.get("count", 0)} for t in traffic if isinstance(t, dict)],
        key=lambda x: x.get("count", 0),
        reverse=True,
    )[:3]

    gender_dist = stats.get("gender_distribution") or {}
    age_dist = stats.get("age_distribution") or {}
    dominant_gender = max(gender_dist.items(), key=lambda kv: kv[1])[0] if gender_dist else None
    dominant_age = max(age_dist.items(), key=lambda kv: kv[1])[0] if age_dist else None

    return {
        "top_periods": top_periods,
        "dominant_gender": dominant_gender,
        "dominant_age_group": dominant_age,
    }


def _fallback_insights(stats: Dict[str, Any], *, scope: Dict[str, Any]) -> Dict[str, Any]:
    derived = _derive_findings(stats)
    total = stats.get("total_pedestrians", 0)
    analyses = stats.get("total_analyses", 0)
    top_periods = derived.get("top_periods") or []

    summary_parts = [f"共完成 {analyses} 次分析，识别行人 {total} 人。"]
    if derived.get("dominant_gender"):
        summary_parts.append(f"性别占比最高为 {derived['dominant_gender']}。")
    if derived.get("dominant_age_group"):
        summary_parts.append(f"年龄层占比最高为 {derived['dominant_age_group']}。")
    if top_periods and top_periods[0].get("count", 0) > 0:
        summary_parts.append(f"客流峰值出现在 {top_periods[0]['time']}（{top_periods[0]['count']} 人）。")

    key_findings = []
    if top_periods:
        key_findings.append("客流Top时段：" + "，".join([f"{p['time']}({p['count']})" for p in top_periods if p.get("time")]))
    if stats.get("storage_used"):
        key_findings.append(f"当前存储占用：{stats['storage_used']}。")

    recommendations = [
        "如用于安防/运营，建议对峰值时段设置告警阈值并进行人力调度。",
        "建议定期清理无用媒体文件并开启分层存储以控制占用。",
    ]
    questions = [
        "是否需要按摄像头点位/区域对比峰值时段差异？",
        "是否需要进一步分析服饰颜色/背包等属性与时间段的关联？",
    ]

    return {
        "llm_used": False,
        "scope": scope,
        "stats": stats,
        "summary": " ".join(summary_parts),
        "key_findings": key_findings,
        "anomalies": [],
        "recommendations": recommendations,
        "questions": questions,
        "derived": derived,
    }


def generate_insights(stats: Dict[str, Any], *, scope: Dict[str, Any], allow_llm: bool = True) -> Dict[str, Any]:
    """
    Generate insights from computed stats.
    - If LLM is configured (LLM_API_KEY), uses OpenAI-compatible Chat Completions API.
    - Otherwise returns a deterministic fallback.
    """
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not allow_llm or not api_key:
        return _fallback_insights(stats, scope=scope)

    derived = _derive_findings(stats)

    system_prompt = (
        "你是城市客流与行人属性数据分析助手。"
        "你会收到一段统计数据(JSON)，请输出严格的JSON对象，必须包含以下键："
        "summary(字符串)、key_findings(字符串数组)、anomalies(字符串数组)、recommendations(字符串数组)、questions(字符串数组)。"
        "如果没有内容，也必须输出空数组或空字符串。"
        "不要输出多余文本，不要使用Markdown。"
    )

    try:
        parsed = call_chat_completions_json(
            system_prompt=system_prompt,
            user_payload={"scope": scope, "stats": stats, "derived": derived},
            temperature=0.2,
        )
        # Normalize missing keys to keep UI stable
        parsed.setdefault("summary", "")
        parsed.setdefault("key_findings", [])
        parsed.setdefault("anomalies", [])
        parsed.setdefault("recommendations", [])
        parsed.setdefault("questions", [])
        return {
            "llm_used": True,
            "scope": scope,
            "stats": stats,
            "derived": derived,
            **parsed,
        }
    except Exception:
        # LLM failure should never break the UI; return fallback with some context.
        return _fallback_insights(stats, scope=scope)


def answer_question(
    stats: Dict[str, Any],
    *,
    scope: Dict[str, Any],
    question: str,
    allow_llm: bool = True,
) -> Dict[str, Any]:
    """
    Answer a natural-language question grounded in `stats`.
    Returns a JSON object for direct UI rendering.
    """
    question = (question or "").strip()
    if not question:
        return {
            "llm_used": False,
            "scope": scope,
            "stats": stats,
            "question": "",
            "answer": "请输入问题。",
            "related_findings": [],
            "suggested_next_questions": [],
        }

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not allow_llm or not api_key:
        # Simple grounded fallback: reuse deterministic insights summary.
        insights = generate_insights(stats, scope=scope, allow_llm=False)
        return {
            "llm_used": False,
            "scope": scope,
            "stats": stats,
            "question": question,
            "answer": f"当前未配置 LLM Key，无法进行问答推理。你可以先参考摘要：{insights.get('summary','')}",
            "related_findings": insights.get("key_findings", []) or [],
            "suggested_next_questions": insights.get("questions", []) or [],
        }

    derived = _derive_findings(stats)

    system_prompt = (
        "你是城市客流与行人属性数据分析助手。"
        "你会收到统计数据(JSON)与用户问题。"
        "请只基于给定数据回答，不要编造不存在的数据；如无法回答请说明原因并给出需要的额外数据。"
        "输出严格JSON对象，必须包含键："
        "answer(字符串)、related_findings(字符串数组)、suggested_next_questions(字符串数组)。"
        "不要输出多余文本，不要使用Markdown。"
    )

    try:
        parsed = call_chat_completions_json(
            system_prompt=system_prompt,
            user_payload={"scope": scope, "stats": stats, "derived": derived, "question": question},
            temperature=0.2,
        )
        parsed.setdefault("answer", "")
        parsed.setdefault("related_findings", [])
        parsed.setdefault("suggested_next_questions", [])
        return {
            "llm_used": True,
            "scope": scope,
            "stats": stats,
            "question": question,
            **parsed,
        }
    except Exception:
        return answer_question(stats, scope=scope, question=question, allow_llm=False)


def parse_nl_search_query(query: str, *, allow_llm: bool = True) -> Dict[str, Any]:
    """
    Parse a natural-language retrieval query into structured search criteria.
    Output values should be compatible with SearchRequest in `backend/routers/search.py`.
    """
    query = (query or "").strip()
    if not query:
        return {"llm_used": False, "criteria": {}, "explanation": "空查询。"}

    # Heuristic fallback (fast + deterministic)
    def heuristic() -> Dict[str, Any]:
        q = query.lower()
        criteria: Dict[str, Any] = {}

        # gender
        if "female" in q or "女" in query:
            criteria["gender"] = "Female"
        elif "male" in q or "男" in query:
            criteria["gender"] = "Male"

        # age groups in this project typically: Child/Teenager/Adult/Senior (mock), or Child/Adult/Senior
        if any(k in query for k in ["老人", "老年", "60", "senior"]):
            criteria["age_group"] = "Senior"
        elif any(k in query for k in ["儿童", "小孩", "child"]):
            criteria["age_group"] = "Child"
        elif any(k in query for k in ["青年", "成人", "adult"]):
            criteria["age_group"] = "Adult"

        colors = {
            "red": "Red",
            "blue": "Blue",
            "black": "Black",
            "white": "White",
            "grey": "Grey",
            "gray": "Grey",
            "green": "Green",
            "yellow": "Yellow",
            "khaki": "Khaki",
            "红": "Red",
            "蓝": "Blue",
            "黑": "Black",
            "白": "White",
            "灰": "Grey",
            "绿": "Green",
            "黄": "Yellow",
            "卡其": "Khaki",
        }
        for k, v in colors.items():
            if k in q or k in query:
                criteria["upper_color"] = v
                break

        if any(k in query for k in ["背包", "backpack"]):
            criteria["has_backpack"] = True
        if any(k in query for k in ["帽", "hat"]):
            criteria["has_hat"] = True
        if any(k in query for k in ["眼镜", "glasses"]):
            criteria["has_glasses"] = True
        if any(k in query for k in ["手提包", "包", "handbag", "bag"]):
            criteria["has_bag"] = True

        if any(k in query for k in ["正面", "front"]):
            criteria["orientation"] = "Front"
        elif any(k in query for k in ["侧面", "side"]):
            criteria["orientation"] = "Side"
        elif any(k in query for k in ["背面", "back"]):
            criteria["orientation"] = "Back"

        # time: support "HH:MM-HH:MM"
        import re

        m = re.search(r"(\d{1,2}:\d{2})\s*[-~到至]\s*(\d{1,2}:\d{2})", query)
        if m:
            criteria["start_time"] = m.group(1)
            criteria["end_time"] = m.group(2)

        return criteria

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not allow_llm or not api_key:
        c = heuristic()
        return {"llm_used": False, "criteria": c, "explanation": "未启用LLM，使用规则解析。"}

    system_prompt = (
        "你是行人属性检索助手。"
        "请将用户的自然语言检索需求解析为严格JSON对象，必须包含键：criteria(对象)、explanation(字符串)。"
        "criteria 仅允许以下字段（没有就不要输出该字段）："
        "gender(Male/Female), age_group(Child/Teenager/Adult/Senior), upper_color(Red/Blue/Black/White/Grey/Green/Yellow/Khaki), "
        "has_backpack(true/false), has_hat(true/false), has_glasses(true/false), has_bag(true/false), orientation(Front/Side/Back), "
        "start_time(HH:MM), end_time(HH:MM)."
        "不要输出多余文本，不要使用Markdown。"
    )
    try:
        parsed = call_chat_completions_json(
            system_prompt=system_prompt,
            user_payload={"query": query},
            temperature=0.0,
        )
        criteria = parsed.get("criteria") or {}
        if not isinstance(criteria, dict):
            criteria = {}
        explanation = parsed.get("explanation") if isinstance(parsed.get("explanation"), str) else ""
        return {"llm_used": True, "criteria": criteria, "explanation": explanation}
    except Exception:
        c = heuristic()
        return {"llm_used": False, "criteria": c, "explanation": "LLM解析失败，已降级为规则解析。"}


def generate_brief(stats: Dict[str, Any], *, scope: Dict[str, Any], allow_llm: bool = True) -> Dict[str, Any]:
    """
    Produce a daily brief and alert items for dashboard.
    """
    def fallback() -> Dict[str, Any]:
        traffic = stats.get("traffic_trend") or []
        counts = [t.get("count", 0) for t in traffic if isinstance(t, dict)]
        avg = (sum(counts) / len(counts)) if counts else 0
        peak = max(counts) if counts else 0
        peak_time = None
        if traffic and peak:
            for t in traffic:
                if isinstance(t, dict) and t.get("count", 0) == peak:
                    peak_time = t.get("time")
                    break

        alerts = []
        if avg and peak >= avg * 2:
            alerts.append({"level": "high", "title": "客流峰值偏高", "detail": f"峰值 {peak}，约为均值 {avg:.1f} 的 2 倍以上（{peak_time or '-'}）。"})
        if stats.get("storage_bytes", 0) >= 1024 * 1024 * 1024:
            alerts.append({"level": "medium", "title": "存储占用较高", "detail": f"当前占用 {stats.get('storage_used')}，建议清理或归档。"})

        summary = f"{scope.get('date') or '今日'}：分析 {stats.get('total_analyses', 0)} 次，识别 {stats.get('total_pedestrians', 0)} 人。"
        key_findings = []
        if peak_time:
            key_findings.append(f"峰值时段：{peak_time}（{peak} 人）")
        if stats.get("gender_distribution"):
            top_gender = max(stats["gender_distribution"].items(), key=lambda kv: kv[1])[0]
            key_findings.append(f"主要性别：{top_gender}")
        if stats.get("age_distribution"):
            top_age = max(stats["age_distribution"].items(), key=lambda kv: kv[1])[0]
            key_findings.append(f"主要年龄层：{top_age}")

        return {
            "llm_used": False,
            "scope": scope,
            "stats": stats,
            "summary": summary,
            "key_findings": key_findings,
            "anomalies": [],
            "recommendations": [
                "关注峰值时段并结合点位进行人流疏导或安保调度。",
                "定期清理历史媒体/分析记录，控制存储占用。",
            ],
            "alerts": alerts,
        }

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not allow_llm or not api_key:
        return fallback()

    system_prompt = (
        "你是城市运营数据助手。"
        "你会收到当天统计数据(JSON)。请输出严格JSON对象，必须包含键："
        "summary(字符串)、key_findings(字符串数组)、anomalies(字符串数组)、recommendations(字符串数组)、alerts(对象数组)。"
        "alerts 的每个对象必须包含 level(low/medium/high), title, detail。"
        "只基于数据，不要编造。不要输出多余文本，不要使用Markdown。"
    )
    try:
        parsed = call_chat_completions_json(
            system_prompt=system_prompt,
            user_payload={"scope": scope, "stats": stats, "derived": _derive_findings(stats)},
            temperature=0.2,
        )
        parsed.setdefault("summary", "")
        parsed.setdefault("key_findings", [])
        parsed.setdefault("anomalies", [])
        parsed.setdefault("recommendations", [])
        parsed.setdefault("alerts", [])
        return {"llm_used": True, "scope": scope, "stats": stats, **parsed}
    except Exception:
        return fallback()


def generate_record_report(record_summary: Dict[str, Any], *, allow_llm: bool = True) -> Dict[str, Any]:
    """
    Generate a report for a single analysis record.
    """
    def fallback() -> Dict[str, Any]:
        meta = record_summary.get("meta") or {}
        return {
            "llm_used": False,
            "record_id": meta.get("record_id"),
            "summary": f"文件 {meta.get('filename')}：识别 {meta.get('pedestrian_count', 0)} 人。",
            "key_findings": record_summary.get("highlights") or [],
            "anomalies": [],
            "recommendations": [
                "如需更强的文字报告，请配置 LLM_API_KEY。",
                "可进一步按时段/点位拆分对比。",
            ],
        }

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not allow_llm or not api_key:
        return fallback()

    system_prompt = (
        "你是安防/运营分析报告助手。"
        "你会收到单次分析记录的摘要数据(JSON)，请输出严格JSON对象，必须包含键："
        "summary(字符串)、key_findings(字符串数组)、anomalies(字符串数组)、recommendations(字符串数组)。"
        "只基于数据，不要编造。不要输出多余文本，不要使用Markdown。"
    )
    try:
        parsed = call_chat_completions_json(
            system_prompt=system_prompt,
            user_payload={"record_summary": record_summary},
            temperature=0.2,
            timeout_s=12,
        )
        parsed.setdefault("summary", "")
        parsed.setdefault("key_findings", [])
        parsed.setdefault("anomalies", [])
        parsed.setdefault("recommendations", [])
        meta = record_summary.get("meta") or {}
        return {"llm_used": True, "record_id": meta.get("record_id"), **parsed}
    except Exception:
        return fallback()
