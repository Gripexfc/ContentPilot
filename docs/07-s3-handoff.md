# S3 垂直切片交付记录（返工前基线）

> 本文记录早期演示切片。2026-09-30 已补充真实编辑、版本历史、内容库回读和简报修订；返工边界见 `docs/08-usability-rework.md`。早期“已完成能力”不能替代返工后的验收。

## 修改文件

- `creatoros/db/models.py`、`migrations/versions/0002_content_flow.py`：新增任务、输入、状态事件、简报、平台产物、产物修订、用户编辑事件和能力记忆模型。
- `creatoros/domain/content.py`：任务、简报、产物、记忆的 API DTO 与状态/平台枚举。
- `creatoros/adapters/demo_content.py`：不访问网络的 deterministic adapter，生成三个不同的平台结构。
- `creatoros/services/content_service.py`：事务编排、状态推进、溯源、修订和记忆确认。
- `creatoros/api/app.py`：主题、简报、生成、修订、记忆 API 与 404/409 错误映射。
- `web/frontend/src/api.ts`、`Workspace.tsx`、`lib/content.ts`、`App.tsx`、`styles.css`：内容工作台、三平台卡片、编辑和记忆确认。
- `tests/test_api.py`、`tests/test_profile_service.py`、`web/frontend/src/lib/content.test.ts`：纵向 API 和前端辅助函数测试。

## 数据模型与接口

任务绑定创建时的 `profile_version_id`，不会随画像后续更新而漂移。任务输入保存在 `task_inputs`，状态变化写入 `task_events`。简报的 `facts`、`sources`、`research_gaps` 和平台计划是结构化字段；未核验来源保持空数组。

产物按 `wechat`、`xiaohongshu`、`douyin` 分开保存。每次生成或编辑创建 `artifact_revisions`，通过 `parent_revision_id` 串起历史；`edit_events` 记录字段路径、前后值和用户说明。由编辑事件产生的 `memories` 默认 `proposed`，只有用户点击确认才变成 `confirmed`。

主要接口：

- `POST /api/v1/tasks`、`GET /api/v1/tasks/{task_id}`
- `POST /api/v1/tasks/{task_id}/briefs`
- `POST /api/v1/tasks/{task_id}/briefs/{brief_id}/confirm`
- `POST /api/v1/tasks/{task_id}/generate`
- `POST /api/v1/artifacts/{artifact_id}/revisions`
- `GET /api/v1/memories?task_id=...`、`POST /api/v1/memories/{memory_id}/accept`

## 启动与测试

```bash
cd CreatorOS
make install
make test
make lint
cd web/frontend && npm run build
```

实际结果：后端 8 个 pytest 用例通过；前端 2 个 Vitest 用例、TypeScript 检查和 Vite 构建通过。测试使用临时 SQLite 目录，不写入默认用户数据目录。

## 已完成能力

个人画像 → 手动主题 → 简报 → 三平台独立草稿 → 内容库回读 → 用户修改 → 待确认能力记忆 → 用户确认，已形成可运行纵向流程。未确认简报直接生成会返回 409，避免跳过人工确认。

## 尚未实现能力

当前只支持手动文本主题；链接、文件、热点源、账号导入、图片生成、卡片/PDF/Markdown 导出、FFmpeg 媒体模块、真实模型、平台 API 和发布流程尚未实现。`demo_deterministic` 只是本地测试替身，不是模型质量或平台效果证明。

## 外部平台行为

未配置、未连接和未触发任何 LLM、新闻源、图片服务、视频服务、公众号、小红书或抖音接口。当前状态 `adapted` 只表示本地三份草稿写入 SQLite，不表示审核通过、提交草稿或发布成功。

## 回滚方式

代码回滚到 S2 文件版本即可恢复画像和空内容工作台；开发数据库可删除后从 `make db-upgrade` 重建。用户内容修订不覆盖旧 revision，能力记忆可保持 `proposed` 或在后续加入撤销，不需要修改历史正文。生产或真实用户数据迁移前应先备份 SQLite 文件，不手工改迁移版本。
