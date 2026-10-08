# CreatorOS × 对照实现 功能差异矩阵

核对日期：2026-09-30（Asia/Shanghai）
参考项目：`对照目录`（Git `0e9e9dd2880227802843c24c5cce2fe0ed4772fe`）
目标项目：`CreatorOS`

这份矩阵只记录能在源码、迁移、测试或本地运行结果中定位的事实。对照实现 目录保持只读；CreatorOS 的扩展能力不会通过复制参考代码实现。

## 参考项目能力基线

| 能力 | 对照实现 证据 | 目标行为 | CreatorOS 当前状态 | 差异/动作 |
| --- | --- | --- | --- | --- |
| 本地内容工作台 | `PRODUCT.md`；`web/frontend/src/App.tsx` | 在本机管理可恢复内容 | 已有总览、工作台、内容库、记忆页 | 保留并统一 shell 视觉；不复用参考布局 |
| 内容库 | `baseline-module/storage/repository.py` 的 JSON 草稿仓 | 任务、版本、来源可检索 | SQLite `content_tasks`、`briefs`、`platform_artifacts`、revision 链 | CreatorOS 是扩展实现；保留导出与回读 |
| 公众号账号状态 | `api/app.py`：`GET /api/v1/account`、`/account/login/status` | 明确区分未配置、已连接、读取成功 | 仅设置页静态显示“未连接” | 当前缺口：本地连接器状态 API；真实登录保持未接入 |
| 登录触发 | `POST /api/v1/account/login`；`integrations/wechat.py` | 只在用户点击时打开登录流程 | 无对应入口 | 补 Mock Connector 的显式连接动作；不伪造真实登录 |
| 草稿创建/读取/编辑 | `DraftCreate`、`POST/GET /api/v1/drafts` | 保存标题、摘要、作者、正文 HTML、封面和状态 | SQLite `wechat_drafts`，支持本地保存/回读/复制 | 已实现本地草稿中心；真实微信写接口仍未接入 |
| 封面路径/预览 | `Draft.cover_path`；参考前端封面区域 | 本地封面资产可预览 | `wechat_drafts.cover_path` + PNG/JPEG/WebP 头部、尺寸和 10 MB 校验 | 已实现本地封面；真实微信上传未接入 |
| 明确草稿提交 | `POST /api/v1/drafts/{id}/publish`；适配器只提交草稿不群发 | 用户显式触发，提交状态可回看 | `POST /api/v1/drafts/{id}/submit`，仅本地 Mock | 已实现 Mock；真实平台仍 unsupported |
| 提交失败与重试 | `WeChatError` 写回 `status=failed`、`publish_error` | 错误原因持久化，新 attempt 不覆盖旧错误 | `wechat_draft_events` 保留失败/成功链；失败可重试，成功提交幂等 | 已实现 Mock 契约；真实适配器仍缺授权和回执 |
| 基础账号数据读取 | `GET /api/v1/analytics`；`fetch_stats()` | 明确读取触发、无数据不造增长率 | CSV/JSON 指标导入 + 描述性摘要 | 已有本地数据路径；官方 API 仍待接入 |
| SQLite 持久化 | 参考项目为 JSON 文件，并无 SQLite 模型 | 目标使用 SQLite + 迁移 | Alembic `0001`–`0004`、SQLite WAL | CreatorOS 扩展并符合本地优先约束 |
| 前后端 API | FastAPI 路由与 React API client | 单一契约、错误可恢复 | FastAPI + TypeScript client | 保留；后续补连接器契约 |
| 测试 | `对照实现/tests` 覆盖 scope/repository | 每个切片有 API/服务/前端验证 | 后端 11 passed；前端 2 passed；typecheck/build 通过 | 新增连接器和视觉状态测试 |

## CreatorOS 产品扩展（参考项目没有）

| 扩展 | 代码/数据证据 | 当前状态 |
| --- | --- | --- |
| 个人画像版本、差异、恢复 | `creator_profile_versions`、`profile_service.py`、`tests/test_profile_service.py` | 已实现；恢复创建新版本 |
| 主题到任务状态机 | `ContentTask.status`、`content_service.py` | 已实现 `idea → researching → briefed → drafting → adapted → reviewing → archived` |
| 来源与输入资产 | `task_inputs`、`POST /tasks/{id}/inputs/file` | 已实现主题、链接、文本和本地文件摘要/哈希 |
| 热点池与人工核验 | `hotspots`、`hotspot_evidence`、`/hotspots` | 已实现手动入池；RSS/官方采集未实现 |
| 三平台独立产物 | `platform_artifacts`、`demo_content.py` | 已实现独立字段；需继续视觉和专属编辑体验 |
| 版本/修改/能力记忆 | `artifact_revisions`、`edit_events`、`memories` | 已实现 proposed/confirmed/rejected/revoked 流程 |
| 指标导入与结构性分析 | `metric_imports`、`metric_observations`、`metric_analysis.py` | 已实现 CSV/JSON 主动导入；无数据时不生成增长率 |
| Markdown/JSON/HTML 导出 | `GET /artifacts/{id}/export` | 已实现 |

## 无法在本地验证的外部行为

| 行为 | 为什么不能宣称完成 | 当前产品状态 |
| --- | --- | --- |
| 公众号扫码登录、会话有效性 | 需要用户设备、扫码和官方后台 | `not_configured` / `unsupported` |
| 公众号封面上传、草稿提交回执 | 需要真实管理员会话、后台接口和可用封面 | Mock 适配器只验证本地状态机 |
| 公众号发表/分析数据 | 需要真实账号权限与后台返回 | 本地 CSV/JSON 可用，官方读取待接入 |
| RSS、BetterOPC、政府/监管源自动采集 | 需要网络、来源可访问性和当前授权 | 手动热点入口可用 |
| LLM、图片生成、视频渲染 | 需要模型/媒体服务配置与运行时额度 | `demo_deterministic`，明确标注未接入 |

## 第一切片边界与回滚

本轮第一切片是“可见的本地 SaaS 控制台 + 连接器状态契约”：

* 保留现有画像/任务/热点/分析/记忆 API 与页面行为；统一桌面和移动端视觉 token、状态组件、SVG 导航图标和空/错/离线状态。
* 新增本地 `connector_states` 表与 Mock Connector API，区分 `not_configured → configured → connected → read_succeeded → submit_succeeded → publish_succeeded`，失败保留 `failed` 和错误码；不触发外部平台。
* 设置页读取真实状态并提供显式连接、读取、提交测试和失败重试；所有动作写本地审计记录。

明确不做：真实扫码、公众号后台请求、自动登录、自动发布/群发、对照实现 或 `.easel` 修改、LLM/图片/视频生成。

回滚时删除 `0005_connector_states` 迁移和连接器路由/组件，数据库回退到 `0004_input_metadata`；前端 token 变更可独立回退，不影响既有业务表。

## 第二切片状态（2026-10-01）

在第一切片基础上已补齐公众号草稿中心：SQLite 草稿与事件表、从已保存公众号产物当前 revision 转入、来源三元组追溯、封面校验/预览、正文 HTML 编辑、脏状态保护、隔离 iframe 预览、明确提交、失败原因和重试。提交接口先检查 `wechat-oa` Mock Connector 已完成读取；成功回执只更新本地 `submitted`，不会声称真实公众号草稿箱成功。已提交草稿不可覆盖，可复制为新草稿。详细证据见 `docs/13-slice-2-draft-center-handoff.md`。
