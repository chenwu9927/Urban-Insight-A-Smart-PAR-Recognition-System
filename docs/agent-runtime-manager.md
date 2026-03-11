# Agent Runtime Manager 第一版

## 1. 作用

`agent-runtime-manager` 是 control plane 之外的后台 worker。

它负责：

- 轮询并 claim `queued` 的 `agent_run`
- 维护 lease/heartbeat
- 将 claim 转发给独立的 `agent-executor`
- 将结果回写到 control plane
- 在失败时把 run 标记为 `failed`

## 2. 当前实现能力

第一版是一个调度型 worker，当前通过独立的 `agent-executor` 执行 `api_only` 动作。

## 3. 关键文件

- `agent/runtime_manager/config.py`
- `agent/runtime_manager/client.py`
- `agent/runtime_manager/executor.py`
- `agent/runtime_manager/worker.py`
- `agent/runtime_manager/main.py`
- `microservices/agent_runtime_manager/main.py`

## 4. 运行方式

单次处理一个 run：

```bash
python -m microservices.agent_runtime_manager.main --once
```

持续运行：

```bash
python -m microservices.agent_runtime_manager.main
```

## 5. 关键环境变量

- `AGENT_CONTROL_PLANE_URL`
- `AGENT_EXECUTOR_URL`
- `AUTH_SERVICE_URL`
- `MEDIA_SERVICE_URL`
- `ANALYSIS_SERVICE_URL`
- `SEARCH_SERVICE_URL`
- `INSIGHT_SERVICE_URL`
- `AGENT_RUNTIME_POLL_SECONDS`
- `AGENT_RUNTIME_HEARTBEAT_SECONDS`
- `AGENT_RUNTIME_LEASE_SECONDS`

## 6. 当前边界

这一版 runtime manager 仍然是最小可用骨架，不是最终形态。

当前还没有做：

- 多并发 worker
- 分布式 in-flight 去重
- 审批后自动恢复的更复杂策略
- 沙箱 executor
- artifact 生成
- memory 注入

## 7. 下一步建议

在这版 runtime manager 之后，最合适的下一步是：

1. 增加邮件 connector，让邮件任务真正进入 `session/run`
2. 让 executor 支持 artifact、memory 和更复杂的能力束
3. 逐步演进到沙箱 executor
