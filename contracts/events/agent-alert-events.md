# Agent Alert Events

这份文档定义 Agent 告警域在引入消息队列后的标准事件名称与最小 payload。

## 事件列表

### `agent.alert.opened`

当新的告警进入 `open` 状态时发布。

建议字段：

- `event_type`
- `event_version`
- `alert_id`
- `source_rule`
- `severity`
- `scope_type`
- `scope_id`
- `summary`
- `detected_at`

### `agent.alert.resolved`

当告警从 `open` 转为 `resolved` 时发布。

建议字段：

- `event_type`
- `event_version`
- `alert_id`
- `source_rule`
- `severity`
- `scope_type`
- `scope_id`
- `summary`
- `detected_at`
- `resolved_at`

## 事件约束

- 所有事件必须带 `event_version`
- 事件字段新增应向后兼容
- 告警通知器、监控平台、审计系统都应消费同一事件定义
