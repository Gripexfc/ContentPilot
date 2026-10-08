# 当前验收报告

日期：2026-10-01（Asia/Shanghai）
阶段：第一阶段审计完成；总览/工作台第一条 UX 垂直切片完成本地验证。

## 修改文件

- `creatoros/api/app.py`：新增 `/api/v1/overview` 汇总接口。
- `creatoros/domain/ops.py`：新增 `OverviewRead` 契约。
- `tests/test_api.py`：增加空数据和有任务/热点时的总览快照测试。
- `web/frontend/src/api.ts`：增加 Overview 类型和 client。
- `web/frontend/src/Pages.tsx`：总览显示恢复计数、草稿和导入时间。
- `web/frontend/src/Workspace.tsx`：输入自动保存/恢复、输入类型恢复、简报证据计数。
- `web/frontend/src/styles.css`：自动保存和证据状态样式。
- `README.md`、`docs/14-experience-audit.md`、`docs/15-full-feature-parity.md`、本文件及 `docs/16/17`：同步状态与边界。

## 验证结果

- CreatorOS Python：`16 passed`（项目 `.venv/bin/pytest -q`）。
- 前端：`npm run typecheck` 通过；Vitest `4 passed`；Vite `npm run build` 通过。
- 对照实现 只读基线：Python `2 passed`（使用 CreatorOS 环境加 `PYTHONPATH`）；前端 `npm run build` 通过；`git status` 干净。
- 本切片没有启动真实平台登录、LLM、热点采集、账号 API、微信后台提交、朱雀检测或媒体渲染；本轮 AI 浏览器对照证据另见 docs/evidence/2026-10-01-ai-browser-parity/。

## 完成/Mock/未实现/外部限制

| 类别 | 当前项 |
| --- | --- |
| 已完成 | 总览快照 API、任务/记忆/热点/草稿/指标计数、本地输入恢复提示、简报来源计数、静态/单元/API 测试 |
| Mock | 三平台离线模板、公众号连接器配置/连接/读取/提交、失败重试 |
| 未实现 | 真实 LLM/Prompt 版本、研究采集、平台专属重写、job 取消与重试、内容库多维筛选、卡片/视频媒体、质量门禁和实验记录 |
| 外部限制 | 真实账号凭据/扫码、官方 API 权限、热点 API、朱雀验证码/次数、媒体编码环境 |

## 回滚快照与下一条切片

CreatorOS 当前目录没有独立 Git 元数据；本次回滚清单和 SHA-256 见 `docs/evidence/2026-10-01/rollback-manifest.sha256`，只涉及上述 CreatorOS 文件。对照实现 的 Git HEAD 未改动。下一条垂直切片是“主题/链接/文本/文件/热点 → 研究证据账本 → 可编辑简报差异”，完成前继续保持模板回退和外部能力分层。
## AI 浏览器对照验收（2026-10-01）

使用同一 TaskSpace（2）和同一 QA 输入，对 对照实现（p1）与 CreatorOS（p2）进行了真实 Ego Lite 页面操作；证据保存在 docs/evidence/2026-10-01-ai-browser-parity/。

- CreatorOS 已走通主题 → 简报 → 确认 → 三平台模板 → 本地公众号草稿 → 编辑保存/刷新 → 封面校验 → Mock 失败/刷新/重试；有效 PNG 成功、无效文件被明确拒绝。
- CreatorOS 设置、工作台、热点和分析页明确标记“演示模板 · 未连接 LLM”“RSS/官方源待接入”“官方 API 待接入”“真实 AI 生成尚未接入”；指标导入只做结构性分析。
- 对照实现 新建草稿可保存，但已有草稿编辑后刷新回旧值；这是对照实现当前基线缺陷，不能把两边描述成已经完全一致。
- 对照实现 真实提交在隔离环境显示“公众号草稿提交失败：ModuleNotFoundError”；没有登录、扫码或真实提交证据。

因此，本轮结论是：**CreatorOS 本地流程通过，真实外部能力和高质量内容能力不通过/未接入，不能称为对照实现真实能力的等价替代，也不能称为高质量成稿或越用越强。**

## 现有功能对齐修复（2026-10-01）

本轮只修改 CreatorOS；对照实现、`.easel` 和用户内容未改动。修改前文件 SHA-256 清单和本轮截图位于 `docs/evidence/2026-10-01-repair/`。CreatorOS 没有独立 Git 元数据，未伪造提交。

### 已修复并验证

- **B1**：草稿提交异常后后端立即写入 `failed` 事件，前端提交失败分支会回读列表/详情，当前状态、错误和事件数即时更新；未配置/未读取连接器时显示“去设置与连接器”。
- **B2**：所有草稿操作开始时清掉旧成功提示；无效封面后不会残留“封面已保存”。
- **B3**：API 对草稿、草稿事件、连接器和内容工作流时间统一输出带 `+00:00` 的 UTC ISO；前端统一经 `dateLabel` 显示 Asia/Shanghai。本轮浏览器回执 `02:00:09+00:00` 显示为 `10:00:09`，没有 8 小时错位。
- **B4**：补齐 `writing/ready/submitted` 中文状态；导航标题随路由变化（实测 `CreatorOS · 总览`、`CreatorOS · 公众号草稿中心`、`CreatorOS · 账号分析`）。
- **B5**：只把 `confirmed` 且未撤销、平台范围匹配的记忆传入后续模板生成，并写入 `revision.memory_ids` 和 `memory_guidance`。AI 浏览器同一输入对照：首次无记忆；采纳“公众号开头保留真实现场”后第二任务引用该 memory；撤销后第三任务引用为空。

### 已实现、待真实账号现场验收

- **A1**：新增可选 `browser` 微信公众号适配器，持久化本地 Playwright 会话，支持依赖预检、登录中/二维码等待、过期和失败恢复、`whoami` 会话核验；未扫码/未核验不会返回真实 `connected`。默认仍为 Mock。
- **A2**：真实适配器包含封面素材上传和草稿提交调用；提交成功保存 `remote_id` 与非敏感回执，已提交草稿幂等返回，失败保留错误和事件供重试。当前任务没有真实公众号写入授权，因此未执行外部写入。
- **A3**：新增 `GET /api/v1/analytics/wechat` 与分析页“读取公众号后台数据”入口；Mock/CSV/JSON 不会被冒充真实读取，真实读取回执包含 `source`、`fetched_at`、发表记录和限制说明。

真实账号验收所需条件：`CREATOROS_WECHAT_ADAPTER=browser`、安装 `.[wechat]` 可选依赖、用户自行扫码/验证码。密钥、Cookie、二维码和真实草稿均未写入仓库或本轮隔离数据。

### 本轮实际验证

- 后端：`.venv/bin/pytest -q`，**15 passed**；覆盖 B1 失败事件、B5 跨任务记忆采纳/撤销、0008 迁移幂等和 browser 适配器不冒充连接成功。
- 前端：`npm test -- --run`（4 passed）、`npm run typecheck`、`npm run build` 均通过。
- AI 浏览器：续用 Ego Lite TaskSpace 2（p1 对照实现、p2 CreatorOS），隔离数据目录 `/private/tmp/creatoros-ui-20261001-repair`，服务端口 18310。实际完成主题→简报→确认→三平台模板→本地草稿→编辑读取→无效/有效封面→未配置提交失败即时刷新→配置/连接/读取→Mock 失败/重试→跨任务记忆应用/撤销；截图在 `docs/evidence/2026-10-01-repair/screens/`，步骤和回执在同目录 `browser-results.md`。
- 视口复核：390、1024、1440；截图分别为 `analytics-390.png`、`analytics-1024.png`、`settings-1440.png`、`draft-failed-1440.png`、`draft-submitted-1440.png`。

### 仍未实现或未授权

真实 LLM、研究采集、图片/视频生成、完整质量门禁、发布/群发仍未实现；真实公众号扫码、后台提交和后台数据读取没有在本轮执行。它们不因 Mock、模板或导入记录而升级为“已接入”。
