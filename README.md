# Urban Insight

Urban Insight 是一个面向安防与运营场景的智能视频分析平台。当前仓库已经整理成适合部署和持续演进的结构，核心由三层组成：

- 前端客户端：`apps/web-console`
- 业务服务：`auth / media / analysis / search / insight`
- 常驻自主 Agent：`agent-service`

## 当前结构

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
├─ agent/              # agent 共享实现
├─ backend/            # 业务共享实现
├─ contracts/          # HTTP / event 契约
├─ deploy/             # Docker / Compose / Nginx
└─ docs/
```

## 系统形态

当前推荐形态不是“所有模块都拆成很多服务”，而是：

- 业务能力保持轻量微服务边界
- 自主能力集中在单一 `agent-service`
- 网关统一承载前端静态资源和 `/api` 反向代理
- PostgreSQL 作为主数据存储

这比过度拆分更适合当前阶段，部署更短、运行链路更稳定，也更容易把 24x7 Agent 做扎实。

## Agent 当前能力

当前 Agent 已经具备完整主链：

- 常驻运行：`runtime + scheduler + email` loop
- 短期状态：`session / message / run / scheduled_task / approval`
- 长期记忆：`MEMORY.md + daily notes`
- 自主规划：goal lifecycle、follow-up step、replan、recovery、verification
- 主动工作：memory distillation、proactive goal、patrol boost
- 策略闭环：strategy-aware execution + strategy feedback + feedback-aware rescheduling

详细设计见：

- [项目蓝图](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/docs/project-blueprint.md)
- [Agent 设计](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/docs/agent-ops-design.md)

## 启动方式

开发或本地验证：

```bash
docker compose up --build
```

标准部署入口：

```bash
docker compose -f deploy/compose/docker-compose.yml up --build
```

生产部署：

```bash
cp .env.example .env
docker compose --env-file .env -f deploy/compose/docker-compose.yml -f deploy/compose/docker-compose.prod.yml up -d --build
```

## 仓库校验

统一校验命令：

```bash
python scripts/validate_repo.py --install-frontend-deps
```

它当前会检查：

- 目录结构和 legacy 路径约束
- OpenAPI 契约导出
- Python 源码可编译
- Agent 自主链 smoke test
- 前端构建
- 前端依赖安全审计
- Docker Compose 配置

Agent 自主链专项校验也可以单独执行：

```bash
python scripts/validate_agent_autonomy.py
```

## 关键文档

- [企业级重构蓝图](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/docs/enterprise-refactor-blueprint.md)
- [项目蓝图](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/docs/project-blueprint.md)
- [Agent 设计](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/docs/agent-ops-design.md)
- [部署说明](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/deploy/README.md)
- [HTTP 契约说明](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/contracts/http/README.md)
