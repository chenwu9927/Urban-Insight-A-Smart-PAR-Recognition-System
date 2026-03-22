# HTTP Contracts

这里存放前后端与服务间的 HTTP 契约。

## 当前文件

- `gateway-routing-contract.md`
- `auth-service.openapi.json`
- `media-service.openapi.json`
- `analysis-service.openapi.json`
- `search-service.openapi.json`
- `insight-service.openapi.json`
- `agent-service.openapi.json`

## 生成方式

OpenAPI 文件不手写，统一从标准部署入口导出：

```bash
python scripts/export_openapi_contracts.py
```

脚本会自动进入 `contract-export` 模式，避免导出契约时触发数据库初始化、模型加载和 LLM 配置。

生成源头固定为：

- `services/*/app.py`
- `agents/agent_service/app.py`

约束：

- `gateway-routing-contract.md` 仍然是人工维护的网关边界文档
- 每次新增或调整 HTTP 路由后，都应重新导出这些契约文件
- 不再从 legacy 入口生成契约，避免双轨结构继续扩散
