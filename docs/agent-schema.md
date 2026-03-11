# Agent 数据层第一版

## 1. 当前策略

当前项目还没有正式接入 Alembic，因此 `agent` 的第一版数据层采用“共享 SQLAlchemy metadata + 幂等建表脚本”的方式落地。

这套策略适用于当前阶段，原因很简单：

- 这次新增的是一组全新的 `agent_*` 表
- 不涉及对现有业务表做破坏性变更
- 现有项目同时支持 SQLite 和 PostgreSQL
- 我们需要先把 `agent` 运行时骨架落下来，再决定是否引入正式迁移框架

## 2. 新增表

本次新增了这些核心表：

- `agent_sessions`
- `agent_messages`
- `agent_runs`
- `agent_scheduled_tasks`
- `agent_approval_requests`
- `agent_incidents`
- `agent_alerts`
- `agent_subscriptions`
- `agent_artifacts`
- `agent_memory_items`
- `agent_memory_jobs`
- `agent_connector_deliveries`
- `agent_dedup_events`

## 3. 设计分组

### 运行时

- `agent_sessions`
- `agent_messages`
- `agent_runs`
- `agent_scheduled_tasks`
- `agent_approval_requests`

### 事件与通知

- `agent_incidents`
- `agent_alerts`
- `agent_subscriptions`
- `agent_connector_deliveries`
- `agent_dedup_events`

### 记忆与证据

- `agent_memory_items`
- `agent_memory_jobs`
- `agent_artifacts`

## 4. 如何初始化

在项目根目录运行：

```bash
python scripts/migrate_agent_schema.py
```

这个脚本会：

1. 读取当前数据库中的表
2. 调用现有 `init_db()`
3. 创建缺失的 `agent_*` 表
4. 输出哪些表是新创建的，哪些表已经存在

## 5. 当前限制

这不是最终 migration 方案。

当前限制是：

- 只能稳定支持“新增表”
- 不适合复杂列变更、列重命名、约束迁移
- 不适合多人并行维护长期 schema 演进

因此，接下来当 `agent-control-plane` 和 `memory-service` 进入实装阶段后，建议补一套正式的 Alembic 迁移体系。

## 6. 下一步建议

数据层落地后，下一步最合适的是：

1. 新建 `agent-control-plane` 服务骨架
2. 基于这些表实现 `session/run/scheduled_task/approval` 的最小 API
3. 再实现 `runtime-manager` 的 claim/lease
