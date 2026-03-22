# Urban Insight

Urban Insight 是一个面向安防与运营场景的智能视频分析平台，当前由三部分组成：

- 用户侧 `Web Console`
- 业务微服务：`auth / media / analysis / search / insight`
- 一个 24x7 常驻运行的 `agent-service`

## 当前推荐结构

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
├─ deploy/
│  ├─ compose/
│  ├─ docker/
│  └─ nginx/
├─ backend/         # 共享业务逻辑
└─ agent/           # 共享 agent 逻辑
```

## 启动方式

默认入口：

```bash
docker compose up --build
```

规范化入口：

```bash
docker compose -f deploy/compose/docker-compose.yml up --build
```

生产部署推荐先准备环境文件：

```bash
cp .env.example .env
```

然后使用生产 override：

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.yml -f deploy/compose/docker-compose.prod.yml up -d --build
```

## 校验方式

本仓库现在有一条统一校验命令：

```bash
python scripts/validate_repo.py --install-frontend-deps
```

它会检查：

- 新结构目录是否完整
- `frontend / deployment / microservices` 等 legacy 路径是否回流
- OpenAPI 契约是否可重新导出
- Python 源码是否可编译
- `apps/web-console` 是否可构建
- 两个 Compose 入口是否仍然有效
- 生产 Compose override 是否仍然能与 `.env.example` 对齐解析

## 关键文档

- 企业级改造蓝图：[docs/enterprise-refactor-blueprint.md](docs/enterprise-refactor-blueprint.md)
- 项目蓝图：[docs/project-blueprint.md](docs/project-blueprint.md)
- Agent 设计：[docs/agent-ops-design.md](docs/agent-ops-design.md)
- HTTP 契约：[contracts/http/README.md](contracts/http/README.md)
- 部署目录说明：[deploy/README.md](deploy/README.md)

## 当前约束

- Web Console 正式位于 `apps/web-console`
- 业务服务标准入口位于 `services/*`
- Agent 标准入口位于 `agents/agent_service`
- HTTP 契约统一沉淀到 `contracts/http/*.openapi.json`
- 新部署资产统一放在 `deploy/`
- CI 会通过 `scripts/validate_repo.py` 守住这些结构约束
