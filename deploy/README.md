# Deploy

`deploy/` 是当前唯一继续演进的部署目录。

目录约定：

- `compose/`
  - Docker Compose 入口
- `docker/`
  - Dockerfile
- `nginx/`
  - 网关配置

## 当前部署资产

当前标准部署文件：

- `deploy/compose/docker-compose.yml`
- `deploy/compose/docker-compose.prod.yml`
- `deploy/docker/python-service.Dockerfile`
- `deploy/docker/web-console.Dockerfile`
- `deploy/nginx/default.conf`
- `.env.example`

当前仓库不再维护旧的部署目录或旧的微服务外壳。

## 推荐启动方式

### 本地开发或单机联调

```bash
docker compose up --build
```

### 标准 Compose 启动

```bash
docker compose -f deploy/compose/docker-compose.yml up --build
```

### 生产部署

```bash
cp .env.example .env
docker compose --env-file .env -f deploy/compose/docker-compose.yml -f deploy/compose/docker-compose.prod.yml up -d --build
```

## 生产覆盖层说明

`deploy/compose/docker-compose.prod.yml` 在基础编排之上主要做两件事：

- 不再把 PostgreSQL 端口暴露到宿主机
- 通过 `GATEWAY_HTTP_PORT` 控制对外 HTTP 端口

## 健康检查

当前所有 Python 服务都暴露 `/health`。

`agent-service` 额外暴露：

- `/agent/runtime-status`

Compose 已经接入：

- `healthcheck`
- `depends_on: service_healthy`

## 部署前校验

提交或部署前建议执行：

```bash
python scripts/validate_repo.py --install-frontend-deps
```

该脚本当前会验证：

- 目录结构与 legacy 路径约束
- OpenAPI 契约导出
- Python 编译
- 一方文本编码/异常字符扫描
- Agent 自主链 smoke test
- 前端构建
- 前端依赖安全审计
- Docker Compose 配置

如果只想单独校验 Agent 自主链：

```bash
python scripts/validate_agent_autonomy.py
```

## 当前部署边界

当前标准部署集合：

- `gateway`
- `auth-service`
- `media-service`
- `analysis-service`
- `search-service`
- `insight-service`
- `agent-service`
- `postgres`

当前不默认启用：

- Redis
- MQ
- Object Storage
- Monitoring Stack

这些属于后续增强项，不属于当前默认交付面。
