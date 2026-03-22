# Agent Schema

## 1. 当前 schema 的定位

数据库 schema 仍然保留了较完整的 agent 表结构，但当前推荐实现已经收敛为更简单的运行模型。

数据库优先承载的是：

- `agent_sessions`
- `agent_messages`
- `agent_runs`
- `agent_scheduled_tasks`
- `agent_approval_requests`
- `agent_connector_deliveries`

这些表已经足够支持：

- 邮件任务
- 24x7 巡检
- claim/lease 执行
- 回邮
- 审批

## 2. 现在不作为第一优先级的表

下面这些表先保留，但暂时不是默认主链路：

- `agent_incidents`
- `agent_alerts`
- `agent_subscriptions`
- `agent_artifacts`
- `agent_memory_items`
- `agent_memory_jobs`
- `agent_dedup_events`

原因不是它们不重要，而是当前更推荐：

- 先把巡检和邮件闭环跑稳
- 记忆先用文件式 workspace memory
- 告警和 incident 作为下一阶段增强

## 3. 记忆的当前实现

当前记忆不是优先写数据库，而是优先写：

- `<workspace>/memory/MEMORY.md`
- `<workspace>/memory/YYYYMM/YYYYMMDD.md`

数据库里的 memory 相关表作为后续升级保留。

## 4. 演进策略

如果后续需要：

- 向量检索
- 多 scope 记忆治理
- 记忆审批
- 记忆历史版本

再把当前文件式记忆同步扩展到数据库和独立 memory service。
