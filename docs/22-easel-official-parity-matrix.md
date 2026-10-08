# Easel 能力迁移差异矩阵

日期：2026-10-01（Asia/Shanghai）  
官方基线：`ZJU-REAL/Easel`，当前只读官方 checkout `4b9c03cf2129b6155595b66fc1e604546a3aa4ad`。旧审计使用 `3fe2d99`，本轮以当前 checkout 校正。   
待验收实现：`/Users/fc/Desktop/随波逐流/CreatorOS`（默认页面为 CreatorOS 自有 UI，官方项目只读）  
只读依据：`/private/tmp/easel-official-audit-20261001/inventory.md`、`/private/tmp/easel-browser-acceptance-20261001.md`

状态含义：`CONFIRMED` 表示当前行为与官方目标一致；`PARTIAL` 表示有数据或页面基础但行为不等价；`BLOCKED` 表示接口/页面有入口但需要未接入的外部能力；`NOT_IMPLEMENTED` 表示当前没有可执行实现。

## 1. 官方功能 → 当前实现 → 证据 → 差异

| 功能 | 官方路径与行为 | CreatorOS 当前路径/接口 | 当前证据与状态 | 优先级与修复范围 |
|---|---|---|---|---|
| 工作台 | `DashboardPage` 并行读取热点、选题、日历、产物、账号和分析，快捷动作可带入创作 | `App.tsx` → `OverviewPage`；`GET /api/v1/overview` 只有计数 | 浏览器工作台只有计数、任务和流程卡；无热点/选题/产物卡，`PARTIAL` | P1；补卡片数据和入口，不改变已有任务数据 |
| 一键工作流 | 用户追加要求（官方基础版无 `WorkflowPage`）：一次启动六阶段并轮询状态；本地 `.easel` 扩展仅作行为说明 | `Workspace.tsx` 串行 `POST /tasks`、`/briefs`、`/confirm`、`/generate` | 浏览器必须手动点保存→简报→确认→模板，`NOT_IMPLEMENTED` | P0；增加 job 状态、六阶段、轮询、重试/恢复和单次启动 |
| 对话与会话 | `ChatPage`/`App.tsx` 支持多会话、SSE token/thinking/activity/heartbeat/question/done、停止、重试、追问、附件、断线恢复 | `ChatPage.tsx` 只有未配置说明；后端无 `/api/chat/*` | 浏览器无输入框、无会话列表；真实 LLM 未接入，`NOT_IMPLEMENTED` + 外部 `BLOCKED` | P0；先补可操作阻断、会话状态和 SSE 契约，真实模型保持 BLOCKED |
| 技能库 | `SkillPage`、`SkillDrawer`、`GET /api/skills`、`GET /api/skill/{name}`、`POST /api/skill` | CreatorOS `SkillsPage.tsx` → `GET /api/skills` | 自有技能卡片、搜索和配置状态可见；未配置模型显示 BLOCKED，`CONFIRMED` for migrated read path | P1；后续补详情/运行状态 |
| 内容库/产物 | `OutputsPage` 递归读取 `outputs/`，支持文本、Markdown、图片、视频、音频、HTML、PDF 预览、下载、删除 | CreatorOS `LibraryPage` 保留任务视图，`OutputsPage` → `GET /api/outputs` 展示迁移后的产物树 | 任务与产物树分成自有页面；空态和文件打开入口可见，`PARTIAL` | P1；补媒体预览/删除 |
| 账号 | `AccountsPage` 三平台登录、whoami、二维码/短信、退出、公众号凭证 | CreatorOS `SettingsPage` 同时读取 `/api/accounts` 与 `/api/v1/connectors` | 三平台白名单、登录态和本地连接器状态均可见；真实登录保持 `BLOCKED` | P0/P1；继续补用户触发的登录回执 |
| 画像 | `ProfilePage`/`OnboardingWizard` 多画像、六文件、平台链接分析、切换/删除、异步构建 | `ProfilePage` 单一数据库画像版本、差异和恢复 | 画像版本可保存，但无向导、多画像和文件 API，`PARTIAL` | P1；补多画像/六维文件映射，模型分析保持 BLOCKED |
| 热点雷达 | `TrendsPage` 自动拉取、更新时间、平台筛选、缓存/备用源/空态/重试；收藏进 ideas，做内容进 Agent | `HotspotsPage` + `GET /api/v1/trends`；收藏进 `hotspots`，做内容建 task | 抖音榜单可取且有缓存/备用源；收藏没有独立选题库，默认暴露发现源，`PARTIAL` | P1；保留发现源，增加 ideas 投影和上下文带入 |
| 选题库 | `IdeasPage` Kanban pending/doing/done，新建/编辑/删除/推进/做内容/加入日历 | 无独立页；热点收藏列表代替 | `#/ideas` 回退工作台，`NOT_IMPLEMENTED` | P0；增加 ideas 数据模型/API/看板和任务、日历入口 |
| 内容日历 | `CalendarPage` 月历、content/event 两类、状态、平台、日期详情、增删改、context | 无路由、无 `/api/v1/schedule` | `#/calendar` 不存在，`NOT_IMPLEMENTED` | P0；增加 schedule API/页面，平台仅三目标平台 |
| 发布中心 | `PublishPage` 母稿→平台改编、字数/媒体规则、预览、检查、发布、异步状态和短信墙 | `PublishCenter.tsx` 读取本地 artifact；公众号转草稿，其余仅检查条件 | 浏览器三平台是通用字段，无字数/媒体校验；`PARTIAL` + 外部 `BLOCKED` | P0；补独立平台编辑、规则阻断和状态轮询 |
| 公众号限制 | 标题≤64、正文≤20000、封面、草稿箱/真实回执 | Draft 模型/页面已有标题 64、封面、Mock/Browser adapter | 本地草稿和封面失败/重试已验收，真实微信未调用，`PARTIAL` | P1；接入发布中心预检，真实回执保持 BLOCKED |
| 小红书限制 | 标题≤20、正文≤1000、图片或视频、话题 | 模板字段无限制和媒体字段 | 当前页面没有计数、媒体选择或话题校验，`NOT_IMPLEMENTED` | P0；前后端共同校验，未连接账号保持 BLOCKED |
| 抖音限制 | 文案≤55、必须视频、异步发布、短信验证码 | 模板字段无限制；无发布状态/SMS | 当前页面只有“检查发布条件”，`NOT_IMPLEMENTED` | P0；增加视频必选、55 字校验、异步/SMS 契约，真实发布 BLOCKED |
| 账号分析/归因 | `analytics` 读取三平台真实账号数据、观察窗口、已发内容，拆解结果可写回画像记忆 | `AnalyticsPage` 仅 CSV/JSON 导入和公众号读取；无可见入口 | 代码有 `/api/v1/metrics/*`，无三平台页面和归因闭环，`PARTIAL` | P1；补导航和空态/限制；真实数据保持 BLOCKED |
| 爆款拆解 | `BreakdownPage` 提交内容/链接，运行拆解并把可验证经验写入画像 | `BreakdownPage` + `#/breakdown`；按公众号/小红书/抖音选择平台，调用 `skill-competitor-analysis`，结果支持复制/下载 | 已实现入口和平台提示；模型网关未配置时 BLOCKED，参考来源和真实数据仍需人工核验 | 后续补来源资产、拆解结果到选题库的持久化，以及小红书专用数据 Skill 的可用性检查 |
| 设置/环境/模型 | `SettingsPanel` 六通道模型、密钥脱敏、自测、环境工具安装和轮询 | `SettingsPage` 只有连接器和本地状态文案 | 缺少 `/api/settings/models`、`/api/env/*` 的后端/页面，`NOT_IMPLEMENTED` | P1；补状态页面和配置契约，不回显密钥 |
| 首次引导/恢复 | `OnboardingWizard` 无画像启动；任务/会话刷新恢复、失败重试、跨标签占用 | 无首次引导；任务/草稿可刷新恢复 | 浏览器未发现引导/会话恢复，`PARTIAL` | P1；补本地引导标记和任务 job 恢复 |
| 附件 | 聊天多文件上传，超限转 `/api/upload/local`，关联会话 | 任务文件上传 25MB；聊天无附件 | `POST /api/v1/tasks/{id}/inputs/file` 可用，`NOT_IMPLEMENTED` for chat | P1；补会话附件和超限/类型回执 |
| 失败/权限/可访问性 | 官方各页有 loading/empty/error/retry、ARIA、无水平溢出 | 主要页面有部分 loading/error；缺少官方状态页面 | 390/1024/1440 已有截图，但缺失页面无法验收，`PARTIAL` | P2；新增页面沿用状态组件并复跑四视口 |

## 2. 三平台接口、登录、发布与媒体限制

| 平台 | 目标平台标识 | 编辑规则 | 登录/发布接口契约 | 当前状态 |
|---|---|---|---|---|
| 公众号 | `wechat-oa` / UI `wechat` | 标题 64、正文 20000、必须封面；只到草稿箱或真实回执 | `/api/accounts/wechat-oa/credentials`、`/mp-login`、`/whoami`、`/publish/wechat-oa` | 本地 Draft/Mock 已有；真实凭证、扫码、上传和回执 `BLOCKED` |
| 小红书 | `xiaohongshu` | 标题 20、正文 1000、图片或视频、话题标签 | `/api/login/xiaohongshu`、`/whoami`、`/publish/xiaohongshu` | 无等价接口/媒体检查，`NOT_IMPLEMENTED`；真实账号 `BLOCKED` |
| 抖音 | `douyin` | 文案 55、必须视频；异步发布；短信验证码 | `/api/login/douyin`、`/login/douyin/sms`、`/publish/douyin/status`、`/publish/douyin/sms` | 无等价接口/状态轮询，`NOT_IMPLEMENTED`；真实账号 `BLOCKED` |

微博、知乎、百度、头条、B 站只能出现在热点发现源，不得出现在发布目标、账号卡、日历平台选择或三平台编辑器。

## 3. 关键流程验收结果

| 流程 | 浏览器/API 结果 | 状态 |
|---|---|---|
| 打开工作台 | `/api/v1/status` 200；工作台可访问，但缺少热点/选题/产物/归因卡 | PARTIAL |
| 自动热点 | `/api/v1/trends?platforms=douyin` 返回 12 条 fresh 热榜，含来源/热度/原链；收藏落 hotspots | CONFIRMED for fetch，PARTIAL for ideas |
| 热点→内容 | “用此选题”生成 task；未进入独立 ideas 或官方对话 | PARTIAL |
| 主题→三平台 | 可完成任务、简报、确认、三份本地模板；需多次手动操作 | PARTIAL |
| 一键六阶段 | 无 `/api/workflow/run` 或 job 状态，无法一次启动 | NOT_IMPLEMENTED |
| 对话 | 页面只有未配置说明，无输入框/会话/SSE | BLOCKED + NOT_IMPLEMENTED |
| 公众号草稿 | 本地保存、封面类型阻断、Mock 失败/重试回执可复现 | PARTIAL; real publish BLOCKED |
| 小红书/抖音发布 | 只能检查连接器，无平台独立预览/媒体/状态/SMS | NOT_IMPLEMENTED |
| 画像 | 单画像版本保存/差异/恢复可复现；无多画像向导 | PARTIAL |
| 分析导入 | CSV/JSON 结构性导入和限制说明可复现；无三平台真实读取/归因 | PARTIAL; real data BLOCKED |
| 四视口 | 390、1024、1440 已有截图；缺失页和官方主流程未完成 | PARTIAL |

## 4. P0/P1/P2 修复清单与修改白名单

### P0

1. 增加六阶段 workflow job API、轮询、失败重试/恢复和工作台一次启动按钮。
2. 增加独立 ideas、schedule API 与页面，打通热点收藏→选题→日历→创作。
3. 补齐发布中心三平台字段、字数计数、媒体选择和发布前阻断；真实账号/模型未接入时保持 BLOCKED。
4. 将对话页改为可操作的会话/消息/附件入口；无真实 LLM 时返回明确 BLOCKED SSE 事件，不生成伪造文本。

### P1

1. 工作台补热点、选题、最近产物、账号状态和分析入口。
2. 增加 outputs 产物树、多媒体预览/下载/删除。
3. 增加技能库、爆款拆解、账号分析页面和路由。
4. 增加多画像/六维文件映射、首次引导和设置/环境/模型状态面板。
5. 统一三平台白名单和发现源语义，保留来源、热度、获取时间与人工核验状态。

### P2

1. 补齐 loading/empty/error/retry/ARIA 与 390/1024/1280/1440 视口回归。
2. 补断线恢复、跨标签会话占用、超大附件转本地复制通道。
3. 补真实能力接入后的质量门禁、媒体渲染和回执持久化；未接入前维持 BLOCKED。

本矩阵在代码修改前完成，后续修改和验收必须回填对应状态、文件、接口和截图证据。

## 5. 统一实施白名单

- `vendor/easel/**`：固定官方源码、脚本、技能、许可和指纹；不包含官方用户数据或凭据。
- `creatoros/api/app.py`、`creatoros/api/easel_bridge.py`、`creatoros/services/workflow_service.py`：保留 `/api/v1`，挂载官方兼容 API、隔离存储和六阶段作业。
- `vendor/easel/web/frontend/src/**`：官方前端只读参考；`web/frontend/src/**`：CreatorOS 自有页面与迁移后的能力入口。
- `pyproject.toml`、`tests/test_easel_parity.py`、相关文档和验收证据。
- 不修改 `data/**`、原始数据库、`.easel` 或官方参考 checkout。

## 6. 实施后状态回填（2026-10-01）

前述“修改范围”表是修改前快照；统一修复后以 [`docs/23-easel-parity-validation.md`](23-easel-parity-validation.md) 的证据为准：

| 条目 | 回填状态 | 证据 |
|---|---|---|
| CreatorOS 自有工作台/对话/技能/产物/账号/画像界面 | `CONFIRMED`（自有界面与路由可打开） | 浏览器本地验收；`GET /api/status`、`/api/accounts`、`/api/outputs` |
| 旧 CreatorOS API 与数据 | `CONFIRMED` | `/api/v1/status`、`/api/v1/connectors` 均 200；原测试全通过 |
| 一键六阶段工作流 | `CONFIRMED`（编排、轮询、持久化、重试、阻断） | `tests/test_easel_parity.py`；浏览器一次启动后 discovery 显示 `BLOCKED` |
| 三平台限制与发布前校验 | `CONFIRMED` | 账号/发布/日历/画像只显示三平台；标题、正文、媒体校验测试通过 |
| 真实 LLM/研究/媒体/登录/发布 | `BLOCKED` | 当前环境无网关、无账号；API/UI 明确返回 `NOT CONFIGURED`/`BLOCKED`，未调用外部发布 |
| 质量检测与公开发布 | `BLOCKED` | 工作流产物固定为 `draft`，需真人审校和真实平台回执 |

## 7. 目标修正

本矩阵最初按“官方界面一比一还原”记录，随后按产品目标修正为“参考官方项目并迁移能力”。因此，官方 `SkillPage`、`OutputsPage`、账号状态、SSE 对话和六阶段工作流的行为契约被保留在后端/接口层，但默认入口由 CreatorOS 的 `Workspace.tsx`、`ChatPage.tsx`、`SkillsPage.tsx`、`OutputsPage.tsx` 和 `SettingsPage` 自行呈现。不存在把官方前端当作产品默认入口的要求。
