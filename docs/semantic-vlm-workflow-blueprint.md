# 第二工作流蓝图：基于 Qwen3.5-0.8B 的语义研判链

## 1. 目标

当前项目已经具备一条成熟的结构化识别工作流：

1. 用户上传图片或视频。
2. `analysis-service` 创建 `AnalysisTask`。
3. 识别器运行 `YOLO + 属性模型 + 可选 ReID`。
4. 结果写入 `AnalysisRecord.results`。
5. `search-service`、洞察服务和 Agent 复用结构化结果。

这条链适合“找人、筛人、检索、统计”，但不擅长“解释片段、总结行为、理解场景、形成自然语言报告”。

第二条工作流的目标不是替代第一条，而是新增一条语义研判链：

1. 对视频做抽帧。
2. 使用 `Qwen3.5-0.8B` 对帧或关键窗口做自然语言描述。
3. 聚合出时间窗口级摘要。
4. 把窗口摘要送入更强的大模型，形成更高层的事件、风险和建议。
5. 让 Agent、洞察和前端直接消费这些语义结果。

## 2. 为什么选择这条链

`Qwen/Qwen3.5-0.8B` 是统一的视觉语言模型，支持图像和视频输入，也支持 OpenAI 兼容接口调用。它非常适合：

- 逐帧场景描述
- 行人或人群行为概括
- 环境和风险提示
- 为更强的大模型提供时间序列语义输入

它不适合单独承担：

- 稳定多人检测
- 跨帧跟踪
- 精确坐标级定位
- 高精度 ReID

因此最合理的定位是：

- 第一条工作流负责“结构化识别”
- 第二条工作流负责“语义理解与研判”

## 3. 新的双工作流模型

### 3.1 工作流 A：结构化识别链

用途：

- 属性识别
- 人员检索
- 结构化搜索
- 统计分析

主输出：

- `pedestrians`
- `bbox`
- `attributes`
- `person_id`
- `timestamp`

### 3.2 工作流 B：语义研判链

用途：

- 看懂场景
- 总结行为
- 判断异常
- 输出自然语言摘要
- 给 Agent 提供高质量上下文

主输出：

- `frame_descriptions`
- `window_summaries`
- `video_level_insights`
- `risk_narratives`
- `followup_suggestions`

### 3.3 工作流模式

建议支持三种模式：

- `classic_cv`
- `semantic_vlm`
- `dual`

推荐默认值：

- 图片：`classic_cv`
- 短视频：`dual`
- 长视频：`classic_cv` 或 `semantic_vlm-lite`

## 4. 第二工作流的分层设计

### 4.1 Frame Sampler

职责：

- 从视频中抽帧
- 根据时长、运动强度、巡检级别动态调整采样率

建议策略：

- 默认 `1 fps`
- 异常高风险片段 `2-4 fps`
- 超长视频优先使用窗口级关键帧抽样

输出：

- `frame_index`
- `timestamp`
- `frame_path` 或对象存储地址

### 4.2 Frame Narrator

职责：

- 调用 `Qwen3.5-0.8B`
- 对单帧生成严格结构化的自然语言描述

建议输出字段：

- `timestamp`
- `scene_summary`
- `people_count_estimate`
- `pedestrian_descriptions`
- `behaviors`
- `risk_signals`
- `environment_notes`
- `confidence_notes`

要求：

- 输出 JSON，不直接存自由文本
- 不允许猜测身份
- 不允许凭空补细节
- 风险字段必须给出视觉依据

### 4.3 Window Aggregator

职责：

- 将连续多帧的描述合并为时间窗口摘要

建议窗口：

- `10 秒`
- `30 秒`
- `60 秒`

建议输出：

- `window_summary`
- `crowd_change`
- `behavior_trends`
- `anomaly_candidates`
- `evidence_timestamps`

### 4.4 Deep Analyst

职责：

- 将窗口摘要交给更强的大模型
- 生成全视频级的深度结论

建议输出：

- `event_chain`
- `risk_level`
- `incident_summary`
- `operator_recommendations`
- `agent_followups`

### 4.5 Agent Integration

职责：

- 让 Agent 消费语义研判结果，而不是只消费结构化属性

主要用途：

- 巡检摘要
- 主动告警解释
- 长短期记忆沉淀
- proactive goals 的证据输入

## 5. 和当前代码的对接点

当前关键入口：

- [analysis.py](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/backend/routers/analysis.py)
- [real_recognition.py](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/backend/services/real_recognition.py)
- [search.py](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/backend/routers/search.py)
- [database.py](C:/Users/hsx/Desktop/Urban-Insight-A-Smart-PAR-Recognition-System/backend/database.py)

建议新增服务：

- `backend/services/frame_sampler.py`
- `backend/services/vlm_narrator.py`
- `backend/services/semantic_aggregator.py`
- `backend/services/video_analyst.py`
- `backend/services/semantic_normalizer.py`

建议新增或扩展字段：

### AnalysisTask

- `pipeline`
- `pipeline_config`
- `semantic_status`
- `semantic_progress`

### AnalysisRecord

- `pipeline`
- `result_schema_version`
- `semantic_results`
- `window_summaries`
- `video_insights`
- `pipeline_meta`

注意：

第二条工作流最好不要破坏现有 `results` 字段的搜索兼容性。建议把语义结果并排新增，而不是替换现有结构。

## 6. 存储设计建议

### 6.1 不建议只存大段文本

如果只存一段全文总结，会导致：

- 无法做时间轴呈现
- 无法做证据追溯
- 无法被 Agent 精确引用
- 难以做后续再分析

### 6.2 建议的三层结构

#### frame_descriptions

- 适合排查原始语义证据
- 可做时间轴展示

#### window_summaries

- 适合洞察和审阅
- 可直接成为高级模型输入

#### video_level_insights

- 适合报告、告警、Agent 和记忆

## 7. 推理与部署建议

### 7.1 建议的模型职责

不建议让 `Qwen3.5-0.8B` 直接替代整条 CV 链。

建议职责划分：

- `YOLO / Tracker / ReID`：几何与身份层
- `Qwen3.5-0.8B`：语义解释层
- 更强大模型 API：综合判断层

### 7.2 资源建议

对于第二条工作流：

- 开发测试：`8 GB VRAM`
- 单路视频低并发：`12 GB VRAM`
- 更稳妥生产：`16 GB VRAM`
- 多路视频或叠加更强本地模型：`24 GB+`

不建议 CPU-only 作为长期生产方案。

### 7.3 上下文与采样建议

不建议使用默认超长上下文去堆大量帧。

推荐：

- 帧级描述：短上下文
- 窗口级聚合：中上下文
- 视频级总结：用摘要喂更强模型

## 8. 面向客户的 UI 重塑方向

当前 UI 更像功能页集合。随着第二条工作流引入，交互应从“功能驱动”改为“任务和事件驱动”。

建议一级导航收敛为：

### 8.1 监控总览

看今天发生了什么：

- 风险摘要
- 任务状态
- 智能体状态
- 重点事件

### 8.2 任务中心

处理上传和分析：

- 上传媒体
- 选择工作流
- 查看进度
- 查看分析详情

### 8.3 事件与检索

统一入口：

- 结构化检索
- 自然语言检索
- 事件检索
- 片段复核

### 8.4 智能研判

围绕第二条工作流：

- 语义时间线
- 窗口摘要
- 风险研判
- 一键生成报告
- 交给 Agent 深挖

## 9. 核心页面重构建议

### 9.1 任务详情页

这是未来的核心页面，应取代零散结果入口。

页面分为三栏：

- 人员与属性
- 场景语义时间线
- AI 研判结论

### 9.2 语义时间线组件

展示：

- 关键帧缩略图
- 帧摘要
- 窗口总结
- 风险标签
- 证据时间点

### 9.3 事件卡片

每张卡是一个事件：

- 事件概括
- 风险等级
- 证据片段
- 结构化目标
- Agent 建议动作

### 9.4 对比视图

支持结构化结果和语义结果并排查看，让客户直观看懂两条工作流的价值区别。

## 10. Agent 需要同步变化

第二工作流落地后，Agent 不应继续只围绕结构化属性和系统运行态工作。

### 10.1 提示词变化

Agent 的系统上下文应显式加入一条规则：

- 当问题涉及场景、行为、异常解释、视频摘要、时间线判断时，优先读取语义分析结果，而不是只依赖结构化属性。

### 10.2 工具变化

至少新增两类工具：

- `analysis.get_record`
- `analysis.get_semantic_record`

用途：

- 读取单条分析记录的完整详情
- 读取逐帧语义描述、窗口摘要和视频级研判结果

### 10.3 行为变化

Agent 的推理策略应区分两类问题：

- `找人 / 筛人 / 属性过滤`
  - 优先结构化检索链
- `这个片段发生了什么 / 有什么异常 / 为什么判成风险`
  - 优先语义研判链

### 10.4 长短期记忆变化

Agent 记忆不应只写结构化巡检结果，还应写入：

- 窗口级异常摘要
- 视频级 incident summary
- 风险解释和后续建议

这样后续 proactive goal、策略蒸馏和巡检优先级才会真正受第二工作流影响。

## 11. 实施顺序

### Phase 1

- 新增 `pipeline` 概念
- 实现抽帧
- 接入 `Qwen3.5-0.8B` 单帧描述
- 落库 `frame_descriptions`

### Phase 2

- 增加窗口摘要
- 增加任务详情页
- 增加语义时间线

### Phase 3

- 接更强模型做视频级研判
- 接入 Agent 和记忆
- 接入告警和巡检闭环

## 12. 最终定位

这个项目后续不应只被定义为“行人属性检索系统”。

更准确的定位是：

`结构化安防识别 + 语义视频研判 + 常驻 Agent 巡查平台`

这也是第二条工作流的真正价值所在。
