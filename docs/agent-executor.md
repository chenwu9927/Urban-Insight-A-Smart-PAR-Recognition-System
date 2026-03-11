# Agent Executor 第一版

## 1. 作用

`agent-executor` 是 agent 的独立执行服务。

它的职责是：

- 接收 runtime manager 转发的 `claim`
- 根据 run 内容执行内部工具动作
- 返回 `output_payload` 和 `result_summary`

这一步完成后，`agent-runtime-manager` 就只负责调度，不再内联具体执行逻辑。

## 2. 当前实现形态

当前版本是 `api_only executor`，也就是：

- 不接触宿主机
- 不执行 shell
- 只通过 HTTP 调用现有内部业务服务

已支持动作：

- `stats.get`
- `insights.get_brief`
- `insights.ask`
- `search.structured`
- `search.nl`
- `analysis.get_task`

## 3. 关键文件

- `agent/executor/config.py`
- `agent/executor/schemas.py`
- `agent/executor/service.py`
- `agent/executor/router.py`
- `microservices/agent_executor/app.py`

## 4. 接口

### `POST /execute`

入参：

```json
{
  "claim": {
    "run": {},
    "trigger_message": {},
    "session": {}
  }
}
```

出参：

```json
{
  "output_payload": {},
  "result_summary": "Fetched stats successfully",
  "executor_mode": "api_only"
}
```

## 5. 为什么这一步重要

这一步把“调度”和“执行”真正分开了。

后面如果我们要：

- 上容器沙箱
- 注入 memory
- 接入 artifact 生成
- 增加更复杂的工具束

都可以继续沿着 `agent-executor` 扩展，而不用再把 runtime manager 改坏。

## 6. 下一步建议

在 `agent-executor` 落地之后，最合适的下一步是：

1. 新建 `agent-connector-email`
2. 让邮件任务进入 `session -> run`
3. 再把 ACK / 结果回邮 / 审批回邮打通
