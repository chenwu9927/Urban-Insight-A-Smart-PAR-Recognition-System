# Agent Executor

## 1. 当前定位

`executor` 是 Agent 的工具执行层。

默认情况下，它通过 `agent-service` 内部的 `/execute` 路由被调用，不再要求单独部署成一个容器。

## 2. 当前支持的动作

### 业务动作

- `stats.get`
- `insights.get_brief`
- `insights.ask`
- `search.structured`
- `search.nl`
- `analysis.get_task`
- `patrol.analysis_backlog`
- `patrol.analysis_failures`
- `patrol.approval_timeout`

### 记忆动作

- `memory.get_context`
- `memory.read_long_term`
- `memory.write_long_term`
- `memory.append_daily_note`

巡检动作在发现问题时，会把摘要写入 workspace memory 的每日笔记。

## 3. 设计原则

- 只提供受控内部工具
- 不默认开放 shell
- 不把 executor 做成通用无限执行器

## 4. 默认运行方式

默认由 `agent-service` 内部调用。

标准部署入口：

- `agents/agent_service/app.py`

内部实现位置：

- `agent/executor/router.py`
- `agent/executor/service.py`
