# CreatorOS SaaS 可用性审计

审计日期：2026-10-02（Asia/Shanghai）  
审计范围：`CreatorOS/` 当前源码、路由、API、模型、运行时配置、前端生成/保存/反馈链，以及隔离临时数据目录中的可复现 API 探针。  
本文前半部分保留 2026-10-02 初始审计基线；后半部分记录同日完成的首批窄切片实现。未修改 `vendor/easel/` 或外部参考项目。

首批实施边界、跨层契约和验收步骤另见 [`docs/29-quick-create-persistence-plan-2026-10-02.md`](29-quick-create-persistence-plan-2026-10-02.md)。

## 一句话结论

CreatorOS 仍是“有可靠本地骨架的内容工作台原型”，但首批切片已把新保存的快速草稿接入 SQLite 内容任务并保留输入版本；完整的简报确认、三平台 Artifact、媒体产物、平台连接和发布链仍未闭合。

本次继续实现了两项窄改：工作流明确返回 `BLOCKED` 时不再伪装成完成；快速创作通过 `/api/v1/quick-drafts` 持久化为带画像版本的 `ContentTask` 输入，重复保存相同文本幂等，编辑后产生新的不可变输入版本。

## 项目结构速览

- `creatoros/api/`：FastAPI 应用、旧 `/api/v1` 业务路由和 Easel 兼容桥接。
- `creatoros/domain/`、`creatoros/db/`、`creatoros/services/`：画像、任务、简报、平台产物、记忆、热点、指标、连接器和公众号草稿的契约、SQLite 模型与业务服务。
- `web/frontend/src/`：React + TypeScript 页面；当前主入口由 `App.tsx` 挂载。
- `vendor/easel/`：迁移进来的运行时、Skill 目录、对话、模型设置和六阶段工作流；它不是本轮的外部参考项目，当前 CreatorOS 会加载其中的 Web 运行时。外部 ContentPilot 参考项目仍保持只读。
- `data/` 与 `runtime/`：本地 SQLite/资产和隔离的 OpenClaw 会话、作业、产物；真实凭据不应写入仓库。
- `tests/`、`docs/`：后端/前端验证与阶段交付、差异矩阵、验收证据。

## 证据边界与实测结果

### 代码与路由证据

- 主导航只有 `发现热点`、`拆解爆款`、`开始创作`、`我的内容`、`我的画像`、`模型设置`，见 [`web/frontend/src/App.tsx:12-68`](../web/frontend/src/App.tsx)。`PublishCenterPage`、`DraftCenterPage`、`ChatPage`、`OutputsPage` 文件存在，但没有被主导航渲染。
- 热点页调用 `GET /api/v1/trends`，把“写这个”的选题放进 `creatoros:selected-hotspot`，再跳到 `#/create`，见 [`web/frontend/src/HotspotsPage.tsx:24-44`](../web/frontend/src/HotspotsPage.tsx)。
- 快速创作调用 `POST /api/workflow/run`、轮询 `GET /api/workflow/{id}`，然后只读取 `adaptation` 和 `quality` 文件；保存时先保留浏览器恢复副本，再调用 `POST /api/v1/quick-drafts`，见 [`web/frontend/src/QuickCreatePage.tsx:42-73`](../web/frontend/src/QuickCreatePage.tsx)。
- “我的内容”优先读取 `GET /api/v1/quick-drafts`，并合并尚未同步的本机副本；服务端记录仍显示为可编辑草稿，未提交平台，见 [`web/frontend/src/StudioLibraryPage.tsx`](../web/frontend/src/StudioLibraryPage.tsx)。
- 后端确实有可追溯的 `profile → task → brief → artifact revision → memory → WeChat draft` API：`/api/v1/profile/*`、`/api/v1/tasks/*`、`/api/v1/artifacts/*`、`/api/v1/memories/*`、`/api/v1/drafts/*`，见 [`creatoros/api/app.py:223-665`](../creatoros/api/app.py)（路由区间以文件中的实际装饰器为准）。
- 六阶段工作流接口在迁移的 Easel runtime 中：`POST /api/workflow/run`、`GET /api/workflows`、`GET /api/workflow/{id}`、`POST /api/workflow/{id}/retry`，见 [`vendor/easel/web/app.py:4179-4200`](../vendor/easel/web/app.py)；服务在模型/研究网关不可用时把当前阶段置为 `blocked`，见 [`creatoros/services/workflow_service.py:185-201`](../creatoros/services/workflow_service.py)。
- 工作流归档固定写 `kind='article'`、`content_status='draft'`、`media_verified=false`，并把各阶段结果写成 `.md`，见 [`creatoros/services/workflow_service.py:202-239`](../creatoros/services/workflow_service.py)。因此“配图”目前没有可验证的媒体产物契约：它仍落成文章 Markdown，也没有结构化图片文件清单、尺寸或权利状态。
- 发布中心和公众号草稿中心本身具备本地能力，但未接主导航：[`web/frontend/src/PublishCenter.tsx:14-80`](../web/frontend/src/PublishCenter.tsx)、[`web/frontend/src/DraftCenter.tsx:17-97`](../web/frontend/src/DraftCenter.tsx)。

### 隔离临时目录 API 探针

使用 `CREATOROS_DATA_DIR=/tmp/creatoros-audit-data`、`CREATOROS_RUNTIME_ROOT=/tmp/creatoros-audit-runtime`，并以 `Origin: http://127.0.0.1:5173` 模拟本机工作台：

| 探针 | 结果 | 说明 |
|---|---|---|
| `GET /api/status` | `200`，`gateway=false` | Easel 迁移接口可读；**本次空隔离运行时**的模型网关离线 |
| `GET /api/v1/status` | `200`，`scope=local-first` | CreatorOS API 正常启动；迁移到 `0009_quick_draft_persistence` |
| `GET /api/accounts` | `200`，公众号/小红书/抖音均 `loggedIn=false` | **仅说明这次空的隔离运行时目录未登录**，不能推断用户当前账号状态 |
| `GET /api/settings/models/status` | `200`，`configured=false`、`gatewayOnline=false` | **仅说明这次空的隔离运行时目录没有模型配置**，不能推断用户当前工作区配置 |
| `GET /api/skills` | `200`，返回 `114` 个技能 | 技能目录可发现，但不等于已调用或生成成功 |
| `GET /api/v1/connectors` | `200`，三平台均 `adapter_kind=mock`、`state=not_configured` | 连接器是本地 Mock 状态机 |
| `GET /api/v1/overview` | `200`，空数据计数为 `0` | 总览快照可读，但不是主导航页面 |
| `GET /api/v1/trends?platforms=douyin&limit=3` | `200`，`status=unavailable`、0 条 | 当前网络/热榜源未返回数据，前端有不可用空态 |
| `POST /api/workflow/run` | `202` 后很快变为 `blocked` | 阶段 `discovery` 阻断，原因是模型/研究网关未配置或不可用；没有伪造内容 |

本地业务链也在隔离目录走通：

`POST /api/v1/profile/versions` → `POST /api/v1/tasks` → `POST /api/v1/tasks/{id}/briefs` → 确认简报 → `POST /api/v1/tasks/{id}/generate` 生成三份 `demo_deterministic` 平台模板 → `POST /api/v1/artifacts/{id}/revisions` 形成第 2 版 → `/api/v1/memories` 生成 `proposed` 记忆并可确认 → `POST /api/v1/artifacts/{id}/draft` 建立公众号本地草稿。无效封面会被拒绝；没有封面时提交接口返回 `404 draft_cover_missing`，这是语义问题，详见 P2。

### 验证命令

- 后端：在全新临时数据/运行时目录执行 `CreatorOS/.venv312/bin/python -m pytest -q` → **37 passed**（1 个 Starlette/httpx 弃用警告）。
- 前端：`npm test -- --run` → **3 files / 4 tests passed**；`npm run typecheck` 通过；`npm run build` 通过。
- 旧的 `.venv/bin/pytest` 使用 Python 3.9，会在迁移的 Easel `str | None` 类型注解处失败；项目 Makefile 已指定 `.venv312`，因此本审计以 3.12 结果为准。
- 本轮没有把历史截图当成新的视觉验收证据；没有执行真实模型、二维码/OAuth、媒体生成、平台草稿写入、发布或生产部署。

### 生成阻断状态探针

- 使用合成 runner（不调用网络、模型或平台）执行 [`docs/evidence/2026-10-02-audit-followup/workflow-blocked-probe.py`](evidence/2026-10-02-audit-followup/workflow-blocked-probe.py)。修复前回执 [`workflow-blocked-result-before-fix.json`](evidence/2026-10-02-audit-followup/workflow-blocked-result-before-fix.json) 显示网关在线夹具的五个阶段被错误标为 `completed`；当前回执 [`workflow-blocked-result.json`](evidence/2026-10-02-audit-followup/workflow-blocked-result.json) 显示同一夹具保持 `blocked`，`matches_expected=true`。
- 这是本地状态机修复的合成证据，不是任何真实模型可用性结论；真实模型、研究源和平台仍未调用。

## 普通用户真实主流程

### 当前能走通的主链

1. 打开 `/`，默认落到 `#/hotspots`。用户看到抖音、微博、知乎三类公开热榜；热榜读取失败时显示“暂不可用”。
2. 用户点“写这个”，选题标题、摘要和来源先写入浏览器 `localStorage`，跳到 `#/create`。这一步没有创建后端 `ContentTask`。
3. 用户在 `#/create` 选择平台（公众号/小红书/抖音）、结果（文章/配图）和 Skill，可选发送画像。点击生成后调用六阶段工作流；在本轮空隔离运行时中没有网关会在发现阶段阻断，真实工作区状态没有由本轮验证。
4. 如果网关和模型可用，前端读取适配和质量阶段的 Markdown，放进一个文本框。用户可以直接改文本。
5. 点击“保存到我的内容”后，先写本机恢复副本，再尝试写入 SQLite `ContentTask` 的 `generated_markdown` 输入；有已确认画像时，`#/library` 从服务端读回并保留输入版本，未配置画像或服务不可用时明确显示“仅保存在本机”。
6. 用户选择“像我/需要调整”时，反馈只写 `creatoros:learning-feedback`；下一次快速创作把最近几条反馈拼进 prompt 文本，但没有后端事件、来源、置信度或确认操作。
7. 当前主导航没有发布中心、账号页、草稿中心或产物树，因此快速草稿没有自然的下一步交付路径。

### 后端可走但普通用户看不到的链

`#/workspace/{task_id}` 和 `/api/v1/*` 可以走另一条更完整的本地链：画像版本 → 任务 → 简报草案 → 人工补来源/事实/读者问题 → 确认简报 → 三平台独立 `demo_deterministic` 产物 → 字段级修订/历史 → `proposed` 记忆 → 用户确认 → 公众号本地草稿 → 封面校验 → Mock 失败/重试。`PublishCenterPage` 能把公众号产物转换为本地草稿，但它没有被 `App.tsx` 的主导航接入。

### 当前没有完成的链

真实研究来源与逐条核验、真实 LLM 成稿、真实图片/视频产物、平台账号读取、真实草稿提交、正式发布、真实指标回读、可归因实验，以及通过真人表达门禁后的 `final` 状态均没有本轮证据。

## 100 分评分表

| 维度 | 权重 | 得分 | 依据 |
|---|---:|---:|---|
| 发现与选题 | 12 | 6 | 热点页、筛选、刷新和“写这个”存在；当前热榜可用性依赖外部源，缺 BetterOPC/官方证据队列，选题只进 localStorage。 |
| 首次上手与导航 | 10 | 5 | 首屏简单，平台选择清楚；关键的发布、账号、草稿、产物和对话页面未进主导航。 |
| 内容生成（文章/配图） | 15 | 5 | 文章工作流有状态和阻断；本轮空隔离运行时网关离线，且“配图”仍走 Markdown 文章归档，没有可验证的媒体产物契约。 |
| 平台差异化 | 10 | 5 | UI 有三平台和平台 Skill；真实平台输出质量、长度/媒体规则和独立发布动作未在主链闭合。 |
| 编辑、版本与撤销 | 10 | 7 | 后端 artifact revision、编辑事件和冲突保护较完整；快速创作文本编辑仍是无版本的 localStorage 覆盖。 |
| 保存、检索与内容库 | 12 | 6 | 新快速草稿已能写入 SQLite 并在内容库回读；尚未接入结构化平台产物、草稿中心和产物树。 |
| 反馈、画像与学习 | 10 | 4 | 画像版本和后端确认记忆存在；快速反馈没有进入同一记忆模型，也没有展示“哪条反馈改变了什么”。 |
| 发布与账号边界 | 8 | 3 | Mock/真实适配器边界有提示；主导航不可达，本轮空隔离运行时没有登录态，真实账号与发布未验证。 |
| 稳定性与恢复 | 8 | 6 | 六阶段作业可持久化、轮询、重试和重启标记；快速链依赖 localStorage，没有跨设备/跨浏览器恢复。 |
| 数据、证据与安全 | 5 | 4 | 后端保存来源/版本/记忆/草稿溯源，连接器不存凭据；快速链绕开这些字段，外部数据与质量证据仍缺。 |
| **合计** | **100** | **51** | **首批持久化切片完成后仍是本地原型，尚不足以按 SaaS 完整交付；分数是代码与隔离 API 证据的启发式判断，不是用户调研或行业基准。** |

## P0–P3 问题清单

### P0：必须先修

| 问题 | 影响 | 证据 | 建议 | 验收标准 |
|---|---|---|---|---|
| 快速创作的保存链与后端内容链分裂（首批已部分修复） | 原问题是“已保存”只存在浏览器；当前新保存已写入带画像版本的 `ContentTask` 输入，但还没有简报、平台产物版本或发布关联。 | 原证据为 `QuickCreatePage.tsx` 的 localStorage；当前新增 `POST/GET /api/v1/quick-drafts`、`ContentTask.quick_draft_id` 和 `TaskInput(input_type="generated_markdown")`。 | 下一步把服务端快速输入引导到工作台，由用户确认简报后再生成结构化平台 artifact；不要自动确认或把 Markdown 冒充平台产物。 | 新保存可在刷新/换标签后回读，同一 ID 重复保存幂等，编辑保存产生输入版本；进入完整工作台后保留 source/profile/brief/revision IDs。 |
| “配图”选项没有对应媒体产物 | 用户选择内容配图，却拿到文章 Markdown 或空结果，无法下载/预览可用图片，也无法进入平台媒体校验。 | `QuickCreatePage.tsx:20-23,49-67` 允许配图；`workflow_service.py:205-239` 固定 `kind='article'`、写 `.md`、`media_verified=false`，没有 image artifact 分支。 | 先建立 `media` 产物契约：真实 provider 未配置时在点击前明确 BLOCKED；配置后保存真实文件、mime、尺寸、sha256、来源和权利状态。 | “配图”只能出现三种可见结果：真实媒体并带文件信息、失败并可重试、未配置并明确阻断；绝不把文字 prompt 当成已生成图片。 |
| 生成后的交付入口不可达 | 主导航没有发布中心、草稿中心、账号连接器、产物树；普通用户无法把快速草稿交给下一步，也无法判断是否只是本地保存。 | `App.tsx:12-68` 只渲染六个页面；`PublishCenter.tsx:14-80`、`DraftCenter.tsx:17-97`、`OutputsPage.tsx:10-19` 虽存在但未挂路由。 | 将“我的内容/发布中心/账号与连接器/产物”接入同一 task 详情；区分本地草稿、Mock 回执、真实草稿回执和已发布。 | 新用户从“保存”可一键打开对应 task、平台预览和发布前检查；未登录时显示 BLOCKED/待人工操作，不出现“已发布”。 |
| 工作流把模型的 BLOCKED 文本当作完成（已修复） | 修复前研究或模型明确拒绝/缺证据时，用户仍会看到完成的草稿；当前已在 runner 边界阻断，不再写完成归档。 | 修复前回执 [`workflow-blocked-result-before-fix.json`](evidence/2026-10-02-audit-followup/workflow-blocked-result-before-fix.json)；当前实现 [`workflow_service.py`](../creatoros/services/workflow_service.py) 的 `_blocked_reason` 与回执 [`workflow-blocked-result.json`](evidence/2026-10-02-audit-followup/workflow-blocked-result.json)。 | 已完成保守识别 `BLOCKED`/`not_configured`/`unsupported`；后续补充结构化 runner 契约。 | 合成 runner 返回阻断时作业保持 `blocked`，阶段原因可见且可重试；正常非空内容才继续。 |

### P1：三天内修

| 问题 | 影响 | 证据 | 建议 | 验收标准 |
|---|---|---|---|---|
| 研究证据没有进入快速生成的可追溯账本 | 模型即使返回文字，用户也无法逐条回看来源、观察日期、事实状态和原创增量。 | `HotspotsPage.tsx:39-42` 只保存热点；`QuickCreatePage.tsx:49-68` 把摘要拼入 prompt；六阶段产物写文件而非来源实体。 | 生成前先建立 `ResearchLedger`/来源实体，绑定 task 和 claim；每个平台产物引用同一事实核但独立版本化。 | 每个事实主张可回到 URL、抓取/观察时间、核验状态；缺来源的内容不能显示“已核验”。 |
| 反馈没有进入可确认的长期学习模型 | “越用越强”目前只是同一浏览器里拼接最近反馈文本，不能审计、拒绝、撤销或解释对下一次生成的影响。 | `QuickCreatePage.tsx:32,47-48,71` 读写 `creatoros:learning-feedback`；后端 `Memory` 才有 `source_event_id/confidence/scope/confirmation_status`，见 `db/models.py:146-158`。 | 把“像我/需要调整/备注”写成 proposed memory 或 feedback event，展示来源和应用范围，用户确认后才检索。 | 用户能看到反馈 → 候选记忆 → 确认/拒绝/撤销 → 下一次生成引用的完整链；撤销不追改历史版本。 |
| 配图、公众号、小红书、抖音的校验未回到快速创作主链 | UI 让用户先选平台，但标题/正文长度、话题、图片/视频必需和发布状态在主链不阻断。 | `QuickCreatePage.tsx:10-23` 只有描述；平台规则虽在 `workflow_service.py:53-56` 提示给模型，主页面没有计数和媒体检查。 | 生成后为每个平台显示独立编辑器、字数/媒体检查、引用和发布前清单。 | 越界字段在保存/提交前明确阻断；三平台正文、标题、媒体和动作互不覆盖。 |
| 画像编辑页没有展示全部可用的平台画像和经历证据 | 后端模型支持 `audience`、`format_preferences`、`experiences`，前端只编辑定位/语气和少量通用字段，生成上下文不完整。 | `StudioProfilePage.tsx:62-70` 没有平台 audience/format_preferences 输入，也没有经历编辑；模型定义见 `domain/profile.py:46-79`。 | 补齐平台读者、格式偏好、经历/证据的编辑和确认状态；生成前显示将发送的最小字段。 | 每个平台至少能保存定位、读者、格式、语气；内容 revision 能指出使用了哪个画像版本。 |
| 模型配置完成后仍需要人工启动隔离网关，阻断文案不够可执行 | 普通用户填完模型仍会在工作流发现阶段收到 BLOCKED，不知道是 API Key、网关还是研究源问题。 | `ModelSettingsPage.tsx:89-108` 把保存、自测、启动 OpenClaw 分为多步；**空隔离探针**为 `configured=false/gatewayOnline=false`；`workflow_service.py:196-200` 只给统一阻断原因。 | 把“配置→自测→启动/检查→生成”做成可见状态机，错误区分 key、网络、网关、研究源和权限。 | 每个阻断状态都有下一步和重试入口；模型可连接但网关未启动时不显示为同一种错误。 |

### P2：一周内修

| 问题 | 影响 | 证据 | 建议 | 验收标准 |
|---|---|---|---|---|
| 草稿缺封面时返回 404 | 用户会把“缺少前置资料”误判成资源不存在，前端难以统一重试和引导。 | `DraftCoverMissing` 与 `DraftNotFound` 共用 404 handler，见 `creatoros/api/app.py:202-206`；本地探针无封面提交返回 `404 draft_cover_missing`。 | 缺封面改为 409/422，保留结构化 code；前端直接定位到上传封面。 | 同一草稿无封面、无效封面、超过 10MB 分别返回可行动的状态码和提示。 |
| 快速文本编辑没有版本历史、差异和并发保护 | 用户不能回到上一个版本，多个标签页可能互相覆盖。 | `QuickCreatePage.tsx:67-73` 直接修改 `output` 后整体写 localStorage；后端 revision 能力未复用。 | 快速链统一使用 artifact revision，保存原因、差异和 base revision；增加脏状态和冲突提示。 | 保存两次可看到 v1/v2 差异；旧版本只读；冲突不会静默覆盖。 |
| 热点源和官方线索不足 | 热点不可用时没有 BetterOPC/官方公告兜底，且没有人工输入/核验队列入口。 | `HotspotsPage.tsx:6-10` 只列抖音/微博/知乎；当前 `/api/v1/trends` 探针为 `unavailable`；`POST /api/v1/hotspots` 存在但无主导航表单。 | 增加手动链接/文本录入、BetterOPC 发现入口和官方来源核验队列；来源失效时保留旧数据并说明日期。 | 外部热榜失败时用户仍能录入线索；每条线索显示来源、抓取时间、热度状态和人工核验状态。 |
| 390/1024/1440 的当前主链没有本轮新鲜视觉回归 | 代码有响应式样式和旧截图，但不能把旧截图当作今天的完整体验证据。 | 当前验证只重新跑了后端/前端测试、类型检查、生产构建；没有新浏览器截图。 | 每次把关键路由接入主导航后，复跑三视口和键盘/焦点/空态/错误态。 | 热点→创作→保存→内容库→发布中心在 390、1024、1440 都可完成，焦点和错误提示可见。 |

### P3：体验收尾

| 问题 | 影响 | 证据 | 建议 | 验收标准 |
|---|---|---|---|---|
| “模型设置”承担了普通用户理解中的账号/发布设置，但账号页面没有对应入口 | 用户会把“模型已配置”误以为“平台可发布”，连接器状态又在未挂载的旧页面。 | `App.tsx:16-18` 只挂 `ModelSettingsPage`；账号连接器 UI 在旧 `Pages.tsx`，主导航不展示。 | 将“模型”“账号与连接器”“发布规则”拆成明确导航和状态卡。 | 用户能分别看到模型、平台登录、草稿提交、正式发布四种状态。 |
| 快速创作把 Skill 名称暴露给普通用户，但没有说明真实能力与证据级别 | 用户容易把 Skill 卡片当成已接入的能力或高质量结果保证。 | `QuickCreatePage.tsx:20-23,41` 展示并选择 Skill；`GET /api/skills` 返回 `needsApi/apiConfigured`，但结果区主要依赖统一文本提示。 | 显示“模板/需模型/已接入/外部阻断”标签和本次实际执行回执。 | 每次生成都能看到实际执行的 Skill、适配器、输入来源和状态，不用名称推断成功。 |

## 今天、3 天、1 周路线图

### 今天：先把一条真链接起来

1. 确定 SQLite task/artifact/draft 为唯一内容真源；快速创作先创建任务，浏览器只保存未提交输入。
2. 给 `#/library`、`#/publish`、`#/drafts`、`#/accounts` 增加明确路由；把当前隐藏的页面串起来。
3. 把“文章/配图”拆成不同产物类型；未接入媒体 provider 时在生成前阻断，不能落成文章 Markdown。
4. 增加一个端到端测试：热点/手动主题 → 任务 → 简报 → 生成 → 编辑 → 保存 → 刷新 → 发布前检查，断言 source/profile/revision ID 全部保留。
5. 修正缺封面提交的 HTTP 状态码和前端引导。

### 3 天：补证据和可解释学习

1. 建立研究来源/事实账本，支持 URL、原文摘要、观察时间、核验状态、claim 与产物引用。
2. 把快速反馈写入后端候选记忆，补确认、拒绝、编辑、撤销及“本次生成实际采用了哪些记忆”。
3. 补齐画像平台字段、经历、证据范围和确认前预览。
4. 三平台编辑器增加字数、媒体、话题、封面/视频和质量检查；失败平台独立重试。
5. 模型配置页提供 key 自测、网关在线、研究源可用三段状态和可执行下一步。

### 1 周：做真实小规模试用

1. 在用户自行完成授权的前提下，只接一个平台的真实读取/草稿回执；保留 Mock、真实草稿、正式发布三个独立状态。
2. 接入一类真实图片 provider 或明确保持 BLOCKED，完成文件尺寸、格式、权利来源和失败重试。
3. 做 CSV/JSON 指标导入后的候选洞察回写，要求样本量、观察窗口和不可归因说明。
4. 复跑 390/1024/1440、键盘导航、断线/刷新/重复提交、跨标签冲突和本地数据恢复。
5. 只在真实证据齐全后，给一小批用户做“从热点到可交付草稿”的试用；不把试用结果写成发布或增长成功。

## 普通用户导航建议

当前版本的安全顺序是：

1. **模型设置**：只有在确实要用真实生成时，填写模型地址/Key，做连接性自测，并按页面说明启动隔离网关。
2. **我的画像**：先填身份、领域、支柱、读者、语气、禁用表达和平台定位；保存后再生成。
3. **发现热点**：热榜只当线索；点击原始链接，自己核验事实和来源日期。热榜不可用时不要把空态当作没有热点。
4. **开始创作**：把主题、自己的素材、平台和内容类型说清楚；没有真实模型时接受 BLOCKED，不把模板当成成稿。
5. **我的内容**：当前只适合查看同一浏览器里的快速草稿；不要把这里的“已保存”理解成后端归档或平台草稿。
6. **真实交付**：当前应由人工完成事实复核、配图/视频制作、平台后台登录、草稿检查和正式发布。主导航接好之前，不建议普通用户依赖隐藏的 `#/workspace` 或未挂载的发布页面。

## 内容生成闭环与画像数据模型

### 当前实际闭环

`公开热榜/手动输入` → `localStorage:selected-hotspot` → `POST /api/workflow/run` → 六阶段文件（模型可用时）→ 文本框修改 → `localStorage:quick-drafts` → `localStorage:learning-feedback` → 下一次 prompt 拼接。

这条链的优点是不会伪造真实模型、发布或增长；缺点是选题、来源、画像版本、编辑版本、草稿、反馈和指标没有汇成一个可反查对象。

### 建议的闭环

`来源与读者信号` → `Topic/Hotspot` → `ContentTask` → `ResearchLedger/Brief` → `GenerationRun（画像版本 + 已确认记忆）` → `Artifact(platform, type)` → `ArtifactRevision + EditEvent` → `QualityGate/HumanReview` → `LocalDraft` → `ConnectorReceipt` → `MetricImport/Observation` → `CandidateMemory` → 用户确认后进入下一次生成。

现有数据库已经提供大部分基础字段：

- `CreatorProfile.current_version_id` 与 `CreatorProfileVersion.snapshot_json/parent_version_id/confirmation_status`：[`creatoros/db/models.py:16-43`](../creatoros/db/models.py)。
- `ContentTask.profile_version_id/status` 与 `TaskInput.metadata_json/parse_status`：[`creatoros/db/models.py:45-84`](../creatoros/db/models.py)。
- `Brief.payload_json/confirmation_status`、`PlatformArtifact.platform/current_revision_id`、`ArtifactRevision.profile_version_id/brief_id/source_ids_json/memory_ids_json/generation_kind`：[`creatoros/db/models.py:87-130`](../creatoros/db/models.py)。
- `EditEvent.path/before_json/after_json/reason` 与 `Memory.source_event_id/confidence/scope_json/confirmation_status/revoked_at`：[`creatoros/db/models.py:133-158`](../creatoros/db/models.py)。
- `Hotspot/HotspotEvidence` 保存来源、发布时间、抓取时间、事实状态、热度状态、核验状态：[`creatoros/db/models.py:161-192`](../creatoros/db/models.py)。
- `MetricImport/MetricObservation` 保存来源类型、观察时间、原始行和指标口径：[`creatoros/db/models.py:195-224`](../creatoros/db/models.py)。
- `ConnectorState` 明确不保存凭据或 Cookie；`Draft` 保存 `source_task_id/source_artifact_id/source_revision_id` 和提交回执：[`creatoros/db/models.py:227-292`](../creatoros/db/models.py)。

## 需要人工操作的步骤

- 配置文本模型的 Base URL、模型名和 API Key，并完成连接性自测；Key 不应粘贴进文章、日志或聊天。
- 启动/检查隔离的 CreatorOS OpenClaw 网关；网关在线不等于模型调用成功。
- 打开热点原文，核验事实、发布时间、政策/价格/版本和来源权利；当前热点源可能不可用。
- 提供真实作者经历、案例、数据和可公开引用范围；系统不能替用户补写经历。
- 对文章逐段编辑，对小红书卡片/话题和抖音脚本/镜头分别验收；不要把一个平台稿直接复制到另一个平台。
- 生成或准备真实图片/视频，检查格式、尺寸、大小、来源和使用权；当前配图模式本身尚未交付媒体文件。
- 完成人工质量审校、事实核验、成稿三问和真人表达门禁；工作流归档仍是 `draft`，不是 `final`。
- 用户自行登录平台、处理二维码/OAuth/验证码和权限；**本次空隔离探针**显示三平台 `loggedIn=false`，连接器为 Mock，不能代表用户当前登录态。
- 人工查看平台后台草稿和发布结果；CreatorOS 的本地保存或 Mock 回执不等于真实平台成功。
- 从平台后台导出 CSV/JSON 指标，导入账号分析，检查观察时间、缺失值、样本量和候选记忆，再决定是否确认。

## 未验证项

1. 当前模型/研究网关真实返回的文章质量、来源完整性、延迟、重试和费用。
2. 真实图片/视频/音频 provider 的可用性、文件质量、版权/授权链和失败恢复。
3. 公众号、小红书、抖音真实登录、账号读取、草稿提交、发布回执、验证码和风控行为。
4. 真实平台指标字段、T+1 延迟、CSV/JSON 导出格式变化与可归因实验。
5. BetterOPC 线索、政府/监管一手来源和当前热榜内容的实时核验。
6. 主链接入后的 390/1024/1440 视觉、键盘、屏幕阅读器、断线、刷新、跨标签并发和 localStorage 配额行为。
7. 多用户、多设备、云同步、权限隔离、备份恢复和生产部署性能；当前产品定义仍是单用户本地优先。
8. 真实真人表达检测和回执 SHA-256 门禁；本轮未调用朱雀，也没有把现有文本标记为 `final`。
