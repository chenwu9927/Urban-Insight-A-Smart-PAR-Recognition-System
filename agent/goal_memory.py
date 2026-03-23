from __future__ import annotations

from pathlib import Path

from agent.memory_store import AgentMemoryStore
from agent.models import AgentGoal


class AgentGoalMemoryBridge:
    def __init__(self, workspace_dir: str | Path) -> None:
        self.memory = AgentMemoryStore(workspace_dir)

    def record_goal_snapshot(self, goal: AgentGoal, *, reason: str) -> str:
        lines = [
            f"Goal: {goal.summary or goal.title or goal.id}",
            f"Status: {goal.status}",
            f"Steps: {goal.completed_steps}/{goal.step_count} completed, {goal.active_steps} active, {goal.failed_steps} failed",
        ]
        if goal.last_error:
            lines.extend(["", f"Last error: {goal.last_error}"])
        path = self.memory.append_daily_note(
            "\n".join(lines).strip(),
            heading=f"goal {reason} | {goal.id}",
        )
        return str(path)

    def promote_persistent_goal(self, goal: AgentGoal) -> str:
        fact = f"Active long-running goal: {goal.summary or goal.title or goal.id}"
        path = self.memory.append_long_term_fact(fact)
        return str(path)
