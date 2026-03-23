# Agent Autonomy Phase 12

Phase 12 makes strategic context control execution budget and degradation behavior.

## Added capabilities

- Strategy-aware execution budget
  - `agent/executor/service.py` now derives:
    - `tool_loop_max_iterations`
    - `planner_step_budget`
    - `tool_retry_limit`
    - `max_tool_fallbacks`
  - Urgent contexts get a larger tool-loop budget and a larger planning budget.

- Strategy-aware fallback chain
  - When a tool fails after retries, the executor can try fallback actions derived from policy.
  - Example fallback paths:
    - `insights.ask -> insights.get_brief -> stats.get`
    - `agent.get_overview -> agent.list_alerts / agent.get_runtime_status`
    - `patrol.analysis_backlog -> agent.get_overview / stats.get`

- Strategy-aware retry policy
  - Idempotent tools now use a dynamic retry limit instead of a fixed retry count.
  - Elevated and urgent contexts get more retry budget before falling back.

- Strategy-aware planner budget
  - `agent/goal_planner.py` now accepts a dynamic `max_steps`.
  - Urgent contexts can produce longer follow-up plans than normal contexts.

- Prompt observability
  - `agent/context_builder.py` now renders:
    - verification mode
    - tool loop budget
    - planner step budget

## Design intent

Phase 11 made strategic context affect tool choice and verification strictness.
Phase 12 makes it affect cost and recovery policy.

The result is:

1. Higher-risk contexts get more execution budget
2. Tool failures degrade through explicit fallback chains instead of just hard failing
3. Follow-up plans can expand when the risk posture justifies it
