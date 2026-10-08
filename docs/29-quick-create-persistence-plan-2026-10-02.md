# 快速创作主链修复方案

状态：首批窄切片已实现，后续工作仍按本方案推进，2026-10-02（Asia/Shanghai）。

已完成：`0009_quick_draft_persistence` 迁移、`POST/GET /api/v1/quick-drafts`、服务端输入版本与幂等保存、内容库回读，以及工作流显式 `BLOCKED` 状态识别。媒体、结构化平台 Artifact、真实平台连接和发布仍未实现。

## 目标

让普通用户从“热点/手动主题 → 生成 → 编辑 → 保存 → 刷新后回看”得到一条可解释的本地链，同时保留 CreatorOS 现有的画像、简报、平台版本和草稿状态边界。保存成功只能表示本地 CreatorOS 已持久化；不表示事实已核验、图片已生成、平台草稿已提交或已经发布。

## 当前缺口

- `QuickCreatePage` 只把结果写入 `creatoros:quick-drafts`，`StudioLibraryPage` 只读取这份浏览器数据。
- `ContentTask` 必须绑定已确认的画像版本，`ArtifactRevision` 必须绑定简报和画像版本；不能为了接线而伪造画像、自动确认简报或把自由 Markdown 冒充平台结构化产物。
- 六阶段工作流写入 Markdown 文件，不提供与 `PlatformArtifact` 相同的结构化平台字段，也没有媒体文件契约。
- 工作流曾只检查 runner 返回非空文本，`BLOCKED` 文本会错误地被视为完成；该问题已修复，修复前回执见 [`docs/evidence/2026-10-02-audit-followup/workflow-blocked-result-before-fix.json`](evidence/2026-10-02-audit-followup/workflow-blocked-result-before-fix.json)，当前回执见 [`workflow-blocked-result.json`](evidence/2026-10-02-audit-followup/workflow-blocked-result.json)。

## 第一切片的变更边界

### 要做

1. **已完成**：在工作流 runner 边界解析结构化阻断结果和保守的 `BLOCKED`/`not_configured`/`unsupported` 标记；写入 `blocked`、阶段原因和可重试阶段，不生成完成归档。
2. 为 `ContentTask` 增加可空、唯一的 `quick_draft_id`，把浏览器草稿的稳定 ID 绑定到服务端任务，避免重复点击产生重复任务。
3. 增加 `POST /api/v1/quick-drafts` 和 `GET /api/v1/quick-drafts`：
   - 首次保存要求存在已确认的当前画像；没有画像时返回可行动的 `409 profile_required`，并保留浏览器恢复草稿。
   - 首次保存创建 `ContentTask` 和 `TaskInput(input_type="generated_markdown")`，保存主题、来源、平台、模式、Skill、工作流 ID、原始输出路径和保存时间。
   - 同一个 `quick_draft_id` 再保存时追加新的不可变 `TaskInput`，不覆盖旧输入；返回当前任务 ID和输入版本。
   - 返回中明确 `persistence_state="saved_input"`、`content_status="draft"`、`publish_state="not_started"`，不返回“已核验/已生成图片/已发布”。
4. 内容库优先读取服务端任务和输入版本；浏览器 localStorage 只作未提交恢复和迁移缓存。已保存的条目显示任务 ID、画像版本和输入版本；未同步条目显示“仅保存在本机”并提供重试。
5. 快速创作保存后提供“继续完整工作台”入口。进入工作台后，用户仍需查看/编辑简报并明确确认，才能调用现有 `generate_artifacts` 创建三平台结构化版本。
6. 增加后端 API、重复保存、刷新回读、阻断识别和前端状态测试；测试全部使用隔离临时目录和合成 runner，不调用真实模型、账号或发布接口。

### 明确不做

- 不把六阶段 Markdown 自动转换成 `PlatformArtifact`，不自动确认 Brief，不伪造作者经历、事实来源或平台字段。
- 不实现图片 provider、视频生成、媒体尺寸/版权校验或媒体预览；“配图”仍必须在生成前显示未接入/阻断状态。
- 不接入真实平台登录、二维码/OAuth、草稿提交、发布、指标读取或生产部署。
- 不重构 `vendor/easel/web/app.py`，不修改外部对照实现。
- 不在本切片补齐完整画像编辑、研究账本、指标反馈和长期记忆确认；这些属于后续独立切片。

## 跨层契约

### 保存请求

```json
{
  "quick_draft_id": "browser-generated-stable-id",
  "topic": "用户输入的主题",
  "context": "用户补充素材",
  "source": {"title": "热点标题", "url": "https://...", "source_name": "来源名"},
  "platform": "wechat",
  "mode": "文章",
  "skill": "social-content",
  "workflow_id": "12位小写十六进制 ID 或 null",
  "output": "当前用户编辑后的 Markdown",
  "output_artifact": "工作流产物相对路径或 null"
}
```

### 保存响应

```json
{
  "task_id": "稳定任务 ID",
  "input_id": "本次不可变输入 ID",
  "input_version": 2,
  "profile_version_id": "画像版本 ID",
  "persistence_state": "saved_input",
  "content_status": "draft",
  "publish_state": "not_started"
}
```

API 层负责校验长度、枚举、ID 格式和 JSON 形状；服务层负责事务、幂等查找、任务事件和画像绑定；前端只消费这个响应，不读取数据库字段或自行推断发布状态。

## 预期修改文件

- `creatoros/db/models.py`：`ContentTask.quick_draft_id` 及唯一索引。
- `migrations/versions/0009_quick_draft_persistence.py`：可重复执行的 SQLite 迁移，保留旧行并允许空值。
- `creatoros/domain/content.py`：保存请求/响应 DTO 和 `generated_markdown` 输入类型。
- `creatoros/services/content_service.py`：幂等保存、版本输入、任务事件和查询投影。
- `creatoros/services/workflow_service.py`：阻断结果解析；不改变真实 runner 调用权限。
- `creatoros/api/app.py`：快速草稿路由和结构化错误码。
- `web/frontend/src/api.ts`、`QuickCreatePage.tsx`、`StudioLibraryPage.tsx`：服务端保存/读取、未同步恢复、状态文案和“继续工作台”入口。
- `tests/test_api.py`、`tests/test_easel_parity.py`、新增 `web/frontend/src/lib/quickDraft.test.ts`：覆盖幂等、冲突、阻断和回读。

不应修改 `vendor/easel/`、外部对照实现、平台连接器和媒体 provider。

## 验收步骤

1. 在空隔离目录中没有画像时点击保存：返回 `409 profile_required`，浏览器草稿仍可恢复，没有伪造任务。
2. 创建并确认画像后保存一次：服务端只有一个 `ContentTask`、一个 `quick_draft_id`、一个 `TaskInput` 和一条 `quick_draft_saved` 事件；响应包含真实画像版本 ID。
3. 同一条内容连续保存两次：任务 ID不变，输入版本变为 2，版本 1 内容仍可读；不会新增第二个任务。
4. 刷新页面、清除本地草稿缓存后调用内容库：仍能看到服务端条目和完整 Markdown；服务端不可用时条目标为未同步，不静默删除。
5. 工作流合成 runner 返回 `BLOCKED`：作业保持 `blocked`，只允许重试，不写 `content_status=completed` 或归档完成态；正常非空内容才继续。
6. 快速草稿进入工作台：简报仍显示 `draft`，未点击确认不能生成 `PlatformArtifact`；确认后生成的三平台版本保留 `profile_version_id`、`brief_id` 和来源输入 ID。
7. 运行 `.venv312/bin/python -m pytest -q`、前端测试、类型检查和 `git diff --check`；不宣称视觉、真实平台或外部模型验收完成。

## 后续切片顺序

- **3 天**：研究来源账本、事实状态和快速反馈 → `proposed Memory`，补充确认/拒绝/撤销及生成引用展示。
- **1 周**：三平台独立编辑器、字段/媒体规则、可重试作业和一类真实媒体适配器；真实平台只在用户主动授权并有回读证据后接入。
- **更后**：指标导入与实验、真实小规模试用和 390/1024/1440 视觉回归；任何外部成功状态继续与本地草稿和 Mock 状态分开。
