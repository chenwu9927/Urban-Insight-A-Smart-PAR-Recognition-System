from __future__ import annotations

import datetime
import os
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
