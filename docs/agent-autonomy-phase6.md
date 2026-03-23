# Agent Autonomy Phase 6

Phase 6 links active goals with workspace memory and uses recent memory to change patrol execution priority.

## Added capabilities

- Long-running goal recovery
  - `POST /agent/goals/sweep` now supports `goal_recovery_minutes`.
  - Stale active goals can create `schedule_mode=goal_recovery` runs automatically.
  - Recovery writes a daily goal snapshot into memory and can promote multi-day goals into long-term memory.

- Memory-driven patrol priority
  - New endpoint: `POST /agent/scheduled-tasks/boost-from-memory`
  - Recent daily notes are scanned for recurring incident patterns.
  - Matching patrol tasks can be triggered early, with cooldown protection.

- New goal state
  - `recovering`

## Key files

- `agent/goal_memory.py`
- `agent/patrol_priority.py`
- `agent/control_plane/services.py`
- `agent/control_plane/routers/goals.py`
- `agent/control_plane/routers/scheduled_tasks.py`
- `agent/scheduler/client.py`
- `agent/scheduler/config.py`
- `agent/scheduler/worker.py`

## Example contracts

### Goal sweep

```json
{
  "inspected": 2,
  "synced": 2,
  "replanned": 0,
  "verified": 0,
  "recovered": 1,
  "run_ids": ["goal-recovery-run-id"]
}
```

### Memory patrol boost

```json
{
  "scanned": 1,
  "triggered": 1,
  "run_ids": ["boosted-patrol-run-id"],
  "task_ids": ["scheduled-task-id"]
}
```
