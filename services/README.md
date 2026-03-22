# Services

这里存放业务服务的标准部署入口。

当前阶段这些服务已经迁入：

- `auth_service`
- `media_service`
- `analysis_service`
- `search_service`
- `insight_service`

共享业务逻辑仍在 `backend/`，后续再逐步下沉和去耦。

这些入口也是 HTTP 契约的唯一导出源，统一通过：

- `python scripts/export_openapi_contracts.py`

写入 `contracts/http/*.openapi.json`。
