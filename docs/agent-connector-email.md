# Agent Connector Email

## 1. 当前定位

邮件连接器仍然是管理员和 agent 的首个正式协作入口，但现在它默认运行在 `agent-service` 内，而不是单独部署。

## 2. 当前能力

- 入站邮件转 `session + message + run`
- 自动 ACK
- 已完成任务结果回邮
- 失败任务结果回邮
- 审批邮件发送
- 审批回邮解析
- outbound delivery 去重落账

## 3. 路由

- `POST /email/inbound`
- `POST /email/process-outbound`
- `GET /email/outbox`

## 4. 默认运行方式

默认由 `agent-service` 内部后台轮询处理 outbound。

标准部署入口：

- `agents/agent_service/app.py`

内部实现位置：

- `agent/connectors/email/router.py`
- `agent/connectors/email/service.py`
