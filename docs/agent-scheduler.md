# Agent Scheduler 第一版

## 1. 作用

`agent-scheduler` 负责把 `agent_scheduled_task` 变成真正会自动派发的后台计划任务。

它当前负责：

- 轮询 control plane
- 找出已经到期的 scheduled task
- 派发成新的 `agent_run`
- 避免同一任务在已有活动 run 时重复堆积
- 计算下一次 `next_run_at`

## 2. 关键能力

当前版本已经支持：

- `cron` 表达式校验
- `timezone` 校验
- 按 `cron + timezone` 计算下一次触发时间
- 手动 `trigger`
- 自动 `dispatch-due`
- `reuse_session=true/false`
- 发现已有活动 run 时跳过并重算下次执行时间

## 3. 关键文件

- `agent/control_plane/services.py`
- `agent/control_plane/routers/scheduled_tasks.py`
- `agent/scheduler/config.py`
- `agent/scheduler/client.py`
- `agent/scheduler/worker.py`
- `agent/scheduler/main.py`
- `microservices/agent_scheduler/main.py`

## 4. 新增接口

### `POST /agent/scheduled-tasks/dispatch-due`

由 scheduler 调用。

返回：

```json
{
  "dispatched": 1,
  "skipped": 0,
  "run_ids": ["..."]
}
```

## 5. 调度策略

当前策略是：

- 只调度 `enabled=true` 且 `next_run_at <= now` 的任务
- 若该 `scheduled_task_id` 已存在 `queued/claimed/running/waiting_approval/waiting_input` 的活动 run，则本次跳过
- 跳过时也会重算 `next_run_at`，防止反复命中同一批 due task
- 成功派发后立刻更新 `last_run_id / last_run_status / next_run_at`

## 6. 运行方式

单次派发：

```bash
python -m microservices.agent_scheduler.main --once
```

持续运行：

```bash
python -m microservices.agent_scheduler.main
```

## 7. 下一步建议

有了 scheduler 之后，下一步最适合做的就是首批巡检模板：

- analysis backlog patrol
- failure rate patrol
- camera silence patrol
- storage patrol
- approval timeout patrol
