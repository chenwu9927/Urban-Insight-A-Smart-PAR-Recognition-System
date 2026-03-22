# Gateway Routing Contract

这份文档定义网关到内部服务的标准转发边界。

## 目标

- 保证前端只访问 `/api`
- 保证服务边界稳定
- 为后续 OpenAPI 拆分提供最小契约

## 路由归属

### auth-service

- `/api/auth/*`
- `/api/users*`

### media-service

- `/api/files*`
- `/api/uploads/*`

### analysis-service

- `/api/analyze/*`
- `/api/history*`
- `/api/thumbnails/*`

### search-service

- `/api/search*`

### insight-service

- `/api/stats*`
- `/api/insights*`
- `/api/settings/*`

### agent-service

- `/api/agent/*`
- `/api/email/*`

## 约束

- 前端不得直接访问服务容器地址
- 服务间调用不得绕经网关
- 新增 API 时必须先定义归属服务
- 网关规则变更时应同步更新本文件与 Nginx 配置
