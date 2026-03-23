# Agent Autonomy Phase 7

Phase 7 lets the agent create new goals proactively from workspace memory instead of only reacting to existing goals.

## Added capabilities

- Proactive goal generation from memory
  - New endpoint: `POST /agent/goals/proactive-from-memory`
  - Sources:
    - explicit long-term goal lines in `MEMORY.md`
    - recurring incident patterns in recent daily notes
  - Output:
    - new `goal` session
    - new root run with `schedule_mode=proactive`
    - new `agent_goal`

- Scheduler integration
  - The scheduler now runs proactive goal generation after:
    - scheduled task dispatch
    - goal sweep
    - memory patrol boost

- Memory-backed dedup
  - Repeated proactive candidates are suppressed with `agent_dedup_events`
  - Existing active goals with the same summary also block duplicates

## Key files

- `agent/proactive_goals.py`
- `agent/control_plane/routers/goals.py`
- `agent/control_plane/schemas.py`
- `agent/scheduler/client.py`
- `agent/scheduler/config.py`
- `agent/scheduler/worker.py`

## Example contract

```json
{
  "scanned": 2,
  "candidates": 2,
  "created": 2,
  "deduped": 0,
  "run_ids": ["run-a", "run-b"],
  "goal_ids": ["goal-a", "goal-b"]
}
```
