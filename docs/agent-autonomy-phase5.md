# Agent Autonomy Phase 5

Phase 5 adds recovery loops and event-driven wakeups on top of goal lifecycle management.

## Added capabilities

- Goal sweep
  - New endpoint: `POST /agent/goals/sweep`
  - The scheduler now runs goal sweep after scheduled-task dispatch.
  - Goal sweep performs:
    - state resync
    - blocked-goal recovery via replan runs
    - pending-goal convergence verification

- Convergence verification
  - When all goal steps complete, the goal enters `pending_verification`.
  - Sweep creates a `schedule_mode=verification` run.
  - If the verification run completes without new `planned_steps`, the goal is marked verified and transitions to `completed`.

- Event-driven wakeup
  - New endpoint: `POST /agent/events`
  - External signals can wake the agent immediately and attach to an existing goal or session.
  - Event dedup uses `agent_dedup_events` to suppress duplicate wakeups.

## New goal states

- `pending_verification`
- `verifying`

## Key files

- `agent/control_plane/services.py`
- `agent/control_plane/routers/goals.py`
- `agent/control_plane/routers/events.py`
- `agent/control_plane/routers/runs.py`
- `agent/scheduler/client.py`
- `agent/scheduler/worker.py`
- `agents/agent_service/app.py`

## Example contracts

### Goal sweep

```json
{
  "inspected": 3,
  "synced": 3,
  "replanned": 1,
  "verified": 1,
  "run_ids": ["run-a", "run-b"]
}
```

### Event wakeup

```json
{
  "event_type": "alert.opened",
  "summary": "New alert arrived for active goal",
  "goal_id": "<goal-id>",
  "dedup_key": "alert-goal-001",
  "ttl_seconds": 600
}
```
