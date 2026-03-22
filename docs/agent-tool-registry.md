# Agent Tool Registry

## Purpose

This registry is the single source of truth for the agent's callable system tools.
It exists to keep execution, approval, auditing, and UI presentation aligned.

## Source Files

- `agent/tool_registry.py`
- `agent/executor/service.py`
- `agent/control_plane/routers/tools.py`

## Registry Model

Each tool definition includes:

- `action`: stable action id used by runs
- `name`: human-friendly tool name
- `category`: `insight`, `search`, `analysis`, `patrol`, `memory`, or `orchestration`
- `description`: concise operator-facing description
- `target_service`: underlying service or subsystem
- `risk_level`: operational risk classification
- `approval_mode`: approval expectation
- `idempotent`: whether re-running the tool is expected to be safe
- `input_parameters`: declared input contract
- `output_fields`: high-level output contract

## Current Tool Families

- Insight: `stats.get`, `insights.get_brief`, `insights.ask`
- Search: `search.structured`, `search.nl`
- Analysis: `analysis.get_task`
- Patrol: `patrol.analysis_backlog`, `patrol.analysis_failures`, `patrol.approval_timeout`
- Memory: `memory.get_context`, `memory.read_long_term`, `memory.write_long_term`, `memory.append_daily_note`
- Orchestration: `agent.chat`

## API

- `GET /agent/tools`
  - optional filters: `category`, `risk_level`, `approval_mode`
- `GET /agent/tools/{action}`

These endpoints are exposed by both:

- `agent-control-plane`
- `agent-service`

## Execution Alignment

The executor still implements the action handlers directly, but now:

- unsupported actions are validated against the registry
- execution output includes tool metadata
- future approval or UI layers can consume the same metadata without duplicating action rules

## Recommended Next Step

Promote this registry into a full policy layer by adding:

- approval rules by `risk_level`
- tool allowlists by session type
- operator-visible tool catalog in the Agent UI
