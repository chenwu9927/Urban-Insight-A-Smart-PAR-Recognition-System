from __future__ import annotations

import datetime
import os
import re
from pathlib import Path


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, path)


class AgentMemoryStore:
    """A lightweight workspace memory store inspired by picoclaw.

    Memory is kept in files so the always-on agent can preserve durable,
    human-readable context without adding another service boundary.
    """

    def __init__(self, workspace_dir: str | Path) -> None:
        self.workspace_dir = Path(workspace_dir).resolve()
        self.memory_dir = self.workspace_dir / "memory"
        self.long_term_path = self.memory_dir / "MEMORY.md"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def read_long_term(self) -> str:
        if not self.long_term_path.exists():
            return ""
        return self.long_term_path.read_text(encoding="utf-8")

    def write_long_term(self, content: str) -> None:
        _atomic_write(self.long_term_path, content.strip() + "\n")

    def append_long_term_fact(self, fact: str) -> Path:
        normalized = " ".join((fact or "").split()).strip()
        if not normalized:
            return self.long_term_path

        existing = self.read_long_term().strip()
        bullet = f"- {normalized}"
        if bullet in existing.splitlines():
            return self.long_term_path

        if existing:
            content = existing.rstrip() + "\n" + bullet + "\n"
        else:
            content = "# Long-term Memory\n\n" + bullet + "\n"
        self.write_long_term(content)
        return self.long_term_path

    def append_daily_note(
        self,
        content: str,
        *,
        note_time: datetime.datetime | None = None,
        heading: str | None = None,
    ) -> Path:
        note_time = note_time or datetime.datetime.now()
        note_path = self.get_daily_note_path(note_time)
        existing = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
        if not existing:
            existing = f"# {note_time.strftime('%Y-%m-%d')}\n"
        title = heading.strip() if heading else note_time.strftime("%H:%M:%S")
        block = f"\n## {title}\n\n{content.strip()}\n"
        _atomic_write(note_path, existing.rstrip() + block)
        return note_path

    def get_daily_note_path(self, note_time: datetime.datetime | None = None) -> Path:
        note_time = note_time or datetime.datetime.now()
        month_dir = self.memory_dir / note_time.strftime("%Y%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        return month_dir / f"{note_time.strftime('%Y%m%d')}.md"

    def get_recent_daily_notes(self, days: int = 3) -> str:
        safe_days = max(1, min(30, int(days)))
        chunks: list[str] = []
        for offset in range(safe_days):
            note_time = datetime.datetime.now() - datetime.timedelta(days=offset)
            note_path = self.get_daily_note_path(note_time)
            if note_path.exists():
                chunks.append(note_path.read_text(encoding="utf-8").strip())
        return "\n\n---\n\n".join(chunk for chunk in chunks if chunk)

    def get_context(self, days: int = 3) -> str:
        long_term = self.read_long_term().strip()
        recent = self.get_recent_daily_notes(days=days).strip()
        parts: list[str] = []
        if long_term:
            parts.append("## Long-term Memory\n\n" + long_term)
        if recent:
            parts.append("## Recent Daily Notes\n\n" + recent)
        return "\n\n---\n\n".join(parts)

    def summarize_recent_strategy_feedback(self, days: int = 7, *, limit: int = 12) -> dict[str, object]:
        safe_days = max(1, min(30, int(days)))
        safe_limit = max(1, min(50, int(limit)))
        entries: list[dict[str, object]] = []

        for offset in range(safe_days):
            note_time = datetime.datetime.now() - datetime.timedelta(days=offset)
            note_path = self.get_daily_note_path(note_time)
            if not note_path.exists():
                continue
            try:
                content = note_path.read_text(encoding="utf-8")
            except OSError:
                continue
            entries.extend(self._extract_strategy_feedback_entries(content))

        entries = entries[:safe_limit]
        status_counts = {"validated": 0, "adapted": 0, "needs_adjustment": 0}
        summaries: list[str] = []
        directives: list[str] = []
        risk_labels: list[str] = []

        for entry in entries:
            status = str(entry.get("status") or "").strip().lower()
            if status in status_counts:
                status_counts[status] += 1

            summary = str(entry.get("summary") or "").strip()
            if summary and summary not in summaries:
                summaries.append(summary)

            for directive in entry.get("directives") or []:
                text = " ".join(str(directive or "").split()).strip()
                if text and text not in directives:
                    directives.append(text)

            for label in entry.get("risk_labels") or []:
                text = " ".join(str(label or "").split()).strip()
                if text and text not in risk_labels:
                    risk_labels.append(text)

        summary_text = self._build_strategy_feedback_summary_text(
            status_counts=status_counts,
            summaries=summaries,
            directives=directives,
            risk_labels=risk_labels,
        )
        return {
            "entries": len(entries),
            "status_counts": status_counts,
            "summaries": summaries[:5],
            "directives": directives[:6],
            "risk_labels": risk_labels[:6],
            "summary_text": summary_text,
        }

    @staticmethod
    def _extract_strategy_feedback_entries(content: str) -> list[dict[str, object]]:
        lines = (content or "").splitlines()
        entries: list[dict[str, object]] = []
        current_heading = ""
        current_block: list[str] = []

        def flush() -> None:
            if "strategy feedback" not in current_heading.lower() or not current_block:
                return
            parsed = AgentMemoryStore._parse_strategy_feedback_block("\n".join(current_block))
            if parsed:
                entries.append(parsed)

        for line in lines:
            if line.startswith("## "):
                flush()
                current_heading = line[3:].strip()
                current_block = []
                continue
            current_block.append(line)
        flush()
        return entries

    @staticmethod
    def _parse_strategy_feedback_block(block: str) -> dict[str, object] | None:
        status = ""
        summary = ""
        directives: list[str] = []
        risk_labels: list[str] = []
        section = ""

        for raw_line in (block or "").splitlines():
            line = raw_line.strip()
            if not line:
                section = ""
                continue

            lower = line.lower()
            if lower.startswith("status:"):
                status = line.split(":", 1)[1].strip().lower()
                section = ""
                continue
            if lower == "strategy directives:":
                section = "directives"
                continue
            if lower == "risk clusters:":
                section = "risks"
                continue
            if lower == "feedback summary:":
                section = "summary"
                continue

            if section == "summary" and not summary:
                summary = line
                section = ""
                continue
            if section == "directives" and line.startswith("- "):
                directives.append(line[2:].strip())
                continue
            if section == "risks" and line.startswith("- "):
                label = re.sub(r"^\-\s*\[[^\]]+\]\s*", "", line).split(":", 1)[0].strip()
                if label:
                    risk_labels.append(label)
                continue

        if not status and not summary and not directives and not risk_labels:
            return None
        return {
            "status": status,
            "summary": summary,
            "directives": directives[:5],
            "risk_labels": risk_labels[:5],
        }

    @staticmethod
    def _build_strategy_feedback_summary_text(
        *,
        status_counts: dict[str, int],
        summaries: list[str],
        directives: list[str],
        risk_labels: list[str],
    ) -> str:
        total = sum(int(value or 0) for value in status_counts.values())
        if total <= 0:
            return ""

        parts = [
            (
                "Recent strategy feedback: "
                f"{status_counts.get('needs_adjustment', 0)} needs adjustment, "
                f"{status_counts.get('adapted', 0)} adapted, "
                f"{status_counts.get('validated', 0)} validated."
            )
        ]
        if directives:
            parts.append("Recurring directives: " + "; ".join(directives[:3]))
        if risk_labels:
            parts.append("Observed risk clusters: " + ", ".join(risk_labels[:3]))
        if summaries:
            parts.append("Latest feedback: " + summaries[0])
        return " ".join(part for part in parts if part).strip()
