from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.memory_store import AgentMemoryStore
from backend.services.llm_insights import call_chat_completions_json


ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}
ALLOWED_STRATEGY_TYPES = {
    "monitoring",
    "investigation",
    "hardening",
    "policy",
    "optimization",
    "capacity",
    "coordination",
}


@dataclass(frozen=True)
class DistilledGoal:
    title: str
    summary: str
    prompt: str
    risk_level: str
    strategy_type: str
    confidence: float | None
    evidence: tuple[str, ...]
    cluster_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class DistilledRiskCluster:
    label: str
    summary: str
    severity: str
    confidence: float | None
    recommended_strategy: str | None
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class MemoryDistillationResult:
    used_llm: bool
    goals: tuple[DistilledGoal, ...]
    memory_digest: str
    distillation_summary: str | None = None
    strategy_summary: str | None = None
    strategy_directives: tuple[str, ...] = ()
    risk_clusters: tuple[DistilledRiskCluster, ...] = ()
    strategy_feedback_summary: str | None = None
    feedback_status_counts: dict[str, int] | None = None
    error: str | None = None


class AgentMemoryDistiller:
    def __init__(self, workspace_dir: str | Path) -> None:
        self.memory = AgentMemoryStore(workspace_dir)

    def distill_goals(
        self,
        *,
        lookback_days: int = 3,
        max_candidates: int = 3,
        max_memory_chars: int = 12000,
        min_confidence: float = 0.55,
    ) -> MemoryDistillationResult:
        memory_packet = self._build_memory_packet(
            lookback_days=lookback_days,
            max_memory_chars=max_memory_chars,
        )
        if not memory_packet["long_term_memory"] and not memory_packet["recent_daily_notes"]:
            return MemoryDistillationResult(
                used_llm=False,
                goals=(),
                memory_digest="memory-empty",
                error="memory_empty",
            )

        system_prompt = (
            "You are distilling proactive operations goals for an always-on security and analytics agent.\n"
            "You will receive long-term memory and recent daily notes from the workspace.\n"
            "You will also receive recent strategy feedback produced by prior autonomous runs.\n"
            "Extract only outputs that are justified by recurring signals, explicit long-term goals, unresolved risks, durable operational strategy, or repeated strategy adjustment signals.\n"
            "Return strict JSON with keys: summary, strategy_summary, strategy_directives, risk_clusters, goals.\n"
            "strategy_directives must be an array of short durable operating strategies.\n"
            "risk_clusters must be an array of objects with keys: label, summary, severity, confidence, recommended_strategy, evidence.\n"
            "goals must be an array of objects with keys: title, summary, prompt, risk_level, strategy_type, confidence, evidence, cluster_labels.\n"
            "risk_level must be one of: low, medium, high, critical.\n"
            "severity must be one of: low, medium, high, critical.\n"
            "strategy_type must be one of: monitoring, investigation, hardening, policy, optimization, capacity, coordination.\n"
            "confidence must be a number from 0 to 1.\n"
            "evidence must be an array of short strings grounded in the provided memory.\n"
            "cluster_labels must reference labels from risk_clusters when relevant.\n"
            f"Return at most {max(1, int(max_candidates))} goals.\n"
            "Do not invent facts. Prefer fewer high-quality goals over many weak ones."
        )

        try:
            parsed = call_chat_completions_json(
                system_prompt=system_prompt,
                user_payload=memory_packet,
                temperature=0.1,
            )
            goals = self._normalize_goals(
                parsed.get("goals"),
                max_candidates=max_candidates,
                min_confidence=min_confidence,
            )
            risk_clusters = self._normalize_risk_clusters(parsed.get("risk_clusters"))
            return MemoryDistillationResult(
                used_llm=True,
                goals=tuple(goals),
                memory_digest=memory_packet["memory_digest"],
                distillation_summary=self._normalize_text(parsed.get("summary"), max_chars=500),
                strategy_summary=self._normalize_text(parsed.get("strategy_summary"), max_chars=700),
                strategy_directives=tuple(self._normalize_string_list(parsed.get("strategy_directives"), limit=6, max_chars=220)),
                risk_clusters=tuple(risk_clusters),
                strategy_feedback_summary=self._normalize_text(memory_packet.get("recent_strategy_feedback"), max_chars=700),
                feedback_status_counts=dict(memory_packet.get("strategy_feedback_status_counts") or {}),
            )
        except Exception as exc:
            return MemoryDistillationResult(
                used_llm=False,
                goals=(),
                memory_digest=memory_packet["memory_digest"],
                strategy_feedback_summary=self._normalize_text(memory_packet.get("recent_strategy_feedback"), max_chars=700),
                feedback_status_counts=dict(memory_packet.get("strategy_feedback_status_counts") or {}),
                error=str(exc),
            )

    def _build_memory_packet(self, *, lookback_days: int, max_memory_chars: int) -> dict[str, Any]:
        safe_chars = max(2000, int(max_memory_chars))
        long_term = self.memory.read_long_term().strip()
        recent_notes = self.memory.get_recent_daily_notes(days=lookback_days).strip()
        feedback_snapshot = self.memory.summarize_recent_strategy_feedback(days=max(lookback_days, 3))

        long_term_budget = max(1000, safe_chars // 3)
        feedback_budget = max(800, safe_chars // 5)
        notes_budget = safe_chars - long_term_budget - feedback_budget

        trimmed_long_term = self._trim_text(long_term, long_term_budget)
        trimmed_recent_notes = self._trim_text(recent_notes, notes_budget)
        trimmed_feedback = self._trim_text(str(feedback_snapshot.get("summary_text") or "").strip(), feedback_budget)

        return {
            "memory_digest": json.dumps(
                {
                    "lookback_days": lookback_days,
                    "long_term_chars": len(trimmed_long_term),
                    "recent_note_chars": len(trimmed_recent_notes),
                    "strategy_feedback_chars": len(trimmed_feedback),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "lookback_days": lookback_days,
            "long_term_memory": trimmed_long_term,
            "recent_daily_notes": trimmed_recent_notes,
            "recent_strategy_feedback": trimmed_feedback,
            "strategy_feedback_status_counts": dict(feedback_snapshot.get("status_counts") or {}),
            "strategy_feedback_directives": list(feedback_snapshot.get("directives") or []),
            "strategy_feedback_risk_labels": list(feedback_snapshot.get("risk_labels") or []),
        }

    @staticmethod
    def _trim_text(value: str, max_chars: int) -> str:
        text = (value or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max(0, max_chars - 21)].rstrip() + "\n...[truncated for distillation]"

    def _normalize_goals(
        self,
        raw_goals: Any,
        *,
        max_candidates: int,
        min_confidence: float,
    ) -> list[DistilledGoal]:
        if not isinstance(raw_goals, list):
            return []

        normalized: list[DistilledGoal] = []
        seen: set[str] = set()

        for item in raw_goals:
            if not isinstance(item, dict):
                continue

            title = " ".join(str(item.get("title") or "").split()).strip()
            summary = " ".join(str(item.get("summary") or "").split()).strip()
            if not title or not summary:
                continue

            confidence = self._normalize_confidence(item.get("confidence"))
            if confidence is not None and confidence < min_confidence:
                continue

            risk_level = str(item.get("risk_level") or "medium").strip().lower()
            if risk_level not in ALLOWED_RISK_LEVELS:
                risk_level = "medium"

            strategy_type = str(item.get("strategy_type") or "investigation").strip().lower()
            if strategy_type not in ALLOWED_STRATEGY_TYPES:
                strategy_type = "investigation"

            evidence = self._normalize_evidence(item.get("evidence"))
            cluster_labels = tuple(self._normalize_string_list(item.get("cluster_labels"), limit=4, max_chars=80))
            prompt = self._normalize_prompt(
                item.get("prompt"),
                summary=summary,
                risk_level=risk_level,
                strategy_type=strategy_type,
                evidence=evidence,
            )

            dedup_key = f"{title.lower()}::{summary.lower()}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            normalized.append(
                DistilledGoal(
                    title=title[:255],
                    summary=summary,
                    prompt=prompt,
                    risk_level=risk_level,
                    strategy_type=strategy_type,
                    confidence=confidence,
                    evidence=tuple(evidence),
                    cluster_labels=cluster_labels,
                )
            )
            if len(normalized) >= max(1, int(max_candidates)):
                break

        return normalized

    def _normalize_risk_clusters(self, raw_clusters: Any) -> list[DistilledRiskCluster]:
        if not isinstance(raw_clusters, list):
            return []

        normalized: list[DistilledRiskCluster] = []
        seen: set[str] = set()
        for item in raw_clusters:
            if not isinstance(item, dict):
                continue

            label = self._normalize_text(item.get("label"), max_chars=120)
            summary = self._normalize_text(item.get("summary"), max_chars=400)
            if not label or not summary:
                continue

            severity = str(item.get("severity") or "medium").strip().lower()
            if severity not in ALLOWED_RISK_LEVELS:
                severity = "medium"

            dedup_key = f"{label.lower()}::{summary.lower()}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            normalized.append(
                DistilledRiskCluster(
                    label=label,
                    summary=summary,
                    severity=severity,
                    confidence=self._normalize_confidence(item.get("confidence")),
                    recommended_strategy=self._normalize_text(item.get("recommended_strategy"), max_chars=220),
                    evidence=tuple(self._normalize_evidence(item.get("evidence"))),
                )
            )
            if len(normalized) >= 6:
                break

        return normalized

    @staticmethod
    def _normalize_confidence(value: Any) -> float | None:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _normalize_evidence(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        evidence: list[str] = []
        for entry in value:
            text = " ".join(str(entry or "").split()).strip()
            if text:
                evidence.append(text[:240])
        return evidence[:5]

    @staticmethod
    def _normalize_string_list(value: Any, *, limit: int, max_chars: int) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        seen: set[str] = set()
        for entry in value:
            text = AgentMemoryDistiller._normalize_text(entry, max_chars=max_chars)
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(text)
            if len(items) >= limit:
                break
        return items

    @staticmethod
    def _normalize_text(value: Any, *, max_chars: int) -> str | None:
        text = " ".join(str(value or "").split()).strip()
        if not text:
            return None
        return text[:max_chars]

    @staticmethod
    def _normalize_prompt(
        raw_prompt: Any,
        *,
        summary: str,
        risk_level: str,
        strategy_type: str,
        evidence: list[str],
    ) -> str:
        prompt = " ".join(str(raw_prompt or "").split()).strip()
        if prompt:
            return prompt

        evidence_block = ""
        if evidence:
            evidence_block = "\nEvidence:\n- " + "\n- ".join(evidence[:5])

        return (
            "A proactive goal was distilled from workspace memory. "
            "Assess the current platform state, validate the evidence, and choose the first safe next steps.\n\n"
            f"Goal: {summary}\n"
            f"Risk level: {risk_level}\n"
            f"Strategy type: {strategy_type}"
            f"{evidence_block}"
        ).strip()
