# Urban Insight 企业级改造蓝图

## 1. 文档目的

这份文档定义 Urban Insight 从“可运行的轻量微服务 + 常驻 Agent”升级到“企业级可部署平台”的目标蓝图、目录结构、容器边界、协议契约与分阶段迁移计划。

它同时承担两个作用：

- 作为后续重构与部署的唯一高层蓝图
- 约束本仓库的目录重组与实现顺序，避免边改边散

## 2. 当前问题

当前仓库已经具备前后端分离、业务服务拆分、统一 Agent 服务和 Docker Compose 部署能力，但仍有几个结构性问题：

- 目录按历史演进组织过，旧结构遗留较多，边界曾经不够清晰
- 标准部署入口、契约文件与共享逻辑的边界仍需持续收敛
- 部署资产与业务源码一度混在一起，需要彻底用新结构约束后续开发
- 协议契约存在于代码中，但没有统一“contracts”落点
- Agent 已经可运行，但还缺少明确的平台层定位

## 3. 改造目标

目标不是把所有东西立刻拆成大量仓库，而是先把仓库整理成“可独立部署、可独立扩容、可清晰协作”的结构。

本项目的目标形态是：

- 用户端独立
- 业务服务独立
- Agent 平台独立
- 基础设施独立
- 协议契约独立
- 部署资产独立

## 4. 目标系统分层

### 4.1 客户端层

- `Web Console`
  - 浏览器访问
  - 主要用户入口
  - 通过网关访问后端与 Agent
- `Edge/Desktop App`（可选，后续阶段）
  - 仅当需要本地采集、离线上传、边缘接摄像头时再引入

### 4.2 接入层

- `gateway`
  - 统一 HTTPS 入口
  - 路由转发
  - 后续可扩展鉴权、限流、WAF、审计日志

### 4.3 业务服务层

- `auth-service`
- `media-service`
- `analysis-service`
- `search-service`
- `insight-service`

### 4.4 Agent 平台层

- `agent-service`
  - session / message / run / approval / alert / subscription
  - patrol scheduler
  - runtime worker
  - executor
  - email connector
  - workspace memory

企业级目标不是一开始再把 Agent 拆成 5 个服务，而是：

- 第一阶段保持 `agent-service` 单容器
- 第二阶段补 Redis / Queue / Object Storage / Monitoring
- 第三阶段再按负载拆为 `agent-api / agent-worker / agent-notifier / agent-scheduler`

### 4.5 基础设施层

- `postgres`
- `redis`（下一阶段）
- `object storage`（下一阶段）
- `message queue`（下一阶段）
- `monitoring stack`（下一阶段）

## 5. 目标仓库结构

```text
.
├─ apps/
│  └─ web-console/
├─ services/
│  ├─ auth_service/
│  ├─ media_service/
│  ├─ analysis_service/
│  ├─ search_service/
│  └─ insight_service/
├─ agents/
│  └─ agent_service/
├─ contracts/
│  ├─ http/
│  └─ events/
├─ deploy/
│  ├─ compose/
│  ├─ docker/
│  └─ nginx/
├─ backend/
├─ agent/
├─ scripts/
└─ docs/
```

说明：

- `services/` 存放“可部署服务入口”
- `agents/` 存放“可部署 Agent 入口”
- `backend/` 与 `agent/` 暂时保留为共享业务逻辑层
- `contracts/` 作为跨服务协议契约的固定位置
- `deploy/` 作为新的规范部署目录
- 旧 `microservices/` 兼容层已经退场，不再继续维护
- `scripts/validate_repo.py` 作为结构守卫，阻止 legacy 目录与失配契约回流

## 6. 协议与契约

### 6.1 外部协议

- 浏览器到网关：`HTTPS + REST`
- 邮件：`SMTP / IMAP`

### 6.2 内部同步协议

- 当前阶段：`HTTP + JSON`
- 规范要求：每个服务都应形成稳定的 OpenAPI 契约

### 6.3 内部异步事件

下一阶段引入消息队列后，至少应形成这些事件类型：

- `media.file.uploaded`
- `analysis.task.created`
- `analysis.task.completed`
- `agent.run.completed`
- `agent.alert.opened`
- `agent.alert.resolved`

### 6.4 契约管理原则

- HTTP 契约放在 `contracts/http/`
- 事件契约放在 `contracts/events/`
- 所有跨服务 payload 必须版本化
- 不允许服务之间依赖前端路由或页面逻辑

## 7. 数据边界

当前阶段允许共享 PostgreSQL，但必须明确逻辑边界：

- 业务数据：`users / media_files / analysis_tasks / analysis_records / insight_cache / system_config`
- Agent 数据：`agent_*`

下一阶段建议升级为：

- 先按 schema 逻辑分区
- 再视压力决定是否物理拆库

## 8. 容器蓝图

当前推荐容器集合：

- `gateway`
- `auth-service`
- `media-service`
- `analysis-service`
- `search-service`
- `insight-service`
- `agent-service`
- `postgres`

下一阶段扩容集合：

- `redis`
- `minio`
- `queue`
- `prometheus`
- `grafana`
- `loki`

## 9. Docker 与部署资产规范

企业级改造后，Docker 与部署资产放在 `deploy/`：

- `deploy/docker/python-service.Dockerfile`
- `deploy/docker/web-console.Dockerfile`
- `deploy/nginx/default.conf`
- `deploy/compose/docker-compose.yml`
- `deploy/compose/docker-compose.prod.yml`
- `.env.example`

要求：

- 镜像构建入口固定
- Compose 入口固定
- Docker 上下文必须排除运行时产物、参考仓库和历史目录
- 环境变量模板必须显式化，不允许部署时手拼隐式配置
- 服务健康检查必须纳入编排层
- 后续可平滑增加 `docker-compose.prod.yml`、Kubernetes manifests、Helm chart

## 10. 安全与运维要求

- 所有服务走环境变量注入配置
- 敏感信息不写死在仓库
- 每个服务具备健康检查
- 日志统一 stdout/stderr
- 告警统一进入 Agent/监控体系
- 关键路径可观测

## 11. 分阶段迁移计划

### Phase 1：结构归一

目标：

- 建立新目录骨架
- 迁移服务入口到 `services/` 与 `agents/`
- 引入 `deploy/`
- 清退旧 `microservices/` 兼容层

### Phase 2：部署与契约归一

目标：

- 统一 Compose 与 Dockerfile
- 建立 `contracts/http` 与 `contracts/events`
- 把 Web Console 正式迁到 `apps/web-console`
- 从标准入口自动导出 OpenAPI 契约

### Phase 3：平台化增强

目标：

- Redis
- Object storage
- Queue
- Monitoring
- Secrets

### Phase 4：Agent 扩容拆分

目标：

- 仅在负载和职责需要时再拆 Agent 子服务

## 12. 当前已完成

当前已经完成：

- 新增企业级蓝图文档
- 创建 `apps / services / agents / contracts / deploy` 目录
- 迁移业务服务与 Agent 的部署入口到新路径
- 新增规范化的 `deploy/compose` 和 `deploy/docker`
- Web Console 已迁入 `apps/web-console`
- 根 Compose 与新 Compose 都已切到新部署路径
- 已提供 `scripts/export_openapi_contracts.py`
- 已提供 `scripts/validate_repo.py`
- 已将 `contracts/http/*.openapi.json` 固化为标准 HTTP 契约
- 旧 `microservices/` 兼容层已清退
- 已补充 CI 工作流与更严格的 `.dockerignore`
- 已补充 `.env.example`、Compose 健康检查与生产 override

## 13. 不在本轮立即完成的事项

- 不强行搬迁全部 `backend/` 与 `agent/` 共享逻辑
- 不立即拆 Agent 为多个独立运行容器
- 不立即引入 Redis / MQ / MinIO / Prometheus

这些会在下一阶段继续推进，以保证重构期间系统可持续运行。
