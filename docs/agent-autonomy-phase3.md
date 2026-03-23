# Agent Autonomy Phase 3

Phase 3 upgrades the agent from a single-turn tool user into a stateful operator loop with memory writeback and follow-up chains.

## Added capabilities

- Automatic memory writeback
  - `agent.chat` now writes a daily note with the operator question, agent answer, and planned follow-up steps.
  - Long-term memory promotion is supported for durable instructions such as "remember this default behavior".
  - Patrol breaches continue to be persisted as operational notes.

- Goal and step chaining
  - `agent_runs` now supports `parent_run_id`, `goal_key`, and `step_index`.
  - A completed run can spawn follow-up child runs when `planned_steps` are returned in `output_payload`.
  - Child runs stay in the same session and inherit the parent goal context.

- Planner integration
  - `agent.chat` can produce `goal_summary`, `planned_steps`, `planning_mode`, and `auto_dispatch_followups`.
  - Planning can use an LLM when configured, and falls back to deterministic heuristics.

## Key files

- `agent/goal_planner.py`
- `agent/memory_writeback.py`
- `agent/executor/service.py`
- `agent/control_plane/services.py`
- `agent/control_plane/routers/runs.py`
- `agent/models.py`
- `backend/database.py`

## Runtime contract

When a run completes, `output_payload` may include:

```json
{
  "goal_summary": "Autonomous follow-up chain",
  "planned_steps": [
    {
      "title": "Refresh open alerts",
      "action": "agent.list_alerts",
      "params": { "status": "open", "limit": 10 },
      "rationale": "Re-check alert state."
    }
  ],
  "auto_dispatch_followups": true
}
```

If `auto_dispatch_followups` is not `false`, the control plane creates child runs automatically.
