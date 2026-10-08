# CreatorOS 快速创作链路

## 产品主线

CreatorOS 的默认操作只保留三步：

1. **看热点**：读取公开热榜，用户点击“从这里创作”后，热点标题、摘要和来源自动带入创作页。
2. **选平台和结果**：选择公众号、小红书或抖音，再选择“内容”“配图方案”或“内容 + 配图方案”。公众号和小红书可以一次带走正文与配图方案；平台选择决定输出的结构和语气。
3. **调用能力输出**：从当前内容类型可用的 Skill 中选择一个，进入 Easel 的六阶段内容工作流（发现与核验、选题与结构、主稿、平台适配、质量检查、归档交付），最后只把可编辑的适配稿和质量检查结果带回页面。生成结果可以保存到本机或下载 Markdown。

## 交互原则

- 首屏先展示热点和“自己输入主题”，不要求用户理解任务、简报、作业、连接器等内部模型。
- 一次只做一个决定：主题 → 平台 → 内容/配图组合 → Skill。
- 没有模型或媒体 API 时直接显示 `NOT CONFIGURED`/`BLOCKED`；配图组合当前交付可编辑的文字方案，不把图片提示词冒充已生成媒体。
- 内容库、发布、账号、画像和六阶段工作流保留为后台能力或后续入口，不阻塞快速创作。
- 三个平台仍然独立输出：公众号偏完整文章，小红书偏笔记与话题，抖音偏口播、分镜和字幕。

## 当前实现

- 页面：[HotspotsPage.tsx](../web/frontend/src/HotspotsPage.tsx)、[QuickCreatePage.tsx](../web/frontend/src/QuickCreatePage.tsx)。
- Skill 列表来自 `GET /api/skills`，快速创作通过 `POST /api/workflow/run`、`GET /api/workflow/{id}` 和 `/api/output/*` 读取六阶段产物；底层仍由迁入的 Easel/OpenClaw Agent 执行。
- 工作流保留参考项目的六阶段语义，并为每阶段写入可审计的 Skills：发现（`skill-trending-topics`、`skill-news-intelligence`）、选题（`skill-trend-rider`、`skill-topic-evaluator`、`skill-article-outline`）、平台主稿（`social-content` / `xhs-note-creator` / `video-script`）、质量（`skill-quality-gate`，有画像时加 `skill-persona-check`）和归档（`asset-manager`、`skill-publish-checklist`）。每个非归档阶段使用独立的 `workflow-<id>-<stage>-attempt-<n>` 会话，前序阶段只通过已落盘 artifact 传递；这样不会把所有阶段的 transcript 累积到同一上下文，重试也会获得新的阶段会话。平台适配阶段还必须为已选平台写入对应的非空终稿文件（公众号 `08-gzh-final.md`、小红书 `09-xhs-final.md`、抖音 `10-douyin-final.md`），归档前会核验这些文件。排版和润色只能作为明确的后处理能力。
- 画像开关只发送长度受控的平台风格、读者问题、结构偏好、禁用表达和已确认偏好，身份、经历和原始证据留在本机。
- 账号分析会把已有阅读、评论、收藏、转发、完读率等数据整理为本地“候选优化经验”；需要重复样本，明确标注相关性限制，不自动修改画像，也不自动把私有指标发送给模型。
- 选中的热点只写入本地浏览器状态，生成结果保存到本机草稿或下载文件，不会自动发布。
