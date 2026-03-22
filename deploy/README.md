# Deploy

这里是标准部署目录。

目录约定：

- `compose/`：Docker Compose 入口
- `docker/`：Dockerfile
- `nginx/`：网关配置

当前状态：

- `deploy/` 是唯一继续演进的部署目录
- 根目录 `docker-compose.yml` 与 `deploy/compose/docker-compose.yml` 都已切到新路径
- 旧部署结构已完成淘汰，不再继续维护
- `.env.example` 提供了统一环境变量模板
- `deploy/compose/docker-compose.prod.yml` 提供了生产覆盖层

## 推荐流程

开发或单机验证：

```bash
docker compose up --build
```

生产部署：

```bash
cp .env.example .env
docker compose --env-file .env -f deploy/compose/docker-compose.yml -f deploy/compose/docker-compose.prod.yml up -d --build
```

生产覆盖层当前会额外做两件事：

- 不再暴露 PostgreSQL 到宿主机
- 保持网关公开端口由 `GATEWAY_HTTP_PORT` 控制

## 健康检查

现在所有 Python 服务都暴露 `/health`，`agent-service` 额外暴露 `/agent/runtime-status`，Compose 已经接入健康检查和 `depends_on: service_healthy`。

推荐在提交前运行：

```bash
python scripts/validate_repo.py --install-frontend-deps
```
