# Agent Autonomy Phase 4

Phase 4 adds goal lifecycle management on top of the phase 3 follow-up chain.

## Added capabilities

- Goal lifecycle
  - New `agent_goals` table stores long-running autonomous goals.
  - A root run that emits `planned_steps` now creates a goal automatically.
  - Goal state is synchronized from linked runs and can transition through:
    - `planned`
    - `running`
    - `replanning`
    - `blocked`
    - `completed`
    - `failed`

- Failure-driven replanning
  - When a goal-linked step run fails, the control plane can create a `schedule_mode=replan` child run automatically.
  - The replan run asks `agent.chat` to reassess the goal and generate the next safe steps.

- Goal visibility
  - Added:
    - `GET /agent/goals`
    - `GET /agent/goals/{goal_id}`
    - `GET /agent/goals/{goal_id}/runs`
  - Overview counts now include `active_goals` and `blocked_goals`.

- Agent tools
  - Added:
    - `agent.list_goals`
    - `agent.get_goal`

## Key files

- `agent/models.py`
- `agent/control_plane/services.py`
- `agent/control_plane/routers/runs.py`
- `agent/control_plane/routers/goals.py`
- `agent/executor/service.py`
- `agent/tool_registry.py`
- `agents/agent_service/app.py`

## Runtime contract

Root runs may return:

```json
{
  "goal_summary": "Track alert resolution until stable.",
  "planned_steps": [
    {
      "title": "Refresh open alerts",
      "action": "agent.list_alerts",
      "params": { "status": "open", "limit": 5 },
      "rationale": "Check current alert state."
    }
  ],
  "auto_dispatch_followups": true
}
```

If a child step fails and the goal allows automatic replanning, the control plane creates a new child run with:

- `schedule_mode = "replan"`
- `input_payload.action = "agent.chat"`
- `input_payload.replan_of_run_id = <failed-run-id>`
