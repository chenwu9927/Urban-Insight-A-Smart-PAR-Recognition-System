# Agents

这里放 Agent 平台的标准部署入口。

当前阶段：

- `agent_service/` 是统一常驻 Agent 服务入口

后续如果需要拆分 `agent-worker / agent-notifier / agent-scheduler`，也会继续在这里展开。

Agent 的 HTTP 契约也统一从这里导出：

- `python scripts/export_openapi_contracts.py`
