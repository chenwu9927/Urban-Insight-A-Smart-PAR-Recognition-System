# Agent Runtime Manager

## 1. 当前定位

`runtime-manager` 现在仍然存在，但默认不再单独部署。

默认情况下，它作为 `agent-service` 内部后台循环运行，负责：

- claim `queued` run
- 续租 heartbeat
- 调用 executor
- complete / fail 回写

## 2. 为什么保留这个模块

保留它的原因是：

- 逻辑边界仍然清晰
- 后续如果要扩容，直接单独起进程即可
- 现在统一服务只是部署层合并，不是代码层混乱

## 3. 当前行为

- 拉取 `queued` 或过期 `claimed` 的任务
- 发送 heartbeat
- 把任务提交给 `/execute`
- 成功后写 `completed`
- 失败后写 `failed`

## 4. 默认运行方式

默认通过 `agent/service_runtime.py` 在 `agent-service` 内后台运行。

标准部署入口：

- `agents/agent_service/app.py`

内部实现位置：

- `agent/runtime_manager/main.py`
- `agent/service_runtime.py`
