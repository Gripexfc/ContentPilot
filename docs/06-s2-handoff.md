# S2 交付记录：独立骨架与个人画像版本

日期：2026-09-29（Asia/Shanghai）

## 修改文件

新增独立运行时和测试结构：

- `pyproject.toml`、`.gitignore`、`.env.example`、`Makefile`、`alembic.ini`：安装、配置、迁移和启动入口。
- `creatoros/config.py`：本地数据目录、端口、前端来源配置。
- `creatoros/db/`、`migrations/`：SQLAlchemy 模型、SQLite 连接参数、Alembic 初始迁移。
- `creatoros/domain/profile.py`：画像快照与 API DTO，自动补齐三平台 sections。
- `creatoros/services/profile_service.py`：创建版本、乐观并发冲突、递归差异、恢复为新版本。
- `creatoros/api/app.py`、`creatoros/cli.py`：FastAPI app factory、status、画像路由、结构化错误、`web/db` CLI。
- `web/frontend/`：React + TypeScript + Vite 编辑界面、API client、版本历史、差异和恢复。
- `tests/`、`web/frontend/src/lib/profile.test.ts`：后端服务/API/迁移测试和前端单元测试。
- `data/.gitkeep`：独立数据目录占位。

没有修改 `/Users/fc/Desktop/随波逐流/ContentPilot` 或 `.easel`，没有引入第三方源码，没有写入真实账号、令牌或外部平台数据。

## 数据模型与接口

数据库：

- `creator_profiles`：稳定画像 id 与当前版本指针。
- `creator_profile_versions`：不可变快照、父版本、版本号、变更说明、确认状态和时间。
- `alembic_version`：数据库迁移版本。

主要接口：

- `GET /api/v1/status`
- `GET /api/v1/profile`
- `GET /api/v1/profile/versions`
- `GET /api/v1/profile/versions/{version_id}`
- `GET /api/v1/profile/versions/{version_id}/diff/{other_id}`
- `POST /api/v1/profile/versions`
- `POST /api/v1/profile/restore/{version_id}`

保存画像时带 `base_version_id`；基线过期返回 HTTP 409。恢复不会删除旧版本，而是基于历史快照创建新版本。

## 如何启动

```bash
cd /Users/fc/Desktop/随波逐流/CreatorOS
make install
make db-upgrade
make backend       # 终端 A
make frontend      # 终端 B
```

默认 API 为 `http://127.0.0.1:8000`，前端为 `http://127.0.0.1:5173`。可用 `CREATOROS_DATA_DIR=/tmp/creatoros-data` 做隔离烟测。

## 实际验证

- `.venv/bin/pytest -q`：6 passed。
- `npm run typecheck`：通过。
- `npm test -- --run`：1 test passed。
- `npm run build`：Vite production build 通过。
- 临时目录下 `creatoros db upgrade` 连续执行两次：迁移版本保持 `0001_initial`。
- 本地 HTTP smoke：创建 v1 → 创建 v2 → diff 返回 `pillars` → restore 创建 v3 → 当前版本为 v3。
- Vite 开发服务器 `http://127.0.0.1:5173/` 可返回 CreatorOS HTML 入口。

## 已完成能力

- 独立安装和启动骨架。
- SQLite 数据目录、WAL/外键/busy timeout 连接配置和 Alembic 初始迁移。
- 个人画像创建、编辑、版本化、差异查看、乐观并发冲突和历史恢复。
- 画像快照覆盖身份、经历、领域、内容支柱、目标读者、语气、禁用词/敏感边界、公众号/小红书/抖音定位、内容目标和证据引用。
- 前端能展示当前画像、版本历史、差异和恢复操作。

## 尚未实现

内容任务、来源导入、简报、LLM 生成、三平台产物、用户修改事件、能力记忆、热点源、账号导入、指标分析、图片/视频生成、导出和平台连接器。

## 不能验证的外部平台行为

没有配置或调用 LLM、图片/视频服务、RSS、BetterOPC、公众号、小红书、抖音官方 API；没有登录、读取账号、提交草稿或发布。当前只能证明本地 HTTP、SQLite 和前端开发链路。

## 回滚方式

代码回滚到 S1 文档状态即可移除 S2 实现；开发烟测数据使用临时目录，可直接废弃。用户数据不通过手工删表回滚；后续变更使用新的 Alembic migration 和数据备份。

## 已知限制

- 当前是单用户本地工作区，没有登录和多用户权限。
- 画像保存 API 接受结构化快照，但证据文件尚未上传和绑定。
- 前端为 S2 编辑器，其他导航项仅作未启用占位。
- npm install 报告了依赖审计中的 5 个漏洞（3 moderate、1 high、1 critical）；本轮未执行可能引入破坏性升级的 `npm audit fix --force`，后续单独评估依赖版本。
