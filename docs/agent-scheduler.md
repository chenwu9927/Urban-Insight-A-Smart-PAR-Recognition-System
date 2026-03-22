# Agent Scheduler

## 1. 当前定位

`scheduler` 负责把 `agent_scheduled_task` 变成真实的巡检 run。

现在它默认运行在 `agent-service` 内部，而不是单独部署。

## 2. 当前能力

- 校验 `cron`
- 校验 `timezone`
- 计算 `next_run_at`
- 派发到期任务
- 避免同一巡检重复堆积 active run

## 3. 当前接口

- `POST /agent/scheduled-tasks/dispatch-due`
- `POST /agent/scheduled-tasks/bootstrap-defaults`

## 4. 已落地的巡检模板

`bootstrap-defaults` 会创建 3 个默认巡检计划：

- `Patrol: Analysis Backlog`
- `Patrol: Analysis Failures`
- `Patrol: Approval Timeout`

对应动作分别是：

- `patrol.analysis_backlog`
- `patrol.analysis_failures`
- `patrol.approval_timeout`

## 5. 默认运行方式

默认由 `agent-service` 内部后台循环运行。

标准部署入口：

- `agents/agent_service/app.py`

内部实现位置：

- `agent/scheduler/main.py`
- `agent/service_runtime.py`
