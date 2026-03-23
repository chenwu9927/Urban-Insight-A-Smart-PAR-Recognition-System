# Agent Autonomy Phase 14

Phase 14 makes strategy feedback influence the next round of autonomous planning instead of only being archived.

## Added capabilities

- Feedback-aware memory distillation
  - `agent/memory_store.py` now summarizes recent `strategy feedback` note blocks.
  - `agent/memory_distillation.py` injects this feedback packet into LLM-assisted memory distillation.
  - Distillation now sees:
    - recent feedback summary
    - feedback status counts
    - recurring directives
    - recurring risk labels

- Feedback-aware proactive prioritization
  - `agent/proactive_goals.py` now uses recent strategy feedback when scoring proactive goal candidates.
  - Repeated `needs_adjustment` signals raise candidate and batch priority.
  - Matching directives and risk labels add additional priority weight.

- Feedback-aware scheduler behavior
  - `agent/scheduler/worker.py` now reads `feedback_priority_boost`.
  - When recent strategy feedback indicates repeated adjustment pressure, scheduler triggers an extra goal sweep.
  - This helps active goals replan or recover earlier instead of waiting for the next normal cycle.

- Strategic context propagation
  - `agent/executor/service.py`, `agent/context_builder.py`, and `agent/goal_planner.py` now carry:
    - `strategy_feedback_summary`
    - `feedback_status_counts`
    - `feedback_priority_boost`

## Design intent

Phase 13 closed the loop from execution back into strategy memory.
Phase 14 makes that loop operationally useful.

The autonomy chain is now:

1. Memory and strategy feedback are distilled together
2. Distillation produces goals, strategy, and risk context
3. Strategy changes execution policy and planning
4. Execution outcomes write back strategy feedback
5. Feedback raises or lowers the urgency of future proactive work
6. Scheduler can accelerate goal sweep when adjustment pressure is building
