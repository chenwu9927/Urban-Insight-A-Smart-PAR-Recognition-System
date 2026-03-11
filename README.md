# Urban Insight - 智能行人属性识别系统

## 项目简介

Urban Insight是一个智能行人属性识别系统，旨在通过AI技术识别监控视频中的行人属性，为安防监控和商业分析提供支持。

## 项目结构

```
Urban-Insight-A-Smart-PAR-Recognition-System/
├── frontend/                 # 前端应用
│   ├── public/              # 静态资源
│   ├── src/
│   │   ├── components/      # React组件
│   │   │   ├── common/      # 通用组件
│   │   │   ├── upload/      # 文件上传组件
│   │   │   ├── visualization/ # 可视化组件
│   │   │   ├── auth/        # 认证相关组件
│   │   │   ├── filter/      # 筛选条件组件
│   │   │   └── video-player/ # 视频播放器组件
│   │   ├── pages/           # 页面组件
│   │   │   ├── login/       # 登录页面
│   │   │   ├── dashboard/   # 仪表板
│   │   │   ├── search/      # 搜索页面
│   │   │   ├── history/     # 历史记录页面
│   │   │   └── statistics/  # 统计分析页面
│   │   ├── services/        # API服务
│   │   ├── utils/           # 工具函数
│   │   ├── hooks/           # 自定义React Hooks
│   │   └── assets/          # 资源文件
│   │       ├── images/      # 图片资源
│   │       └── styles/      # 样式文件
│   └── tests/               # 前端测试
├── backend/                  # 后端API
│   ├── src/
│   │   ├── controllers/     # 控制器
│   │   │   ├── auth/        # 认证控制器
│   │   │   ├── upload/      # 文件上传控制器
│   │   │   ├── analysis/    # 分析控制器
│   │   │   ├── search/      # 搜索控制器
│   │   │   ├── statistics/  # 统计控制器
│   │   │   └── user/        # 用户管理控制器
│   │   ├── models/          # 数据模型
│   │   │   ├── user/        # 用户模型
│   │   │   ├── media/       # 媒体文件模型
│   │   │   ├── task/        # 任务模型
│   │   │   ├── result/      # 结果模型
│   │   │   └── log/         # 日志模型
│   │   ├── services/        # 业务服务
│   │   │   ├── auth/        # 认证服务
│   │   │   ├── upload/      # 文件上传服务
│   │   │   ├── preprocessing/ # 预处理服务
│   │   │   ├── detection/   # 检测服务
│   │   │   ├── retrieval/   # 检索服务
│   │   │   └── statistics/  # 统计服务
│   │   ├── routes/          # 路由定义
│   │   ├── middleware/      # 中间件
│   │   ├── utils/           # 工具函数
│   │   └── config/          # 配置文件
│   ├── tests/               # 后端测试
│   └── logs/                # 日志文件
├── ai-models/               # AI模型
│   ├── src/
│   │   ├── detection/       # 行人检测模块
│   │   ├── recognition/     # 属性识别模块
│   │   ├── preprocessing/   # 预处理模块
│   │   └── utils/           # 工具函数
│   ├── models/              # 训练好的模型
│   │   ├── yolov5/          # YOLOv5行人检测模型
│   │   └── resnet50/        # ResNet-50属性识别模型
│   ├── data/                # 数据集
│   │   ├── raw/             # 原始数据
│   │   ├── processed/       # 处理后数据
│   │   └── annotations/     # 标注数据
│   ├── notebooks/           # Jupyter笔记本
│   │   ├── experiments/     # 实验记录
│   │   └── visualization/   # 可视化分析
│   └── tests/               # 模型测试
├── database/                # 数据库相关
│   ├── migrations/          # 数据库迁移
│   ├── seeds/               # 种子数据
│   └── schemas/             # 数据库模式
├── config/                  # 配置文件
│   ├── development/         # 开发环境配置
│   ├── production/          # 生产环境配置
│   └── testing/             # 测试环境配置
├── docs/                    # 文档
│   ├── api/                 # API文档
│   ├── user-guide/          # 用户指南
│   └── development/         # 开发文档
├── tests/                   # 集成测试
│   ├── integration/         # 集成测试
│   ├── e2e/                 # 端到端测试
│   └── performance/         # 性能测试
├── deployment/              # 部署相关
│   ├── docker/              # Docker配置
│   ├── kubernetes/          # Kubernetes配置
│   └── scripts/             # 部署脚本
├── scripts/                 # 项目脚本
│   ├── setup/               # 初始化脚本
│   ├── deployment/          # 部署脚本
│   └── maintenance/         # 维护脚本
└── document.md              # 项目需求文档
```

## 技术栈

- **前端**: React, Vite, Axios
- **后端**: Python, FastAPI, SQLAlchemy, Pydantic
- **AI模型**: PyTorch, Ultralytics YOLO, timm, TorchReID(可选)
- **数据库**: SQLite（当前落地）
- **部署**: 本地单机部署（可扩展到 Docker）

## 主要功能

1. **用户认证与管理**: 支持用户注册、登录和基于角色的权限控制
2. **文件上传**: 支持图片和视频文件的批量上传
3. **行人检测与属性识别**: 使用AI模型识别行人及其属性
4. **属性检索**: 根据属性组合快速筛选目标行人
5. **数据可视化**: 提供直观的图表展示分析结果
6. **历史记录**: 保存和查看历史分析记录
7. **智能洞察（LLM 可选）**: 后端汇总统计数据并可选调用 LLM 生成文字洞察与建议，前端在“智能洞察”页面展示

## 近期后端改造（2026-03）

### 1) 异步分析任务 + 进度/ETA
- `POST /analyze/{file_id}` 改为提交分析任务，不阻塞请求线程。
- 新增 `GET /analyze/tasks/{task_id}`，返回：
  - `status`: `queued/running/completed/failed`
  - `progress_percent`
  - `processed_units` / `total_units`
  - `eta_seconds`
  - `result_record_id` / `error_message`
- 前端文件库页面已接入轮询，展示百分比和预计剩余时间。

### 2) 管道与过滤器（Pipeline & Filters）视频分析流水线
- `backend/services/real_recognition.py` 的视频分析采用分阶段流水线：
  - Reader（读帧采样） -> Detector（行人检测） -> Analyzer（属性/ReID） -> ThumbnailWriter（缩略图写盘）
- 通过队列解耦阶段，避免单线程串行导致的吞吐瓶颈。
- 支持进度回调，上报到任务状态接口。

可调环境变量：
- `VIDEO_SAMPLE_SECONDS`：采样间隔秒数（默认 `1`）
- `ATTR_REFRESH_SECONDS`：同一轨迹属性刷新间隔（默认 `3`）
- `PIPELINE_QUEUE_SIZE`：流水线队列大小（默认 `8`）
- `SAVE_THUMBNAILS`：是否保存缩略图（默认开启）
- `THUMBNAIL_HEIGHT`：缩略图高度（默认 `150`）
- `THUMBNAIL_JPEG_QUALITY`：缩略图JPEG质量（默认 `85`）
- `THUMBNAIL_QUEUE_SIZE`：缩略图写入队列大小（默认 `2 * PIPELINE_QUEUE_SIZE`）

### 3) 一致性修复：删除文件级联清理
- `DELETE /files/{file_id}` 现在会同时清理：
  - 物理视频/图片文件（`uploads/`）
  - 关联分析记录、分析任务、分析报告
  - 关联缩略图（`thumbnails/`）
  - 关联缓存（scope 内包含该 `file_id`）
- 若文件仍在分析中，返回 `409` 防止脏状态。

### 4) 检索性能与结果去重
- 结构化检索和自然语言检索支持：
  - `dedup_person`（默认开启）
  - `max_results`（默认 `300`，后端上限 `1000`）
- 前端结果页同一 `person_id` 仅展示一次，并限制渲染数量，减少页面卡顿。

### 5) 以图搜人（Image Search）
- 新增接口：`POST /search/by-image`（`multipart/form-data`）
  - 入参：`image`、可选 `file_id`、`top_k`、`min_score`
  - 出参：`query_attributes`、`results`
- 当前实现采用“查询图像属性 vs 视频行人属性”相似度匹配，并按得分排序。
- 默认阈值已下调到 `0.20`，提高召回率。

## 智能洞察（LLM 可选）

- API：`GET /insights?date=YYYY-MM-DD` 或 `GET /insights?file_id=123`
- 问答：`POST /insights/ask`（传入 `question` + 可选 `date/file_id`）
- 默认未配置 Key 时自动使用规则化洞察，不影响系统使用
- 配置环境变量后将启用 LLM：
  - `LLM_API_KEY`（或 `OPENAI_API_KEY`）
  - `LLM_BASE_URL`（默认 `https://api.openai.com/v1`）
  - `LLM_MODEL`（默认 `gpt-4o-mini`）
- 缓存（可选）：`LLM_CACHE_TTL_SECONDS`（默认 3600，设置为 0 关闭缓存）

## 行人身份追踪（ReID）

- 视频分析结果会包含 `person_id`（跨帧稳定身份）与 `event_id`（单次检测事件）。
- 默认使用属性模型骨干作为外观特征；如需更稳的 ReID，可配置独立模型：
  - `REID_MODEL_PATH`：TorchScript/torch 模型路径
  - `REID_MODEL_NAME`：timm 模型名（可选）
  - `REID_BACKEND=torchreid`：若已安装 torchreid，可用其模型
  - `REID_INPUT_SIZE`：输入尺寸（默认 `256x128`）
- 统计接口支持去重：`/stats?dedup=1`（默认开启）。

## 批量重跑历史视频（生成 person_id）

运行脚本重新分析历史视频并更新最新记录：

```
python3 scripts/reprocess_person_id.py --all
```

## 快速开始

详细的安装和使用说明请参考 [docs/user-guide](docs/user-guide) 目录下的文档。

## 许可证

本项目采用 [LICENSE](LICENSE) 许可证。
