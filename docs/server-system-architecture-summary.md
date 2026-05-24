# Urban Insight 服务器系统架构总结

生成时间：2026-04-12
服务器项目目录：`/opt/urban-insight`
依据：服务器当前代码、`docker-compose.yml`、Nginx 网关配置和运行中的 Docker Compose 容器状态。

> 本文档不记录邮箱授权码、LLM API Key、数据库密码等敏感值。邮箱系统现状只描述为“外部 163 邮箱 POP3/SMTP 接入”。

## 1. 系统软件体系结构

### 1.1 总体结构

当前服务器部署已经是“前端网关 + 多个轻量业务微服务 + 单一常驻 agent-service + PostgreSQL”的企业化结构：

| 层次 | 组件 | 说明 |
| --- | --- | --- |
| 入口层 | `gateway` / Nginx | 承载 Web Console 静态文件，按 `/api/*` 路径把请求转发到内部服务；对核心 API 先调用 `auth-service` 做会话校验。 |
| 前端层 | `apps/web-console` | 构建后由网关容器的 Nginx 静态目录提供；用户通过浏览器访问首页、任务、检索、洞察、Agent 页面。 |
| 身份层 | `auth-service` | FastAPI 服务，负责登录、登出、当前用户、用户管理、会话 Cookie 校验。 |
| 媒体层 | `media-service` | FastAPI 服务，负责图片/视频上传、文件列表、删除、上传文件静态读取。 |
| 分析层 | `analysis-service` | FastAPI 服务，负责任务创建、后台分析队列、结构化 CV 分析、语义 VLM 分析、任务状态和分析记录读取。 |
| 检索层 | `search-service` | FastAPI 服务，负责结构化检索、自然语言检索，并持有更重的 ConvNeXtV2 属性模型和 OSNet ReID 能力。 |
| 洞察层 | `insight-service` | FastAPI 服务，负责统计、洞察、简报、LLM 配置读写与连通性测试。 |
| Agent 层 | `agent-service` | 单一常驻 Agent 服务，包含控制面 API、执行器、调度器、运行时循环、邮件连接器、记忆与工具注册表。 |
| 数据层 | `postgres` | PostgreSQL 16，保存业务表、分析结果、系统配置、Agent 会话/消息/目标/运行等。 |
| 外部系统 | LongCat/OpenAI-compatible LLM、163 邮箱 POP3/SMTP、可选语义 VLM 接口 | LLM 用于洞察和 Agent 推理；163 邮箱用于 Agent 邮件闭环；语义 VLM 接口未配置时会降级 fallback。 |

服务间通过 Docker 内部网络使用服务名访问，例如 `agent-service` 调用 `analysis-service:8000`、`search-service:8000`、`insight-service:8000`。浏览器不直接访问内部服务，而是统一走 Nginx 网关。

### 1.2 微服务划分

#### gateway

`gateway` 是唯一对外 HTTP 入口。当前运行容器为 `urban-insight-gateway-1`，主机绑定端口为 `127.0.0.1:8081 -> 80`，由外部反向代理或服务器入口再转发到该端口。

Nginx 的主要路由规则：

| 外部路径 | 内部目标 |
| --- | --- |
| `/api/auth/*`、`/api/users*` | `auth-service:8000` |
| `/api/files`、`/api/uploads/*` | `media-service:8000` |
| `/api/analyze/*`、`/api/analysis/*`、`/api/history*`、`/api/thumbnails/*` | `analysis-service:8000` |
| `/api/search*` | `search-service:8000` |
| `/api/stats`、`/api/insights`、`/api/settings/*` | `insight-service:8000` |
| `/api/agent/*`、`/api/email/*` | `agent-service:8000` |
| 其他路径 | 前端 SPA，`try_files $uri $uri/ /index.html` |

其中 Nginx 配置了内部 `= /__auth_check`，会把请求代理到 `auth-service:8000/auth/me` 进行鉴权。需要会话的 API 在网关层先执行鉴权，再进入对应业务服务。

#### auth-service

`auth-service` 是身份认证边界。它使用 Cookie 会话：

- 登录成功后写入 `session_token`。
- 会话由 `AUTH_SESSION_SECRET` 做 HMAC 签名。
- 默认 TTL 为 86400 秒。
- 主要能力：`/auth/login`、`/auth/logout`、`/auth/me`、用户列表、修改密码。

该服务只挂载认证相关 router，避免其他服务直接处理登录状态。

#### media-service

`media-service` 负责媒体文件入口，核心流程：

1. `POST /files/upload` 接收上传文件。
2. 校验文件类型，只允许图片或视频。
3. 保存到共享上传目录 `UPLOAD_DIR`。
4. 写入 `media_files` 表，记录 `filename`、`original_filename`、`file_type`、`file_size`、`start_time` 等。
5. 提供 `GET /files`、`DELETE /files/{file_id}`。

删除文件时会清理关联数据，包括分析记录、分析任务、报告、缩略图和缓存。上传文件本身通过 `/files` router 与 `/uploads` 静态挂载一起对外提供。

#### analysis-service

`analysis-service` 是视频/图片分析任务的主执行边界。它提供：

- `POST /analyze/{file_id}`：创建分析任务。
- `GET /analyze/tasks/{task_id}`：读取单个任务状态。
- `GET /analyze/tasks`：读取任务列表。
- `GET /analysis/records/{record_id}`：读取完整分析记录。
- `GET /analysis/records/{record_id}/semantic`：读取语义 VLM 结果。

分析服务当前支持三种 pipeline：

| pipeline | 说明 |
| --- | --- |
| `classic_cv` | 结构化识别链：YOLO 检测、属性识别、ReID/跟踪、颜色提取、缩略图输出。 |
| `semantic_vlm` | 语义研判链：视频抽帧、逐帧自然语言描述、时间窗口聚合、视频级洞察。 |
| `dual` | 双链路：视频同时运行结构化 CV 和语义 VLM；图片只运行 classic，并记录语义跳过原因。 |

任务执行模型：

- API 请求只创建任务并入队，不在请求线程里长时间执行模型推理。
- 服务内部维护 `queue.Queue[int]` 和后台 `analysis-worker` 线程。
- `analysis_tasks` 表保存任务状态、进度、错误、pipeline、关联 file/record。
- `analysis_records` 表保存结构化结果和语义结果。

#### search-service

`search-service` 是检索边界，当前用于结构化检索和自然语言检索。它启用 recognizer，并承载更重的模型能力：

- ConvNeXtV2 属性模型。
- OSNet ReID。
- 结构化属性检索。
- 自然语言检索。

因为服务器内存约 3.6 GiB，部署策略故意把模型分摊：

- `analysis-service` 使用较轻的 MobileNetV4 属性模型，不启用独立 ReID。
- `search-service` 使用 ConvNeXtV2 属性模型和 OSNet ReID。

这是资源约束下的设计取舍，不是模型遗漏。

#### insight-service

`insight-service` 负责统计、简报、洞察和 LLM 配置：

- `GET /stats`：统计摘要与时间序列。
- `GET /insights`：洞察列表。
- `POST /insights/ask`：针对系统数据提问。
- `GET /insights/brief`：生成面向运营的简报。
- `GET /settings/llm`：读取 LLM 配置。
- `POST /settings/llm`：保存 LLM 配置，需要 admin 会话。
- `POST /settings/llm/test`：测试 LLM 配置，需要 admin 会话。

LLM 调用通过 OpenAI-compatible 接口，当前环境配置指向 LongCat：

- `LLM_BASE_URL=https://api.longcat.chat/openai`
- `LLM_MODEL=LongCat-Flash-Lite`

#### agent-service

`agent-service` 是单一常驻 Agent 容器，不再继续拆成多个 agent 子服务。它把以下能力放在同一个进程内：

- Agent 控制面 API。
- Agent 执行器。
- 运行时循环。
- 调度器循环。
- 邮件连接器循环。
- Agent supervisor。
- 工具注册表。
- 短期记忆与长期记忆访问。

容器进程命令为：

```text
uvicorn agents.agent_service.app:app --host 0.0.0.0 --port 8000
```

它通过内部服务 URL 调用其他微服务：

- `AUTH_SERVICE_URL`
- `MEDIA_SERVICE_URL`
- `ANALYSIS_SERVICE_URL`
- `SEARCH_SERVICE_URL`
- `INSIGHT_SERVICE_URL`

### 1.3 管道与过滤器结构

系统的“微服务”是部署边界，“管道与过滤器”是关键业务流程内部的计算结构。

#### 1.3.1 上传到分析的主链路

完整主链路如下：

1. 浏览器上传视频或图片到 `/api/files/upload`。
2. `gateway` 鉴权后把请求转发给 `media-service`。
3. `media-service` 保存文件并写入 `media_files`。
4. 前端或 Agent 调用 `/api/analyze/{file_id}`。
5. `gateway` 转发到 `analysis-service`。
6. `analysis-service` 创建 `AnalysisTask`，按指定 pipeline 入队。
7. `analysis-worker` 从队列取任务。
8. 根据 pipeline 执行 `classic_cv`、`semantic_vlm` 或 `dual`。
9. 结果写入 `analysis_records`。
10. 前端或 Agent 读取任务状态和分析记录。

#### 1.3.2 classic_cv 管道

结构化 CV 管道的目标是输出可检索、可统计的结构化行人结果。

过滤器序列：

| 阶段 | 过滤器 | 输入 | 输出 |
| --- | --- | --- | --- |
| 1 | 媒体读取 | 图片或视频文件 | 图像帧 |
| 2 | 帧采样 | 视频流 | 采样帧、时间戳 |
| 3 | YOLO person detection | 图像帧 | 行人 bbox、置信度 |
| 4 | crop | bbox | 行人裁剪图 |
| 5 | attribute predictor | 行人裁剪图 | 年龄组、朝向、二值属性等 |
| 6 | dominant color extraction | 行人裁剪图 | 上衣/下装主色 |
| 7 | ReID / IoU tracker | 行人 embedding、bbox、时间戳 | track id、跨帧聚合 |
| 8 | thumbnail writer | 裁剪图、track 信息 | 缩略图文件 |
| 9 | result assembler | 属性、颜色、轨迹、缩略图 | `pedestrians` 结构化结果 |
| 10 | persistence | `pedestrians`、统计信息 | `analysis_records.results` |

视频分析内部进一步使用线程和队列做并行过滤：

- `video-reader`：读取视频并按采样间隔产出帧。
- `video-detector`：对帧运行 YOLO 检测。
- `video-analyzer`：属性识别、颜色提取、跟踪聚合。
- `video-thumb-writer`：异步写缩略图。

这条链路的特征是强结构化：结果主要服务于检索、统计、属性过滤、人员再识别和任务详情页展示。

#### 1.3.3 semantic_vlm 管道

语义 VLM 管道的目标不是替代 classic_cv，而是补充“发生了什么、风险是什么、建议怎么处置”的自然语言研判能力。

过滤器序列：

| 阶段 | 过滤器 | 输入 | 输出 |
| --- | --- | --- | --- |
| 1 | `FrameSampler` | 视频文件 | 抽样帧、时间戳、fps、duration |
| 2 | `QwenFrameNarrator` | 抽样帧 | 每帧自然语言描述 |
| 3 | `SemanticWindowAggregator` | 帧描述、时间戳 | 时间窗口摘要、行为、风险信号、证据时间点 |
| 4 | `VideoSemanticAnalyst` | 窗口摘要 | 视频级风险等级、事件链、运营建议、Agent follow-up |
| 5 | `SemanticVideoWorkflow` | 上述所有结果 | `semantic_results`、`window_summaries`、`video_insights`、`pipeline_meta` |
| 6 | persistence | 语义结果 | `analysis_records.semantic_results` 等字段 |

当前语义链路支持 OpenAI-compatible 多模态接口。关键环境变量包括：

- `SEMANTIC_VLM_SAMPLE_FPS`，默认约 1 fps。
- `SEMANTIC_VLM_MAX_FRAMES`，默认约 180 帧。
- `SEMANTIC_VLM_WINDOW_SECONDS`，默认约 30 秒窗口。
- `SEMANTIC_VLM_API_BASE_URL` 或 `OPENAI_BASE_URL`。
- `SEMANTIC_VLM_MODEL`，默认写法为 `Qwen/Qwen3.5-0.8B`。

若没有配置真实 VLM 服务，`QwenFrameNarrator` 会返回 fallback 描述，不会让分析主链路崩溃。当前你要求先不下载 Qwen 模型，所以服务器上这条链路处于“后端骨架可运行、真实本地模型未落地”的阶段。

#### 1.3.4 Agent 执行管道

Agent 的执行也采用管道与过滤器思想：

1. 触发源进入系统：Web chat、定时任务、目标生命周期、告警、邮件、手动 run。
2. 控制面写入 `agent_runs`。
3. runtime 或 executor 领取 run。
4. `AgentContextBuilder` 构造上下文：系统身份、工作区、短期记忆、长期记忆、当前状态、战略上下文、可用工具。
5. LLM tool loop 或 fallback executor 决策要调用的工具。
6. `ApiOnlyExecutionService` 根据 `action` 分发到内部工具。
7. 工具调用其他微服务或读写 Agent memory。
8. 结果写回 run、message、goal、memory 或 delivery。
9. 如果来自邮件，邮件连接器通过 SMTP 发送 ACK 或最终结果。

Agent 提示词已经适配第二条语义工作流：当问题涉及行为、场景、异常解释、视频摘要时，优先读取语义分析结果，即 `analysis.get_semantic_record` 或完整 `analysis.get_record`。

### 1.4 数据模型概览

业务表：

| 表 | 用途 |
| --- | --- |
| `users` | 用户与角色。 |
| `media_files` | 上传文件元数据。 |
| `analysis_tasks` | 分析任务状态、进度、pipeline。 |
| `analysis_records` | 分析结果，包含结构化结果、语义结果、窗口摘要、视频洞察、pipeline 元信息。 |
| `analysis_reports` | 分析报告。 |
| `insight_cache` | 洞察缓存。 |
| `system_config` | LLM 等系统级配置。 |

Agent 表：

| 表 | 用途 |
| --- | --- |
| `agent_sessions` | Agent 会话。 |
| `agent_messages` | Agent 消息。 |
| `agent_goals` | 目标生命周期。 |
| `agent_runs` | 执行记录。 |
| `agent_scheduled_tasks` | 定时任务。 |
| `agent_approval_requests` | 审批请求。 |
| `agent_incidents` | 事件。 |
| `agent_alerts` | 告警。 |
| `agent_subscriptions` | 订阅。 |
| `agent_artifacts` | 产物。 |
| `agent_memory_items` | Agent 记忆项。 |
| `agent_memory_jobs` | 记忆作业。 |
| `agent_connector_deliveries` | 邮件等连接器投递记录。 |
| `agent_dedup_events` | 去重事件。 |

## 2. 容器编排

### 2.1 当前运行容器

当前服务器 Docker Compose 栈包含以下主要容器：

| 容器 | 镜像 | 角色 | 当前状态 |
| --- | --- | --- | --- |
| `urban-insight-gateway-1` | `urban-insight-gateway` | Nginx 网关和 Web Console 静态资源 | healthy |
| `urban-insight-auth-service-1` | Compose 构建 Python 服务 | 身份认证 | healthy |
| `urban-insight-media-service-1` | Compose 构建 Python 服务 | 文件上传与媒体管理 | healthy |
| `urban-insight-analysis-service-1` | Compose 构建 Python 服务 | 分析任务与模型推理 | healthy |
| `urban-insight-search-service-1` | Compose 构建 Python 服务 | 检索与重模型能力 | healthy |
| `urban-insight-insight-service-1` | Compose 构建 Python 服务 | 统计、洞察、LLM 配置 | healthy |
| `urban-insight-agent-service-1` | Compose 构建 Python 服务 | 常驻 Agent | healthy |
| `urban-insight-postgres-1` | `postgres:16-alpine` | 数据库 | healthy |

`mail-server` 仍可能作为 Compose profile `mail` 的历史配置存在，但当前自建邮箱容器已经停用，不作为主链路依赖。Agent 邮件闭环改为外部 `urbaninsights@163.com` 邮箱，通过 POP3/SMTP 接入。IMAP 是否可用取决于 163 的安全登录策略，系统当前应优先使用已验证的 POP3/SMTP 链路。

### 2.2 构建与启动方式

业务 Python 服务统一使用：

```text
deploy/docker/python-service.Dockerfile
```

前端网关使用：

```text
deploy/docker/web-console.Dockerfile
```

Python 服务通过不同的 uvicorn app entrypoint 区分角色：

| 服务 | app entrypoint |
| --- | --- |
| `auth-service` | `services.auth_service.app:app` |
| `media-service` | `services.media_service.app:app` |
| `analysis-service` | `services.analysis_service.app:app` |
| `search-service` | `services.search_service.app:app` |
| `insight-service` | `services.insight_service.app:app` |
| `agent-service` | `agents.agent_service.app:app` |

### 2.3 环境变量与共享配置

Compose 使用共享的 backend env：

| 变量 | 作用 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 连接串。 |
| `UPLOAD_DIR` | 上传文件目录。 |
| `THUMBNAIL_DIR` | 缩略图目录。 |
| `ALLOWED_ORIGINS` | CORS 白名单。 |
| `OPENAI_API_KEY`、`LLM_API_KEY` | LLM API Key 来源，文档不记录实际值。 |
| `LLM_BASE_URL` | LongCat/OpenAI-compatible API 地址。 |
| `LLM_MODEL` | 当前默认模型。 |
| `LLM_CACHE_TTL_SECONDS` | 洞察缓存 TTL。 |
| `AUTH_SESSION_SECRET` | 会话签名密钥。 |

Agent 服务额外使用：

| 变量 | 作用 |
| --- | --- |
| `AUTH_SERVICE_URL` | 内部访问 auth-service。 |
| `MEDIA_SERVICE_URL` | 内部访问 media-service。 |
| `ANALYSIS_SERVICE_URL` | 内部访问 analysis-service。 |
| `SEARCH_SERVICE_URL` | 内部访问 search-service。 |
| `INSIGHT_SERVICE_URL` | 内部访问 insight-service。 |
| `AGENT_RUNTIME_ENABLED` | 启用运行时循环。 |
| `AGENT_SCHEDULER_ENABLED` | 启用调度循环。 |
| `AGENT_EMAIL_ENABLED` | 启用邮件连接器循环。 |
| `AGENT_SUPERVISOR_ENABLED` | 启用 supervisor。 |
| `EMAIL_POP3_*`、`EMAIL_SMTP_*` | 外部邮箱收发配置。 |

### 2.4 Volume

Compose 的主要持久化卷：

| Volume | 用途 |
| --- | --- |
| `postgres-data` | PostgreSQL 数据。 |
| `uploads-data` | 上传文件。 |
| `thumbnails-data` | 缩略图。 |
| `agent-email-outbox-data` | Agent 邮件 outbox。 |
| `agent-email-state-data` | Agent 邮件轮询状态。 |
| `agent-workspace-data` | Agent 工作区和长期记忆。 |
| `mail-server-data` | 历史自建邮箱服务数据卷；当前主链路不依赖。 |

### 2.5 访问入口

当前展示和测试建议优先使用 IP：

```text
http://119.45.17.207/
http://119.45.17.207/agent
```

域名 `urbaninsights.site` 已配置过 DNS 和邮件相关记录，但备案/链路可用性曾经不稳定，因此 IP 入口仍是最稳入口。

## 3. Agent 相关信息

### 3.1 Agent 所在容器

Agent 全部运行在：

```text
urban-insight-agent-service-1
```

代码入口：

```text
agents/agent_service/app.py
```

运行方式：

```text
uvicorn agents.agent_service.app:app --host 0.0.0.0 --port 8000
```

该容器不是一次性 worker，而是常驻服务。它启动后会创建 `AgentServiceRuntime`，并根据环境变量启动以下循环：

| 循环 | 作用 |
| --- | --- |
| runtime loop | 管理 agent run 生命周期，领取、执行、写回。 |
| scheduler loop | 派发到期的定时任务。 |
| email loop | 从外部邮箱拉取入站邮件、生成 run、处理出站邮件。 |
| supervisor loop | 监督 runtime/scheduler/email 状态。 |

### 3.2 Agent 控制面 API

`agent-service` 对外经网关暴露在 `/api/agent/*` 和 `/api/email/*` 下，内部路由包括：

| API | 作用 |
| --- | --- |
| `GET /agent/overview` | Agent 总览、计数、近期 run、审批、会话。 |
| `GET /agent/runtime-status` | Agent 运行时循环状态快照。 |
| `GET /agent/tools` | 工具注册表列表。 |
| `GET /agent/tools/{action}` | 单个工具定义。 |
| `GET /agent/sessions`、`POST /agent/sessions` | 会话列表和创建。 |
| `GET /agent/messages/unified` | 统一消息流。 |
| `GET /agent/sessions/{session_id}` | 会话详情。 |
| `GET /agent/sessions/{session_id}/messages` | 会话消息列表。 |
| `POST /agent/sessions/{session_id}/messages` | 发送用户消息。 |
| `PATCH /agent/sessions/{session_id}` | 更新会话。 |
| `DELETE /agent/sessions/{session_id}` | 删除会话。 |
| `GET /agent/runs`、`POST /agent/runs` | run 列表和创建。 |
| `GET /agent/runs/{run_id}` | run 详情。 |
| `POST /agent/runs/claim` | 领取待执行 run。 |
| `POST /agent/runs/{run_id}/heartbeat` | run 心跳。 |
| `POST /agent/runs/{run_id}/complete` | run 成功写回。 |
| `POST /agent/runs/{run_id}/fail` | run 失败写回。 |
| `GET /agent/goals`、`GET /agent/goals/{goal_id}` | 目标列表与详情。 |
| `GET /agent/goals/{goal_id}/runs` | 某目标关联的 run。 |
| `POST /agent/goals/sweep` | goal lifecycle sweep。 |
| `POST /agent/goals/proactive-from-memory` | 从记忆生成 proactive goal。 |
| `GET /agent/alerts`、`GET /agent/alerts/{alert_id}` | 告警列表与详情。 |
| `GET /agent/scheduled-tasks`、`POST /agent/scheduled-tasks` | 定时任务列表与创建。 |
| `GET /agent/scheduled-tasks/{task_id}` | 定时任务详情。 |
| `PUT /agent/scheduled-tasks/{task_id}` | 更新定时任务。 |
| `DELETE /agent/scheduled-tasks/{task_id}` | 删除定时任务。 |
| `POST /agent/scheduled-tasks/{task_id}/trigger` | 手动触发定时任务。 |
| `POST /agent/scheduled-tasks/dispatch-due` | 派发到期任务。 |
| `POST /agent/scheduled-tasks/bootstrap-defaults` | 初始化默认任务。 |
| `POST /agent/scheduled-tasks/boost-from-memory` | 根据记忆增强巡检任务。 |
| `GET /agent/approvals`、`POST /agent/approvals` | 审批列表与创建。 |
| `GET /agent/approvals/{approval_id}` | 审批详情。 |
| `POST /agent/approvals/{approval_id}/answer` | 审批答复。 |
| `GET /agent/subscriptions`、`POST /agent/subscriptions` | 订阅列表与创建。 |
| `GET /agent/subscriptions/{subscription_id}` | 订阅详情。 |
| `PUT /agent/subscriptions/{subscription_id}` | 更新订阅。 |
| `DELETE /agent/subscriptions/{subscription_id}` | 删除订阅。 |
| `POST /agent/events` | 事件摄入。 |
| `GET /agent/deliveries`、`POST /agent/deliveries` | 连接器投递记录。 |
| `POST /email/inbound` | 邮件入站处理入口。 |
| `POST /email/process-outbound` | 处理出站邮件。 |
| `GET /email/outbox` | 邮件 outbox 列表。 |
| `POST /execute` | 执行器入口，内部执行 agent run。 |

### 3.3 Agent 工具注册表

Agent 工具定义来自 `agent/tool_registry.py`，并通过 `/agent/tools` 暴露。工具的 `action` 是执行器分发的核心字段。

风险等级说明：

- `R0`：只读或低风险。
- `R1`：会触发分析、检索、LLM 查询或巡检，但不直接破坏数据。
- `R2`：会写长期记忆等更持久的状态，建议审批或至少保留审计。

| action | 类别 | 目标 | 参数 | 输出 | 风险/审批 |
| --- | --- | --- | --- | --- | --- |
| `agent.get_overview` | agent | agent-control-plane | 无 | `counts`、`active_runs`、`recent_runs`、`pending_approvals`、`recent_sessions` | R0，无审批 |
| `agent.get_runtime_status` | agent | agent-service | 无 | `started_at`、`loops` | R0，无审批 |
| `agent.list_alerts` | agent | agent-control-plane | `status?: string = open`、`severity?: string`、`limit?: integer = 10` | `alerts` | R0，无审批 |
| `agent.list_goals` | agent | agent-control-plane | `status?: string`、`limit?: integer = 10` | `goals` | R0，无审批 |
| `agent.get_goal` | agent | agent-control-plane | `goal_id: string` | `goal` | R0，无审批 |
| `stats.get` | insight | insight-service | `interval?: integer = 60` | `summary`、`counts`、`series` | R0，无审批 |
| `insights.get_brief` | insight | insight-service | 无必填参数；执行器默认 `interval = 60` | `brief`、`generated_at` | R0，无审批 |
| `insights.ask` | insight | insight-service | `question: string`、`interval?: integer = 60`、`use_llm?: boolean = true` | `answer`、`supporting_stats` | R1，无审批 |
| `search.structured` | search | search-service | `query: object` | `items`、`total` | R1，无审批 |
| `search.nl` | search | search-service | `query: string` | `items`、`answer`、`total` | R1，无审批 |
| `analysis.get_task` | analysis | analysis-service | `task_id: string` | `task` | R0，无审批 |
| `analysis.get_record` | analysis | analysis-service | `record_id: integer` | `record` | R0，无审批 |
| `analysis.get_semantic_record` | analysis | analysis-service | `record_id: integer` | `semantic_results`、`window_summaries`、`video_insights`、`pipeline_meta` | R0，无审批 |
| `agent.chat` | agent | agent-service | `question?: string` | `answer`、`tool_events`、`session_summary`、`goal_summary`、`planned_steps` | R1，无审批 |
| `patrol.analysis_backlog` | patrol | analysis-service | `stale_minutes?: integer = 15`、`alert_threshold?: integer = 5` | `breached`、`stale_task_count`、`stale_tasks` | R1，无审批 |
| `patrol.analysis_failures` | patrol | analysis-service | `window_minutes?: integer = 60`、`alert_threshold?: integer = 3` | `breached`、`failed_task_count`、`failed_tasks` | R1，无审批 |
| `patrol.approval_timeout` | patrol | agent-control-plane | `older_than_minutes?: integer = 30`、`alert_threshold?: integer = 1` | `breached`、`timed_out_approval_count`、`timed_out_approvals` | R1，无审批 |
| `memory.get_context` | memory | agent-memory | `days?: integer = 3` | `context`、`days` | R0，无审批 |
| `memory.read_long_term` | memory | agent-memory | 无 | `content` | R0，无审批 |
| `memory.write_long_term` | memory | agent-memory | `content: string` | `path` | R2，建议审批，非幂等 |
| `memory.append_daily_note` | memory | agent-memory | `content: string`、`heading?: string` | `path`、`heading` | R1，无审批，非幂等 |

### 3.4 Agent 具备的功能

当前 Agent 已经具备以下主链能力：

- 短期记忆：`session`、`message`、`run`。
- 长期记忆：`MEMORY.md` 和 daily notes。
- goal lifecycle。
- proactive goal。
- strategy-aware execution。
- strategy feedback。
- feedback-aware rescheduling。
- 邮件闭环：外部 163 邮箱 POP3 拉取、SMTP 回复、投递状态记录。
- 运行时巡检：分析积压、分析失败、审批超时。
- 系统工具接入：统计、洞察、结构化检索、自然语言检索、分析任务、分析记录、语义分析记录。
- 语义优先上下文：遇到行为、场景、异常解释、视频摘要问题时，优先读取 `analysis.get_semantic_record` 或完整记录。
- fallback 执行：LLM 不可用或某些 Web 会话场景下，可以使用规则化 fallback 读取 overview、runtime、alerts、insights 等信息。

### 3.5 Agent 与邮件系统

当前自建邮箱服务不可用后，系统改用外部邮箱：

```text
urbaninsights@163.com
```

安全说明：

- 文档不记录授权码。
- 发送使用 SMTP over SSL。
- 接收优先使用 POP3 over SSL。
- 163 的 IMAP 可能因安全登录策略拒绝，所以不作为当前最稳链路。

Agent 邮件流程：

1. 管理员向 `urbaninsights@163.com` 发送邮件。
2. `agent-service` email loop 通过 POP3 拉取新邮件。
3. 邮件连接器将邮件转换成 Agent run。
4. Agent 执行后生成 ACK 或最终结果。
5. 通过 SMTP 发送回复。
6. 投递结果写入 `agent_connector_deliveries` 和 outbox/state volume。

## 4. 系统 SVG 图

SVG 文件位于：

```text
docs/server-system-architecture.svg
```

图中表达了四层结构：

- 浏览器与 Nginx 网关入口。
- 六个主要业务微服务和 PostgreSQL。
- `analysis-service` 内部的 classic CV 与 semantic VLM 双管道。
- `agent-service` 内部的控制面、执行器、调度/邮件循环、工具调用和外部 LLM/邮箱集成。

## 5. 当前状态与注意事项

- 服务器当前运行主链路是 Compose 微服务栈，远端 `/opt/urban-insight` 不是 Git 工作树。
- 自建 `mail-server` 不再作为主链路依赖，外部 163 POP3/SMTP 是当前邮件闭环方案。
- 语义 VLM 工作流后端骨架已接入，但未下载和部署本地 Qwen 模型；未配置真实 VLM 服务时会 fallback。
- LLM 配置 API 由 `insight-service` 的 `/settings/llm` 提供，并要求 admin 会话；如果前端已登录但保存失败并显示未登录，应优先检查网关鉴权 Cookie 是否随 `/api/settings/llm` 请求发送，以及网关是否把该路径正确转发到 `insight-service`。
- Agent UI 的消息流若出现“假流式循环重放”，应优先检查前端消息渲染层是否对已完成的 assistant message 反复触发本地 typewriter 动画；后端当前的 Agent 控制面本质是 run/message API，而不是已确认的 SSE 真流式通道。
