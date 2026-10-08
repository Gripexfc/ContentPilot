# CreatorOS 技术与交互设计

状态：设计基线 v0.1，2026-09-29；S3 可运行返工版已完成本地可继续编辑闭环，S4a/S4b 已完成手动热点入池与 CSV/JSON 指标导入，公开热榜自动读取已接入，RSS、平台 API、外部适配器和媒体导出仍按后续切片交付。

## 1. 约束与选择

CreatorOS 是单机、本地优先的桌面浏览器应用。默认 SQLite，文件资产在 data 目录；外部服务都通过可替换适配器进入。后端采用 FastAPI + Pydantic + SQLAlchemy 2.x，前端采用 React + TypeScript + Vite。第一版不引入常驻消息队列：短操作同步执行，长操作写入本地 job 表后由应用内 worker 轮询；重计算以后可换独立 worker。

SQLite 启动时启用 WAL、外键约束和 busy timeout；所有写入使用事务。SQLite 版本由运行时检查，低于项目最低支持版本时在启动页显示阻断。迁移使用 Alembic（首个基线迁移也可从空库执行）。数据目录和资产目录通过 `CREATOROS_DATA_DIR` / `CREATOROS_ASSET_DIR` 配置，默认落在项目 `data/`。

模型生成、热点源、平台连接器、图片生成、文件解析、视频/FFmpeg 都实现协议接口，并有 offline/no-op adapter。未配置适配器时返回结构化 `not_configured`，不伪造内容、媒体、账号或发布结果。

## 2. 分层与目录

```text
CreatorOS/
├── creatoros/
│   ├── api/                 # FastAPI app、依赖、路由和错误映射
│   ├── config.py            # 环境变量与安全默认值
│   ├── db/                  # engine、session、models、迁移入口
│   ├── domain/              # Pydantic DTO、枚举、状态机和纯业务规则
│   ├── repositories/        # 事务、版本、查询和幂等键
│   ├── services/            # profile/task/brief/production/analysis/memory
│   ├── adapters/            # llm、sources、platforms、media、importers
│   ├── jobs/                # job 状态、重试、取消和恢复
│   ├── assets/              # 安全文件名、sha、原子写入、导出 manifest
│   └── cli.py
├── web/frontend/
│   ├── src/app/             # 路由、布局、API client、query state
│   ├── src/features/        # profile、workspace、hotspots、library、analytics、memory
│   ├── src/components/      # 可访问的共享组件
│   ├── src/lib/             # API 解码、日期、格式化和能力状态
│   └── src/styles/
├── migrations/
├── tests/unit/
├── tests/api/
├── tests/integration/
├── web/frontend/tests/
├── data/.gitkeep
├── docs/
├── pyproject.toml
└── package.json (仅工作区脚本时再加入)
```

路由层只做认证/输入/输出映射；服务层编排事务和适配器；仓储层不能调用网络；前端不能拼接数据库字段或外部平台参数。共享契约用 OpenAPI 生成/校验，前端用单一 API client 解码，不在组件里对 unknown 做私有类型断言。

## 3. 数据流与状态

```text
输入/上传/热点 → source_record + asset → task
task + profile_version + confirmed memories → research/brief
brief + adapter → generation_job → platform_artifact revisions
用户编辑 → edit_event → artifact_revision + proposed_memory
用户确认 → profile/memory version
账号导入 → metric_import + metric_observation → analysis_snapshot → experiment
```

每条跨层记录保存稳定 id、created_at/observed_at、source_type、source_ref、status 和 error。外部适配器结果必须先写 job attempt 再更新业务状态；异常也写失败记录，重试创建新 attempt，不抹掉旧错误。长任务返回 202 + job_id，页面通过轮询读取状态，避免同步请求超时。

业务任务状态由服务层的显式转换表控制；非法跃迁返回 409。产物状态和任务状态分开，例如公众号可为 `generated`、小红书为 `failed`，任务仍处于 `adapted`。

## 4. 页面与交互

首个 shell 为侧栏 + 工作区，但风格独立设计，避免复制参考项目的品牌、紫色、三列卡片或装饰渐变。页面固定显示当前数据范围、证据状态、用户确认入口和恢复动作。

| 页面 | 主交付 |
| --- | --- |
| 总览 | 未完成任务、待确认画像/记忆、热点线索、无数据提示和最近失败 |
| 个人画像 | 当前版本、历史版本、差异、回滚（实际创建新版本）、证据引用和建议采纳 |
| 内容工作台 | 输入、来源/事实、读者问题、简报、生成作业、三平台产物和引用面板 |
| 热点与新闻 | 源过滤、事实/热度/读者证据、核验状态、画像相关度、进入任务 |
| 内容库 | 任务、产物版本、修订记录、导出、归档/重新打开 |
| 三平台适配 | 并列但独立的编辑器、适配状态、平台字段校验、单平台重试 |
| 账号分析 | 导入、列映射、观察时间/来源、空状态、趋势、解释和实验 |
| 能力记忆 | proposed/confirmed/rejected/revoked、来源链、适用范围和撤销 |
| 设置与连接器 | 本地目录、适配器配置存在性、用户触发连接、状态四级回执、重试 |

可访问性：语义表单标签、键盘可操作、可见焦点、状态文本而不只靠颜色、错误旁边给出恢复动作；编辑器窄屏按“证据 → 简报 → 产物 → 审核”顺序访问。

## 5. 外部能力与连接器状态

连接器统一返回：`not_configured → configured → connecting → connected → read_succeeded / submit_succeeded / publish_succeeded`，以及 `unsupported / failed / expired`。这些状态不是可互换的布尔值。发布接口默认不存在；将来加入也必须由用户点击并产生审计事件。

平台适配器只接收领域层的 PlatformDraftContract，不读取前端状态或数据库连接。账号令牌放在 macOS Keychain/系统凭据存储或外部用户配置里；日志只写连接器名、操作、状态、时间和 error_code，不写 Cookie、二维码、令牌、正文私密内容。

## 6. 失败、重试与回滚

- 解析失败：原资产保留，source 为 `parse_failed`，允许补充/替换，不覆盖原件。
- LLM/图片失败：任务保留 researching/drafting 之前的成功产物；job attempt 标 failed，可带指数退避重试。
- 单个平台失败：其它产物保持原版本；平台可单独重新适配，不能覆盖用户已编辑版本。
- 数据导入失败：事务整体回滚；保留导入文件和逐行错误，不保存部分指标为有效数据。
- 画像回滚：选择旧版本后创建一个新的 current 版本，并记录 restore_from_version_id；旧版本只读。
- 数据库迁移失败：启动阻断并保留备份；没有“自动修复生产库”的隐式行为。
- 导出失败：写入临时目录，校验 manifest 后原子移动；失败删除临时文件，数据库仍可重试。

## 7. 安全与隐私

默认绑定 localhost；生产部署（若未来支持）必须明确 origin、CSRF 和本地访问策略。上传文件用 MIME/扩展名/魔数与大小限制，存储名称使用随机 id；渲染 Markdown/HTML 时转义不可信输入。来源网页只作为数据，不执行页面脚本指令。

Git 忽略 `data/`、`.env*`、凭据、二维码、视频和生成大文件；日志做字段白名单。用户删除操作默认软删除并保留审计；物理清理单独明确。导出包自动包含来源和状态，不包含秘密。

## 8. 验证金字塔

1. 纯 Python 规则测试：状态机、画像差异、平台独立性、指标口径、记忆确认/撤销、manifest。
2. 数据库/API 测试：空库迁移、事务、版本冲突、导入回滚、job 重试和 API 错误码。
3. 前端类型/组件测试：表单、状态、空状态、编辑/采纳/拒绝、无障碍关键路径。
4. 本地纵向 smoke：启动 → 创建画像 → 主题 → brief → 三平台 → 修改 → proposed memory → 重启回读。
5. 外部适配器契约测试：只用固定 fixture/模拟服务器；真实账号、API 权限、模型额度和媒体编码另列未验证证据。
