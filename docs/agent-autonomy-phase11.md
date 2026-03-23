# Agent Autonomy Phase 11

Phase 11 turns strategic context into execution policy.

## Added capabilities

- Strategy-aware tool selection
  - `agent/executor/service.py` now derives a tool policy from:
    - current question
    - `strategy_summary`
    - `strategy_directives`
    - `risk_clusters`
    - `priority_tier`
  - The policy outputs:
    - `preferred_tool_actions`
    - `focus_categories`
    - `verification_mode`

- Strategy-aware tool ordering
  - `agent.chat` now orders available tools based on the derived policy.
  - Elevated or urgent contexts bias the tool list toward:
    - orchestration reads first
    - then domain-specific patrol/search/insight tools depending on the memory-derived strategy

- Strategy-aware verification
  - Strict verification is enabled for elevated or urgent contexts.
  - In strict mode, the executor enforces stronger checks on key tools such as:
    - `agent.get_overview`
    - `agent.get_runtime_status`
    - `stats.get`
    - `insights.ask`
    - `patrol.*`
  - Breached patrol results must now carry non-empty evidence lists.

- Verification metadata
  - Tool output payloads now include `verification_policy` metadata so downstream consumers can see:
    - verification mode
    - priority tier
    - preferred tool actions
    - focus categories

## Design intent

Phase 10 made the agent aware of strategic context.
Phase 11 makes that context change execution behavior.

The result is:

1. Memory distillation shapes strategy
2. Strategy shapes tool ordering
3. Priority shapes verification strictness
4. The agent becomes less generic and more operationally intentional
