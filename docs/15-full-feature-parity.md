# 对照实现 → CreatorOS 与 Skills 全功能差异矩阵（第一阶段）

审计日期：2026-10-01（Asia/Shanghai）
参考 HEAD：`对照实现@0e9e9dd`（`feat: expose cover and migration status`）。
目标：`CreatorOS` 当前工作树（该目录没有独立 Git 元数据，因此不虚构目标 commit）。
范围：先做源码、API、模型、测试和 Skill 映射审计；随后记录第一条总览/工作台 UX 垂直切片的回填。本文不表示真实平台已连接或文章已发布。

## 1. 对照实现 → CreatorOS

| 对照实现 能力/契约 | 参考证据 | CreatorOS 对应页面/API/模型/测试 | 状态 | 迁移判断 |
| --- | --- | --- | --- | --- |
| 工作台 | `web/frontend/src/App.tsx`：单一公众号编辑台、进度、下一步、最近草稿 | `App.tsx` 总壳；`Pages.tsx` 总览；`Workspace.tsx` 内容工作台；`GET /api/v1/overview`；`tests/test_api.py::test_overview_snapshot_exposes_recovery_counts` | 部分实现 | CreatorOS 已扩展为多阶段、多平台；总览已有计数快照，还需把恢复、研究、来源和待确认事项集中到工作台 |
| 本地文章草稿 | `domain/models.py:Draft`；`storage/repository.py` JSON 文件；`GET/POST /api/v1/drafts` | `DraftCenter.tsx`；`wechat_drafts`/`wechat_draft_events`；`GET/POST/PATCH /api/v1/drafts`；`tests/test_drafts.py` | 已实现（本地） | 保留本地草稿，增加来源 revision 三元组和不可覆盖的已提交保护 |
| 公众号状态/登录 | `GET /api/v1/account`、`POST /api/v1/account/login`、`GET /api/v1/account/login/status`；Playwright 持久会话和二维码状态文件 | `SettingsPage` 的 `wechat-oa` Mock；`GET /api/v1/connectors` 与 configure/connect/read；`connector_states`/`connector_events`；`tests/test_connectors.py` | 只有 Mock；外部阻塞 | 不复制 对照实现 浏览器登录实现；真实登录须单独适配器、凭据/扫码授权和回读证据 |
| 草稿字段 | `title` ≤64、`digest` ≤120、`author` ≤32、`content_html`、`cover_path`、状态 | `Draft`/`DraftCreate` 同等字段；`DraftCenter.tsx` 可编辑标题、作者、摘要、HTML；`tests/test_drafts.py` | 已实现（本地） | 后续补 HTML 清洗、正文内嵌图片和平台字段验证 |
| 封面路径/预览 | 对照实现 只保存 `cover_path` 文本；真实适配器上传图片 | `POST /drafts/{id}/cover`；PNG/JPEG/WebP 头部、尺寸和 10MB 校验；`GET .../cover`；隔离预览；`tests/test_drafts.py` | 已实现（本地）；真实上传外部阻塞 | 本地文件资产和微信后台上传必须保持两种状态，不能合并为“已上传” |
| 明确提交 | `POST /drafts/{id}/publish` 调 `WeChatAdapter.publish_draft`，文档声明不群发 | `POST /drafts/{id}/submit` 只调 Mock Connector，页面需要用户点击 | 只有 Mock | 保留显式动作；真实草稿接口另做适配器，默认不提供群发路由 |
| 提交失败/重试 | `WeChatError` 写 `failed`/`publish_error`；但只有简单状态覆盖 | `wechat_draft_events` 记录每次 submit；失败保存错误并可重试；已提交不可编辑，可 copy；`tests/test_drafts.py` | 已实现（Mock） | 真实平台需错误码映射、回执回读、超时与幂等证据 |
| 账号读取 | `fetch_stats()` 解析发表记录、趋势和文章列表；`GET /api/v1/analytics` | `POST /connectors/{key}/read` 只推进 Mock 状态；CSV/JSON 指标走 `/metrics/imports`；`metric_observations`/`metric_summary`；`tests/test_api.py` | 部分实现（本地导入）；外部阻塞 | 真实账号读取不能用导入数据或 logged-in 状态替代 |
| 数据存储 | JSON 文件：`data/drafts/*.json`；登录状态和二维码路径在 `data/login`；Playwright profile 在用户目录 | SQLite WAL + Alembic；`CreatorOS/data/assets` 保存文件；配置 `CREATOROS_DATA_DIR`/`CREATOROS_ASSET_DIR`；迁移 `0001–0007` | 已实现（本地） | CreatorOS 追踪关系更完整；需继续补 job/connector 凭据隔离和清理策略 |
| API | `/status`、`/account`、`/account/login`、`/account/login/status`、`/drafts`、`/drafts/{id}/publish`、`/analytics` | FastAPI `/api/v1`：画像、任务、输入、简报、产物 revision、记忆、热点、指标、连接器、草稿和导出 | 已实现（本地契约） | 不是 API 一比一迁移；真实 WeChat API 行为仍未接入 |
| 测试 | 2 个 Python 测试：status scope、JSON repository round-trip；前端无行为测试 | 15 个 CreatorOS Python 测试、3 个前端测试文件共 4 个测试；另有 API/构建/typecheck | 已实现（本地验证） | 测试数量不能替代真实浏览器/账号验收；需为每个垂直切片增加流程测试 |
| 许可证/来源 | HEAD 工作树未发现项目级 `LICENSE`/`NOTICE`；README/PRODUCT/DESIGN 为产品资料 | CreatorOS `docs/04-provenance-and-licenses.md` 记录未复制第三方源码、当前不授予再分发许可 | 外部限制已记录 | 只借鉴行为边界；不复制 对照实现 源码、Skill 实现、Prompt 或视觉资源 |

## 2. 文章生成能力逐项核对

| 需求 | CreatorOS 当前实现证据 | 状态 | 第一阶段结论 |
| --- | --- | --- | --- |
| 主题输入 | `ContentTaskCreate.input_type=theme`；`POST /tasks`；工作台主题表单 | 已实现 | 保存为 `task_inputs`，可生成本地简报 |
| 链接输入 | `input_type=url`、`input_metadata`；工作台可追加链接 | 部分实现 | 只保存 URL/元数据；没有抓取、解析、可读范围或失败重试 |
| 文本/会议记录输入 | `input_type=notes` 或文本任务；`task_inputs.text` | 已实现（本地保存） | 可进入简报，但没有会议说话人/时间戳结构化解析 |
| 文件输入 | `POST /tasks/{id}/inputs/file`，25MB 上限、SHA-256、Markdown/TXT 摘要，否则 `stored_only`；迁移 `0004` | 部分实现 | 文件资产可追溯；PDF/Word/图片/视频没有解析/OCR/转写 |
| 热点输入 | `hotspots` + `hotspot_evidence`；`POST /hotspots/{id}/task` | 部分实现 | 可手动入池并进任务；RSS/官方公告/BetterOPC 适配器未实现 |
| 研究阶段 | 任务状态含 `researching`；`create_brief` 产生研究缺口 | 部分实现 | 只有状态和缺口字段，没有研究作业、原文读取记录或来源队列 |
| 来源保存 | `task_inputs.metadata_json`、简报 `sources/input_ids/reference_to_original`、revision `source_ids` | 部分实现 | 能保存用户输入来源；没有来源类型、读取范围、访问失败和引用定位模型 |
| 事实核 | 简报 `facts=[]`、热点 `fact_status`/evidence verification | 部分实现 | 字段存在但生成模板不填外部事实；不应显示为已核验 |
| 作者观点/增量 | 简报 `author_angle`；模板把它写入平台字段 | 部分实现 | 有入口但没有作者材料门禁和观点证据要求 |
| 读者问题 | 画像 readers 生成 `reader_problem`；任务保存同名字段 | 已实现（结构） | 需要页面明确展示“读者要完成的动作”和缺口 |
| 简报生成/编辑/确认 | `POST /tasks/{id}/briefs`、`brief-revisions`、`.../confirm`；`Brief` 版本和状态；API 测试覆盖 | 已实现（本地） | 确认是生成前门禁；简报仍缺三问、参考—原创映射的强校验 |
| 公众号长文 | `demo_content.py` 输出标题候选、摘要、sections、事实引用、封面/配图说明、natural ending | 只有模板 | 字段形状可用，内容不是 LLM 结果，事实引用为空 |
| 小红书标题 | 模板输出 `title_candidates/title` | 只有模板 | 没有标题实验或读者任务验证 |
| 小红书封面 | 模板输出 `cover_copy` | 只有模板 | 没有 PNG/图片生成、尺寸校验或实际预览 |
| 小红书卡片 | 模板输出 4 页 `cards`、`image_prompts` | 只有模板 | 没有卡片渲染、逐页编辑和图片资产追踪 |
| 小红书正文/话题 | 模板输出 `body/topics` | 只有模板 | 没有独立质量门禁或平台发布包 |
| 抖音标题/3 秒开场 | 模板输出 `title/hook_3s` | 只有模板 | 没有时长实测和配音执行 |
| 抖音口播/分镜/字幕 | 模板输出 `voiceover/shots/subtitle` | 只有模板 | 有结构字段，没有视频或音频产物 |
| 抖音 B-roll/音乐 | 模板输出 `broll_suggestions/voice_and_music` | 只有模板 | 没有来源权利状态、素材文件或 B-roll 资产 |
| 版本与编辑 | `artifact_revisions`、`edit_events`、乐观 `base_revision_id`；前端可编辑完整字段；历史 API | 已实现（本地） | 没有“版本差异”页面、撤销快捷操作和局部编辑 API |
| 回滚 | 画像支持 restore 形成新版本；产物保留 parent revision | 部分实现 | 无产物回滚动作，用户只能从历史读取后重新提交整个 content |
| 记忆 | `memories` 从 edit event 提议；accept/reject/edit/revoke API 与页面操作 | 已实现（本地） | 需要显示依据、采纳影响、有效期和跨任务检索边界 |
| 来源追溯 | 产物 revision 有 `profile_version_id/brief_id/source_ids/memory_ids`；草稿有 task/artifact/revision 三元组 | 已实现（数据） | 前端只截断 ID，不能沿链点击回查 |
| LLM 适配器 | `demo_content.generate_content` 是唯一生成入口，标记 `demo_deterministic` | 只有模板 | 尚无 `LLMAdapter` 协议、能力检测、模型配置或真实调用 |
| Prompt 版本 | 没有 prompt 表、版本字段或 API | 未实现 | 后续必须记录 prompt 名称、版本、输入摘要和输出状态，不能把模板名当 prompt 版本 |
| 失败重试 | 连接器/公众号草稿有失败与重试；`generate` 只在已有产物时拒绝覆盖，没有 generation job | 部分实现 | 生成失败不持久化 job/error/attempt，也无法单平台重试且保留旧版本 |
| 本地模板回退 | `demo_deterministic` 可离线生成三平台结构化内容 | 只有模板（可作为回退） | 必须显式标记 fallback；不能将模板结果命名为模型生成或质量通过 |
| Markdown/JSON/HTML 导出 | `GET /artifacts/{id}/export` | 已实现（本地） | 卡片、脚本、分镜仍是结构化文本导出，不是媒体包 |

## 3. Skills → 页面/API/模型/测试映射

读取范围包括工作区 `.agents/skills` 中的 `suibo-human-first-writing`、`wechat-viral-topic`，以及可用的全局 Skill `operate-suibo-wechat`、`operate-juejin-ai-content`、`operate-xiaohongshu-ai-content`、`enforce-suibo-human-writing`。工作区没有单独的 `suibo-four-tool-wechat`、`operate-suibo-content-growth`、平台发布 Skill 文件，不能把名称存在于其它环境当作 CreatorOS 已接入。

| Skill / 约束 | 页面映射 | API/模型映射 | 测试/证据 | 状态 |
| --- | --- | --- | --- | --- |
| `suibo-human-first-writing`：作者材料/外部事实/读者信号/编辑推断/未知项分层；材料不足则缩小交付 | 当前没有专门的材料分层面板；工作台只显示输入、简报和作者角度 | `task_inputs`、`Brief.payload` 可存 text/sources/reader_problem/author_angle，但无五类枚举或来源角色 | 现有 API 测试只验证简报和模板，不验证材料门禁 | 部分实现（数据承载，门禁未实现） |
| `wechat-viral-topic`：同平台文章、月均阅读倍数、来源 URL、热度证据，缺 API 标 `source_blocked` | `HotspotsPage` 可手填热度状态/来源；没有查询或证据状态筛选 | `Hotspot.heat_status`、`HotspotEvidence`；无外部 API adapter、月均阅读字段 | `test_hotspot_and_metrics_import_are_traceable` 只验证手动线索 | 部分实现（手动线索）；外部阻塞 |
| `operate-suibo-wechat`：模式路由、truth ledger、作者现场、主对标、自然结尾、发布包和不自动发布 | 工作台的三平台字段和草稿中心；没有 truth ledger/参考映射/质量卡页面 | `Brief` 有 `reference_to_original`，公众号模板有 `ending_policy=natural`；无发布包模型/质量卡 | 没有公众号正文门禁测试；草稿测试只验证本地流程 | 部分实现 |
| `operate-juejin-ai-content`：工程问题、可复核资产、证据简报、代码边界、标题/封面/包审计 | CreatorOS 没有掘金独立入口；抖音/小红书/公众号三个入口代替不了掘金 | 无 Juejin 平台枚举、文章包、证据 manifest 或 audit API | 无对应测试 | 未实现 |
| `operate-xiaohongshu-ai-content`：读者回报、封面/卡片、实际图片检查、保留否定版本 | `Workspace` 有 XHS 字段编辑和结构化导出；无卡片画布/图片检查 | `demo_content` 有 `cover_copy/cards/image_prompts`；无媒体资产/版本化提示词 | 仅测试三平台内容不相同；无图片检查测试 | 只有模板 |
| `enforce-suibo-human-writing`：质量卡→SHA→朱雀预算/检测/回执，80/20/0 硬门槛 | 无质量审校页、检测台账、门禁结果和正文指纹视图 | 无 `quality_gate`、`human_gate_receipt`、sha/检测模型/次数表 | 无测试；不能把现有本地模板标 `final` | 未实现；外部阻塞 |
| 公众号新四工具工作流（项目说明要求）：TrendRadar、wechat-viral-topic、AIWriteX、WeWrite 运行记录/主对标/任务书/原创映射 | 无四工具运行记录页或研究资料目录同步 | 无 run record、benchmark、WeWrite brief、source ledger 模型 | 无测试；工作区 Skill 文件缺失 | 未实现；外部/工具缺失 |
| 发布门禁：生成≠草稿箱，草稿箱≠发布；缺凭据保持未连接 | `DraftCenter` 明确 Mock；`SettingsPage` 显示 adapter kind/state | `connector_states/events`、`wechat_drafts/events`，没有 publish 默认路由 | `test_wechat_draft_cover_and_submit_retry`、`test_mock_connector_state_machine_and_retry` | 已实现（本地边界）；真实平台外部阻塞 |

## 4. 数据、状态和测试缺口

### 已存在的基础模型

`creator_profiles`/`creator_profile_versions`、`content_tasks`/`task_inputs`/`task_events`、`briefs`、`platform_artifacts`/`artifact_revisions`/`edit_events`、`memories`、`hotspots`/`hotspot_evidence`、`metric_imports`/`metric_observations`、`connector_states`/`connector_events`、`wechat_drafts`/`wechat_draft_events` 已由迁移 `0001–0007` 覆盖。它们支持本地追溯，但不自动证明来源已读、事实已核验、模型已调用或平台已提交。

### 必须在实现阶段补齐的模型/接口

1. `research_runs` / `source_reads`：记录输入来源、抓取时间、可读范围、解析状态、失败原因、人工核验和引用定位。
2. `generation_jobs`：记录阶段、平台、adapter、模型/Prompt 版本、attempt、取消、失败、重试和旧 revision 保留策略。
3. `quality_gates` / `human_gate_receipts`：记录平台、正文 SHA、检查项、阈值、回执状态和阻断原因。
4. `artifact_exports` / `media_assets`：把文章、卡片、脚本、分镜和图片/视频文件区分开，保留来源与权利状态。
5. `experiment_records`：单一主要变量、样本量、观察时间和平台原生字段；无数据不得推导增长结论。

这些是差异项，不在第一阶段新增；进入第二、三阶段时每一项都要配迁移、API、页面和测试。

## 5. 验证结果与外部限制

- 对照实现 Python：2 passed；前端 `npm run build` 通过；没有修改参考仓库。
- CreatorOS Python：15 passed（使用项目 `.venv/bin/pytest`）；前端 typecheck 通过，Vitest 4 passed，Vite build 通过。
- 当前未执行真实浏览器扫码、真实 LLM、真实热点 API、账号官方 API、真实微信封面上传/草稿写入、朱雀检测、媒体渲染和发布。
- 对照实现 未发现项目级 `LICENSE`/`NOTICE`；CreatorOS 只保留自己的来源边界记录，不把参考代码或第三方 Skill 实现复制进来。
- 旧有截图只能证明之前记录的本地页面状态；本阶段没有用旧截图替代新的浏览器流程验收。

## 6. 实现顺序建议（作为第二阶段入口）

1. 先补总览/导航/工作台的阶段状态、恢复、来源和脏状态；不引入新平台连接器。
2. 再补 `research_runs`、证据账本、简报差异和生成 job，使主题/链接/文本/文件/热点五类输入能解释其状态。
3. 然后把三平台模板改成可替换 adapter：模板回退仍保留，但 UI 明确显示 `template_fallback`。
4. 最后再做公众号本地草稿、导出和 Mock 提交体验；真实连接器另列外部验收，不能与 Mock 结果合并。

本矩阵完成了第一阶段的范围审计；任何实现切片都应回填“修改文件、模型/迁移、API、页面流程、测试、截图、限制和回滚快照”，并更新后续交付文档。
