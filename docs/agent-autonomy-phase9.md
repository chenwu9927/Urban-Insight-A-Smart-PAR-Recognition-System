# Agent Autonomy Phase 9

Phase 9 extends phase 8 from "LLM-assisted goal extraction" to "LLM-assisted operational distillation".

## Added capabilities

- Distilled strategy context
  - `agent/memory_distillation.py` now returns:
    - `distillation_summary`
    - `strategy_summary`
    - `strategy_directives`
    - `risk_clusters`
    - `goals`

- Risk-cluster-aware prioritization
  - `agent/proactive_goals.py` now computes:
    - candidate-level `priority_score`
    - candidate-level `priority_tier`
    - batch-level `priority_tier`
    - batch-level `priority_boost`
  - Priority is derived from:
    - candidate risk level
    - source type
    - confidence
    - evidence density
    - matching high-severity risk clusters

- Distillation context persistence
  - Materialized proactive goals now persist:
    - per-candidate priority metadata
    - batch distillation summary
    - strategy summary
    - strategy directives
    - risk clusters
  - These are stored in session state, system message content, run input payload, and goal meta.

- Scheduler priority dispatch
  - `agent/scheduler/worker.py` now performs one extra immediate `dispatch_due` pass when:
    - proactive goals were created
    - batch priority tier is elevated or urgent
  - This reduces latency between memory distillation and actual agent work.

## API changes

`POST /agent/goals/proactive-from-memory`

Response now also includes:

- `distillation_summary`
- `strategy_summary`
- `strategy_directives`
- `risk_clusters`
- `priority_tier`
- `priority_boost`
- `priority_score`

## Scheduler settings

New environment variables:

- `AGENT_PROACTIVE_GOAL_PRIORITY_DISPATCH_ENABLED`
- `AGENT_PROACTIVE_GOAL_PRIORITY_DISPATCH_LIMIT`

## Design intent

Phase 9 keeps the phase 8 contract intact but adds one higher-level layer:

1. Distill memory into strategy and risk context
2. Distill candidate goals
3. Score and prioritize those candidates
4. Persist the strategy/risk context alongside each goal
5. Let the scheduler accelerate dispatch when the distilled risk is elevated

This gives the always-on agent a way to convert memory into both "what to do next" and "how urgent the platform thinks it is".
