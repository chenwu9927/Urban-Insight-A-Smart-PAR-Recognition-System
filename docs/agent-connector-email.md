# Agent Email Connector 第一版

## 1. 作用

`agent-connector-email` 是管理人员和 agent 的第一条协作通道。

它当前负责：

- 接收入站邮件的标准化 payload
- 将邮件转换为 `session + message + run`
- 发送 ACK
- 轮询已完成 run，发送结果回邮
- 轮询待审批请求，发送审批邮件
- 接收审批回邮并写回 control plane

## 2. 当前实现方式

第一版先做“工程闭环优先”的方案：

- 入站邮件先通过 HTTP 标准化接口接入
- 出站邮件默认使用 `log` 模式，写到本地 `outbox`
- 如果配置了 SMTP，也可以切到真实发信

也就是说，这一版已经把邮件业务流做通了，但没有强绑某一家邮件服务商。

## 3. 关键接口

### `POST /email/inbound`

把一封标准化邮件送进系统。

普通任务示例：

```json
{
  "from_address": "manager@example.com",
  "subject": "请给我今天的统计摘要",
  "text": "请统计最近60分钟的人流情况",
  "action": "stats.get",
  "params": {
    "interval": 60
  }
}
```

审批回邮示例：

```json
{
  "from_address": "manager@example.com",
  "subject": "[APPROVAL:approval-id]",
  "text": "approved"
}
```

### `POST /email/process-outbound`

手动触发一次出站处理：

- 扫描 `completed/failed` 的 run
- 发送结果邮件
- 扫描 `pending` 的 approval
- 发送审批邮件

### `GET /email/outbox`

查看本地 outbox 文件列表。

## 4. 配置项

- `AGENT_EMAIL_DELIVERY_MODE=log|smtp`
- `AGENT_EMAIL_OUTBOX_DIR`
- `AGENT_EMAIL_FROM_ADDRESS`
- `AGENT_EMAIL_ENABLE_BACKGROUND`
- `AGENT_EMAIL_POLL_SECONDS`
- `AGENT_EMAIL_SMTP_HOST`
- `AGENT_EMAIL_SMTP_PORT`
- `AGENT_EMAIL_SMTP_USERNAME`
- `AGENT_EMAIL_SMTP_PASSWORD`
- `AGENT_EMAIL_SMTP_USE_TLS`

## 5. 当前边界

第一版还没有做：

- 真实 IMAP 收件轮询
- 邮件附件解析与上传
- 邮件线程更完整的会话复用策略
- HTML 模板邮件

## 6. 为什么这一步值钱

做到这里以后，项目已经拥有一条真实的运营闭环：

1. 管理人员发邮件
2. 邮件进入 `session/run`
3. runtime manager 调度 executor 执行
4. connector 再把 ACK、结果、审批回到邮件通道

这意味着 agent 已经开始具备“可用的业务接入口”，而不再只是内部架构骨架。
