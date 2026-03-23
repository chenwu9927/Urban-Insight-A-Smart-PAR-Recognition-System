from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from agent.control_plane.services import create_message, create_run, ensure_goal, register_dedup_event, utcnow
from agent.memory_distillation import AgentMemoryDistiller, DistilledRiskCluster
from agent.memory_store import AgentMemoryStore
from agent.models import AgentGoal, AgentSession


ACTIVE_GOAL_STATUSES = {"planned", "running", "replanning", "blocked", "pending_verification", "verifying", "recovering"}
RISK_WEIGHTS = {"low": 0.4, "medium": 0.9, "high": 1.6, "critical": 2.4}
SOURCE_WEIGHTS = {
    "long_term_memory": 0.4,
    "recurring_memory_pattern": 0.8,
    "llm_memory_distillation": 1.0,
}


@dataclass(frozen=True)
class ProactiveGoalCandidate:
    dedup_key: str
    title: str
    summary: str
    prompt: str
    source: str
    distillation_method: str = "rule"
    risk_level: str = "medium"
    strategy_type: str = "investigation"
    confidence: float | None = None
    evidence: tuple[str, ...] = ()
    cluster_labels: tuple[str, ...] = ()
    priority_score: float = 0.0
    priority_tier: str = "normal"


@dataclass(frozen=True)
class ProactiveCandidateBatch:
    candidates: tuple[ProactiveGoalCandidate, ...]
    rule_candidates: int = 0
    llm_candidates: int = 0
    llm_used: bool = False
    llm_error: str | None = None
    distillation_summary: str | None = None
    strategy_summary: str | None = None
    strategy_directives: tuple[str, ...] = ()
    risk_clusters: tuple[dict[str, object], ...] = ()
    strategy_feedback_summary: str | None = None
    feedback_status_counts: dict[str, int] = field(default_factory=dict)
    feedback_priority_boost: int = 0
    priority_tier: str = "normal"
    priority_boost: int = 0
    priority_score: float = 0.0


class ProactiveGoalPlanner:
    INCIDENT_RULES = (
        (
            "analysis backlog alert",
            "Investigate persistent analysis backlog",
            "Repeated analysis backlog alerts were found in memory. Assess the backlog pattern, identify likely causes, and propose the next safe monitoring or remediation steps.",
        ),
        (
            "analysis failure alert",
            "Investigate recurring analysis failures",
            "Repeated analysis failure alerts were found in memory. Assess whether there is a persistent analysis failure pattern and propose the next safe follow-up steps.",
        ),
        (
            "approval timeout alert",
            "Reduce recurring approval timeout incidents",
            "Repeated approval timeout alerts were found in memory. Assess why approvals keep stalling and propose the next safe follow-up steps.",
        ),
    )

    def __init__(self, workspace_dir: str | Path) -> None:
        self.memory = AgentMemoryStore(workspace_dir)

    def extract_candidate_batch(
        self,
        *,
        lookback_days: int = 3,
        recurrence_threshold: int = 2,
        use_llm_distillation: bool = True,
        distilled_limit: int = 3,
        max_memory_chars: int = 12000,
        min_distilled_confidence: float = 0.55,
    ) -> ProactiveCandidateBatch:
        recent_notes = self.memory.get_recent_daily_notes(days=lookback_days)
        long_term = self.memory.read_long_term()
        rule_candidates: list[ProactiveGoalCandidate] = []
        llm_candidates: list[ProactiveGoalCandidate] = []
        llm_error: str | None = None
        llm_used = False
        distillation_summary: str | None = None
        strategy_summary: str | None = None
        strategy_directives: tuple[str, ...] = ()
        risk_clusters: tuple[dict[str, object], ...] = ()
        feedback_snapshot = self.memory.summarize_recent_strategy_feedback(days=max(lookback_days, 3))

        rule_candidates.extend(self._extract_explicit_memory_goals(long_term))
        rule_candidates.extend(self._extract_recurring_incidents(recent_notes, recurrence_threshold=recurrence_threshold))
        if use_llm_distillation:
            llm_result = self._extract_llm_distilled_goals(
                lookback_days=lookback_days,
                distilled_limit=distilled_limit,
                max_memory_chars=max_memory_chars,
                min_distilled_confidence=min_distilled_confidence,
            )
            llm_candidates = llm_result["candidates"]
            llm_error = llm_result["error"]
            llm_used = llm_result["used_llm"]
            distillation_summary = llm_result["distillation_summary"]
            strategy_summary = llm_result["strategy_summary"]
            strategy_directives = llm_result["strategy_directives"]
            risk_clusters = llm_result["risk_clusters"]
            if not feedback_snapshot.get("summary_text") and llm_result.get("strategy_feedback_summary"):
                feedback_snapshot = {
                    **feedback_snapshot,
                    "summary_text": llm_result.get("strategy_feedback_summary"),
                    "status_counts": dict(llm_result.get("feedback_status_counts") or {}),
                }

        prioritized = self._prioritize_candidates(
            [*rule_candidates, *llm_candidates],
            risk_clusters=risk_clusters,
            feedback_snapshot=feedback_snapshot,
        )
        merged = tuple(self._dedupe_candidates(prioritized))
        priority_score, priority_tier, priority_boost, feedback_priority_boost = self._compute_batch_priority(
            merged,
            risk_clusters=risk_clusters,
            feedback_snapshot=feedback_snapshot,
        )
        adjusted_candidates = tuple(
            self._apply_batch_priority(
                candidate,
                priority_tier=priority_tier,
                priority_boost=priority_boost + feedback_priority_boost,
            )
            for candidate in merged
        )
        return ProactiveCandidateBatch(
            candidates=adjusted_candidates,
            rule_candidates=len(rule_candidates),
            llm_candidates=len(llm_candidates),
            llm_used=llm_used,
            llm_error=llm_error,
            distillation_summary=distillation_summary,
            strategy_summary=strategy_summary,
            strategy_directives=strategy_directives,
            risk_clusters=risk_clusters,
            strategy_feedback_summary=str(feedback_snapshot.get("summary_text") or "").strip() or None,
            feedback_status_counts=dict(feedback_snapshot.get("status_counts") or {}),
            feedback_priority_boost=feedback_priority_boost,
            priority_tier=priority_tier,
            priority_boost=priority_boost,
            priority_score=priority_score,
        )

    def extract_candidates(
        self,
        *,
        lookback_days: int = 3,
        recurrence_threshold: int = 2,
        use_llm_distillation: bool = True,
        distilled_limit: int = 3,
        max_memory_chars: int = 12000,
        min_distilled_confidence: float = 0.55,
    ) -> list[ProactiveGoalCandidate]:
        batch = self.extract_candidate_batch(
            lookback_days=lookback_days,
            recurrence_threshold=recurrence_threshold,
            use_llm_distillation=use_llm_distillation,
            distilled_limit=distilled_limit,
            max_memory_chars=max_memory_chars,
            min_distilled_confidence=min_distilled_confidence,
        )
        return list(batch.candidates)

    def materialize_candidates(
        self,
        db: Session,
        *,
        candidates: list[ProactiveGoalCandidate],
        ttl_seconds: int = 6 * 3600,
        batch: ProactiveCandidateBatch | None = None,
    ) -> dict[str, object]:
        run_ids: list[str] = []
        goal_ids: list[str] = []
        deduped = 0
        batch_context = self._build_batch_context(batch)

        for candidate in candidates:
            active_goal = (
                db.query(AgentGoal)
                .filter(AgentGoal.summary == candidate.summary, AgentGoal.status.in_(ACTIVE_GOAL_STATUSES))
                .first()
            )
            if active_goal is not None:
                deduped += 1
                continue

            accepted = register_dedup_event(
                db,
                dedup_key=f"proactive-goal:{candidate.dedup_key}",
                category="proactive_goal",
                scope=candidate.source,
                payload={"summary": candidate.summary, "priority_tier": candidate.priority_tier},
                ttl_seconds=ttl_seconds,
            )
            if not accepted:
                deduped += 1
                continue

            candidate_meta = self._candidate_meta(candidate)
            session = AgentSession(
                kind="goal",
                title=candidate.title,
                status="active",
                source="memory",
                state_patch={
                    "proactive_goal_source": candidate.source,
                    "proactive_goal_meta": candidate_meta,
                    "proactive_distillation": batch_context,
                },
            )
            db.add(session)
            db.flush()
            message = create_message(
                db,
                session_id=session.id,
                role="system",
                content={
                    "text": candidate.prompt,
                    "proactive_goal": True,
                    "source": candidate.source,
                    "summary": candidate.summary,
                    **candidate_meta,
                    "distillation_context": batch_context,
                },
                text_preview=candidate.summary[:500],
            )
            run = create_run(
                db,
                session_id=session.id,
                trigger_message_id=message.id,
                schedule_mode="proactive",
                input_payload={
                    "action": "agent.chat",
                    "params": {"question": candidate.prompt, "auto_plan": True},
                    "auto_dispatch_followups": True,
                    "proactive_goal": True,
                    "goal_summary_hint": candidate.summary,
                    "proactive_goal_meta": candidate_meta,
                    "proactive_distillation": batch_context,
                },
                scheduled_at=utcnow(),
            )
            goal = ensure_goal(
                db,
                root_run=run,
                title=candidate.title,
                summary=candidate.summary,
                auto_replan=True,
                meta={
                    "source": candidate.source,
                    "proactive": True,
                    **candidate_meta,
                    "distillation_context": batch_context,
                },
            )
            run_ids.append(run.id)
            goal_ids.append(goal.id)

            daily_note_lines = [
                "Created proactive goal from memory.",
                "",
                f"Summary: {candidate.summary}",
                f"Source: {candidate.source}",
                f"Method: {candidate.distillation_method}",
                f"Risk level: {candidate.risk_level}",
                f"Strategy type: {candidate.strategy_type}",
                f"Priority tier: {candidate.priority_tier}",
                f"Priority score: {candidate.priority_score:.2f}",
                f"Confidence: {candidate.confidence if candidate.confidence is not None else '--'}",
            ]
            if batch_context.get("strategy_summary"):
                daily_note_lines.extend(["", f"Strategy summary: {batch_context['strategy_summary']}"])
            if batch_context.get("strategy_feedback_summary"):
                daily_note_lines.extend(["", f"Strategy feedback: {batch_context['strategy_feedback_summary']}"])
            self.memory.append_daily_note(
                "\n".join(daily_note_lines),
                heading=f"proactive goal | {goal.id}",
            )

        return {
            "scanned": len(candidates),
            "candidates": len(candidates),
            "created": len(goal_ids),
            "deduped": deduped,
            "run_ids": run_ids,
            "goal_ids": goal_ids,
        }

    def _extract_explicit_memory_goals(self, long_term: str) -> list[ProactiveGoalCandidate]:
        candidates: list[ProactiveGoalCandidate] = []
        for line in (long_term or "").splitlines():
            text = line.strip()
            if not text.startswith("-"):
                continue
            normalized = text.lstrip("-").strip()
            lower = normalized.lower()
            if lower.startswith("goal:"):
                summary = normalized.split(":", 1)[1].strip()
            elif lower.startswith("long-term goal:"):
                summary = normalized.split(":", 1)[1].strip()
            elif normalized.startswith("长期目标:") or normalized.startswith("长期目标："):
                parts = re.split(r"[:：]", normalized, maxsplit=1)
                summary = parts[1].strip() if len(parts) == 2 else ""
            else:
                summary = ""

            if not summary:
                continue

            candidates.append(
                ProactiveGoalCandidate(
                    dedup_key=self._slug(f"goal:{summary}"),
                    title=summary[:255],
                    summary=summary,
                    prompt=(
                        "A long-term operational goal was recorded in memory. "
                        "Assess current platform state and start the first safe steps for this goal.\n\n"
                        f"Goal: {summary}"
                    ),
                    source="long_term_memory",
                    strategy_type="coordination",
                    risk_level="medium",
                )
            )
        return candidates

    def _extract_recurring_incidents(self, recent_notes: str, *, recurrence_threshold: int) -> list[ProactiveGoalCandidate]:
        text = (recent_notes or "").lower()
        candidates: list[ProactiveGoalCandidate] = []
        if not text.strip():
            return candidates

        for keyword, title, prompt in self.INCIDENT_RULES:
            count = text.count(keyword)
            if count < max(2, recurrence_threshold):
                continue
            summary = f"{title} ({count} recurring signals in recent memory)"
            candidates.append(
                ProactiveGoalCandidate(
                    dedup_key=self._slug(f"incident:{keyword}"),
                    title=title,
                    summary=summary,
                    prompt=prompt,
                    source="recurring_memory_pattern",
                    strategy_type="investigation",
                    risk_level="high",
                    evidence=(f"Recurring keyword '{keyword}' appeared {count} times in recent notes.",),
                )
            )
        return candidates

    def _extract_llm_distilled_goals(
        self,
        *,
        lookback_days: int,
        distilled_limit: int,
        max_memory_chars: int,
        min_distilled_confidence: float,
    ) -> dict[str, object]:
        distiller = AgentMemoryDistiller(self.memory.workspace_dir)
        result = distiller.distill_goals(
            lookback_days=lookback_days,
            max_candidates=distilled_limit,
            max_memory_chars=max_memory_chars,
            min_confidence=min_distilled_confidence,
        )
        serialized_clusters = tuple(self._serialize_risk_cluster(cluster) for cluster in result.risk_clusters)
        if not result.goals:
            return {
                "candidates": [],
                "used_llm": result.used_llm,
                "error": result.error,
                "distillation_summary": result.distillation_summary,
                "strategy_summary": result.strategy_summary,
                "strategy_directives": result.strategy_directives,
                "risk_clusters": serialized_clusters,
                "strategy_feedback_summary": result.strategy_feedback_summary,
                "feedback_status_counts": dict(result.feedback_status_counts or {}),
            }

        candidates: list[ProactiveGoalCandidate] = []
        for index, goal in enumerate(result.goals, start=1):
            candidates.append(
                ProactiveGoalCandidate(
                    dedup_key=self._slug(f"llm:{goal.title}:{goal.summary}:{index}"),
                    title=goal.title,
                    summary=goal.summary,
                    prompt=goal.prompt,
                    source="llm_memory_distillation",
                    distillation_method="llm_assisted",
                    risk_level=goal.risk_level,
                    strategy_type=goal.strategy_type,
                    confidence=goal.confidence,
                    evidence=tuple(goal.evidence),
                    cluster_labels=tuple(goal.cluster_labels),
                )
            )
        return {
            "candidates": candidates,
            "used_llm": result.used_llm,
            "error": result.error,
            "distillation_summary": result.distillation_summary,
            "strategy_summary": result.strategy_summary,
            "strategy_directives": result.strategy_directives,
            "risk_clusters": serialized_clusters,
            "strategy_feedback_summary": result.strategy_feedback_summary,
            "feedback_status_counts": dict(result.feedback_status_counts or {}),
        }

    def _prioritize_candidates(
        self,
        candidates: list[ProactiveGoalCandidate],
        *,
        risk_clusters: tuple[dict[str, object], ...],
        feedback_snapshot: dict[str, object],
    ) -> list[ProactiveGoalCandidate]:
        prioritized = [
            self._apply_candidate_priority(
                candidate,
                risk_clusters=risk_clusters,
                feedback_snapshot=feedback_snapshot,
            )
            for candidate in candidates
        ]
        prioritized.sort(key=lambda candidate: (-candidate.priority_score, candidate.title.lower(), candidate.summary.lower()))
        return prioritized

    def _apply_candidate_priority(
        self,
        candidate: ProactiveGoalCandidate,
        *,
        risk_clusters: tuple[dict[str, object], ...],
        feedback_snapshot: dict[str, object],
    ) -> ProactiveGoalCandidate:
        score = RISK_WEIGHTS.get(candidate.risk_level, 0.9)
        score += SOURCE_WEIGHTS.get(candidate.source, 0.3)
        score += max(0.0, candidate.confidence or 0.0)
        if candidate.evidence:
            score += min(0.6, 0.12 * len(candidate.evidence))
        if candidate.distillation_method == "llm_assisted":
            score += 0.3

        cluster_bonus = 0.0
        matched_clusters = set(label.lower() for label in candidate.cluster_labels)
        for cluster in risk_clusters:
            label = str(cluster.get("label") or "").strip().lower()
            if not label:
                continue
            if label in matched_clusters:
                cluster_bonus = max(cluster_bonus, self._cluster_score(cluster))
        score += cluster_bonus
        score += self._feedback_candidate_bonus(candidate, feedback_snapshot=feedback_snapshot)

        priority_tier = self._priority_tier_from_score(score)
        return ProactiveGoalCandidate(
            **{**candidate.__dict__, "priority_score": round(score, 3), "priority_tier": priority_tier}
        )

    def _compute_batch_priority(
        self,
        candidates: tuple[ProactiveGoalCandidate, ...] | list[ProactiveGoalCandidate],
        *,
        risk_clusters: tuple[dict[str, object], ...],
        feedback_snapshot: dict[str, object],
    ) -> tuple[float, str, int, int]:
        candidate_score = max((candidate.priority_score for candidate in candidates), default=0.0)
        cluster_score = max((self._cluster_score(cluster) for cluster in risk_clusters), default=0.0)
        feedback_priority_boost = self._feedback_priority_boost(feedback_snapshot)
        combined_score = round(max(candidate_score, cluster_score) + (0.25 * feedback_priority_boost), 3)
        priority_tier = self._priority_tier_from_score(combined_score)
        priority_boost = {"normal": 0, "elevated": 1, "urgent": 2}.get(priority_tier, 0)
        return combined_score, priority_tier, priority_boost, feedback_priority_boost

    def _apply_batch_priority(
        self,
        candidate: ProactiveGoalCandidate,
        *,
        priority_tier: str,
        priority_boost: int,
    ) -> ProactiveGoalCandidate:
        if priority_boost <= 0:
            return candidate
        adjusted_score = round(candidate.priority_score + (0.15 * priority_boost), 3)
        candidate_tier = priority_tier if priority_tier == "urgent" else candidate.priority_tier
        return ProactiveGoalCandidate(
            **{**candidate.__dict__, "priority_score": adjusted_score, "priority_tier": candidate_tier}
        )

    def _build_batch_context(self, batch: ProactiveCandidateBatch | None) -> dict[str, object]:
        if batch is None:
            return {}
        return {
            "distillation_summary": batch.distillation_summary,
            "strategy_summary": batch.strategy_summary,
            "strategy_directives": list(batch.strategy_directives),
            "risk_clusters": [dict(cluster) for cluster in batch.risk_clusters],
            "strategy_feedback_summary": batch.strategy_feedback_summary,
            "feedback_status_counts": dict(batch.feedback_status_counts),
            "feedback_priority_boost": batch.feedback_priority_boost,
            "priority_tier": batch.priority_tier,
            "priority_boost": batch.priority_boost,
            "priority_score": batch.priority_score,
        }

    @staticmethod
    def _candidate_meta(candidate: ProactiveGoalCandidate) -> dict[str, object]:
        return {
            "distillation_method": candidate.distillation_method,
            "risk_level": candidate.risk_level,
            "strategy_type": candidate.strategy_type,
            "confidence": candidate.confidence,
            "evidence": list(candidate.evidence),
            "cluster_labels": list(candidate.cluster_labels),
            "priority_score": candidate.priority_score,
            "priority_tier": candidate.priority_tier,
        }

    @staticmethod
    def _serialize_risk_cluster(cluster: DistilledRiskCluster) -> dict[str, object]:
        return {
            "label": cluster.label,
            "summary": cluster.summary,
            "severity": cluster.severity,
            "confidence": cluster.confidence,
            "recommended_strategy": cluster.recommended_strategy,
            "evidence": list(cluster.evidence),
        }

    @staticmethod
    def _cluster_score(cluster: dict[str, object]) -> float:
        severity = str(cluster.get("severity") or "medium").strip().lower()
        confidence = cluster.get("confidence")
        try:
            confidence_value = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence_value = 0.5
        return RISK_WEIGHTS.get(severity, 0.9) * (0.6 + (0.4 * confidence_value))

    @staticmethod
    def _priority_tier_from_score(score: float) -> str:
        if score >= 2.7:
            return "urgent"
        if score >= 1.6:
            return "elevated"
        return "normal"

    @staticmethod
    def _feedback_candidate_bonus(
        candidate: ProactiveGoalCandidate,
        *,
        feedback_snapshot: dict[str, object],
    ) -> float:
        counts = feedback_snapshot.get("status_counts") or {}
        try:
            needs_adjustment = max(0, int(counts.get("needs_adjustment") or 0))
            adapted = max(0, int(counts.get("adapted") or 0))
            validated = max(0, int(counts.get("validated") or 0))
        except (TypeError, ValueError):
            needs_adjustment = adapted = validated = 0

        text = " ".join(
            [
                candidate.title,
                candidate.summary,
                candidate.strategy_type,
                " ".join(candidate.cluster_labels),
                " ".join(candidate.evidence),
            ]
        ).lower()
        directives = [str(item or "").strip().lower() for item in feedback_snapshot.get("directives") or [] if str(item or "").strip()]
        risk_labels = [str(item or "").strip().lower() for item in feedback_snapshot.get("risk_labels") or [] if str(item or "").strip()]

        bonus = min(0.9, 0.2 * needs_adjustment) + min(0.45, 0.1 * adapted)
        if directives and any(item in text for item in directives):
            bonus += 0.35
        candidate_cluster_labels = {label.lower() for label in candidate.cluster_labels}
        if risk_labels and (candidate_cluster_labels.intersection(risk_labels) or any(item in text for item in risk_labels)):
            bonus += 0.45
        if validated > (needs_adjustment + adapted) and candidate.source == "long_term_memory":
            bonus = max(0.0, bonus - 0.15)
        return round(bonus, 3)

    @staticmethod
    def _feedback_priority_boost(feedback_snapshot: dict[str, object]) -> int:
        counts = feedback_snapshot.get("status_counts") or {}
        try:
            needs_adjustment = max(0, int(counts.get("needs_adjustment") or 0))
            adapted = max(0, int(counts.get("adapted") or 0))
        except (TypeError, ValueError):
            return 0
        if needs_adjustment >= 3:
            return 2
        if needs_adjustment >= 1 or adapted >= 3:
            return 1
        return 0

    @staticmethod
    def _dedupe_candidates(candidates: list[ProactiveGoalCandidate]) -> list[ProactiveGoalCandidate]:
        seen: set[str] = set()
        semantic_seen: set[str] = set()
        unique: list[ProactiveGoalCandidate] = []
        for candidate in candidates:
            semantic_key = ProactiveGoalPlanner._slug(f"{candidate.title}:{candidate.summary}")[:180]
            if candidate.dedup_key in seen or semantic_key in semantic_seen:
                continue
            seen.add(candidate.dedup_key)
            semantic_seen.add(semantic_key)
            unique.append(candidate)
        return unique

    @staticmethod
    def _slug(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return normalized or "goal"
