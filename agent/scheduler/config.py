from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class SchedulerSettings:
    def __init__(self) -> None:
        self.control_plane_url = os.getenv("AGENT_CONTROL_PLANE_URL", "http://agent-control-plane:8000").rstrip("/")
        self.poll_seconds = max(2, _env_int("AGENT_SCHEDULER_POLL_SECONDS", 10))
        self.dispatch_limit = max(1, _env_int("AGENT_SCHEDULER_DISPATCH_LIMIT", 20))
        self.goal_sweep_limit = max(1, _env_int("AGENT_GOAL_SWEEP_LIMIT", 20))
        self.goal_verification_cooldown_minutes = max(1, _env_int("AGENT_GOAL_VERIFICATION_COOLDOWN_MINUTES", 10))
        self.goal_recovery_minutes = max(15, _env_int("AGENT_GOAL_RECOVERY_MINUTES", 180))
        self.memory_boost_lookback_days = max(1, _env_int("AGENT_MEMORY_BOOST_LOOKBACK_DAYS", 2))
        self.memory_boost_cooldown_minutes = max(1, _env_int("AGENT_MEMORY_BOOST_COOLDOWN_MINUTES", 30))
        self.proactive_goal_lookback_days = max(1, _env_int("AGENT_PROACTIVE_GOAL_LOOKBACK_DAYS", 3))
        self.proactive_goal_recurrence_threshold = max(2, _env_int("AGENT_PROACTIVE_GOAL_RECURRENCE_THRESHOLD", 2))
        self.proactive_goal_llm_distillation_enabled = os.getenv("AGENT_PROACTIVE_GOAL_LLM_DISTILLATION_ENABLED", "1").strip() not in {"0", "false", "False"}
        self.proactive_goal_llm_candidate_limit = max(1, _env_int("AGENT_PROACTIVE_GOAL_LLM_CANDIDATE_LIMIT", 3))
        self.proactive_goal_memory_max_chars = max(2000, _env_int("AGENT_PROACTIVE_GOAL_MEMORY_MAX_CHARS", 12000))
        try:
            self.proactive_goal_min_distilled_confidence = float(os.getenv("AGENT_PROACTIVE_GOAL_MIN_DISTILLED_CONFIDENCE", "0.55"))
        except ValueError:
            self.proactive_goal_min_distilled_confidence = 0.55
        self.proactive_goal_ttl_seconds = max(300, _env_int("AGENT_PROACTIVE_GOAL_TTL_SECONDS", 21600))
        self.proactive_goal_priority_dispatch_enabled = os.getenv("AGENT_PROACTIVE_GOAL_PRIORITY_DISPATCH_ENABLED", "1").strip() not in {"0", "false", "False"}
        self.proactive_goal_priority_dispatch_limit = max(1, _env_int("AGENT_PROACTIVE_GOAL_PRIORITY_DISPATCH_LIMIT", 10))
        self.proactive_goal_feedback_sweep_enabled = os.getenv("AGENT_PROACTIVE_GOAL_FEEDBACK_SWEEP_ENABLED", "1").strip() not in {"0", "false", "False"}
        self.proactive_goal_feedback_sweep_limit = max(1, _env_int("AGENT_PROACTIVE_GOAL_FEEDBACK_SWEEP_LIMIT", 10))
