# Agent Autonomy Phase 8

Phase 8 upgrades proactive goal generation from rule-only extraction to LLM-assisted memory distillation.

## Added capabilities

- LLM-assisted memory distillation
  - New module: `agent/memory_distillation.py`
  - Input:
    - long-term memory from `MEMORY.md`
    - recent daily notes
  - Output:
    - proactive goal candidates with:
      - `title`
      - `summary`
      - `prompt`
      - `risk_level`
      - `strategy_type`
      - `confidence`
      - `evidence`

- Combined candidate pipeline
  - `agent/proactive_goals.py` now merges:
    - rule-based candidates from phase 7
    - LLM-distilled candidates from phase 8
  - Semantic dedup is applied across both sets before materialization

- Goal metadata enrichment
  - Materialized sessions, runs, and goals now store:
    - `distillation_method`
    - `risk_level`
    - `strategy_type`
    - `confidence`
    - `evidence`

- Scheduler controls
  - New scheduler knobs:
    - `AGENT_PROACTIVE_GOAL_LLM_DISTILLATION_ENABLED`
    - `AGENT_PROACTIVE_GOAL_LLM_CANDIDATE_LIMIT`
    - `AGENT_PROACTIVE_GOAL_MEMORY_MAX_CHARS`
    - `AGENT_PROACTIVE_GOAL_MIN_DISTILLED_CONFIDENCE`

## API changes

`POST /agent/goals/proactive-from-memory`

New query params:

- `use_llm_distillation`
- `distilled_limit`
- `max_memory_chars`
- `min_distilled_confidence`

New response fields:

- `rule_candidates`
- `llm_candidates`
- `llm_distillation_used`
- `llm_error`

## Design intent

Phase 8 keeps the phase 7 pipeline intact and only inserts one new layer:

1. Read memory
2. Distill candidates with LLM when configured
3. Merge with rule candidates
4. Dedup
5. Materialize with existing goal/session/run pipeline

This keeps the system operational when no LLM is configured while allowing richer proactive goal creation when memory is complex.
