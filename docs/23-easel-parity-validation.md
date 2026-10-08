# Easel 能力迁移验收记录

日期：2026-10-01（Asia/Shanghai）  
项目：`/Users/fc/Desktop/随波逐流/CreatorOS`  
官方只读基线：`https://github.com/ZJU-REAL/Easel`，checkout `4b9c03cf2129b6155595b66fc1e604546a3aa4ad`，许可 Apache-2.0。  
审计矩阵：[`docs/22-easel-official-parity-matrix.md`](22-easel-official-parity-matrix.md)。官方参考 checkout 和 `/Users/fc/Desktop/随波逐流/.easel` 均未修改。

## 本轮目标

本轮不是把官方 Easel 界面作为 CreatorOS 默认产品，而是将官方项目作为只读参考，抽取可复用能力并落到 CreatorOS 自有页面、数据模型和状态边界。默认入口保持 CreatorOS 品牌与页面结构，收缩为“看热点 → 开始创作 → 我的内容”；官方前端源代码只保留在 `vendor/easel/web/frontend/src/` 供对照。

## 已完成

- 官方 Easel 前端完整源代码固定到 `vendor/easel/web/frontend/src/`，官方后端和技能固定到 `vendor/easel/`，并由 `vendor/easel/UPSTREAM.json` 保存源文件 SHA-256。
- CreatorOS 默认入口保持自有三页：热点页负责发现和带入话题，创作页负责平台/内容类型/Skill 选择与输出，我的内容负责回看已有内容；复杂能力仍在后台接口可用，但不挡住首次创作。
- 旧数据/API 契约保留：原 `/api/v1/*` 路由挂到官方服务，旧数据库迁移和数据目录保持原配置；验收得到 `/api/v1/status` 与 `/api/v1/connectors` 返回 200。
- 账号、发布、日历和画像界面只保留公众号、小红书、抖音三个目标。热点来源仍可保留微博、知乎、B站等发现源，但不能进入目标账号卡片或发布选择器。
- 一键工作流一次启动六阶段：发现与核验、选题与结构、主稿、三平台适配、质量检查、归档交付。作业持久化到 `runtime/outputs/_workflow/`，状态可轮询，失败/服务重启可恢复，已完成阶段不重复执行；归档产物状态固定为 `draft`，不会代表已发布。
- 平台校验：小红书标题 20/正文 1000，抖音文案 55，公众号标题 64/正文 20000；公众号需要封面图片，抖音需要视频；发布始终沿用真实登录态和异步状态回执。
- 模型、研究、图片/视频、账号登录和真实发布未配置时，UI/API 显示 `NOT CONFIGURED` 或 `BLOCKED`，不生成模拟高质量文案、不伪造媒体、不声称发布成功。
- 前端恢复 `typecheck`、`test`、`build` 脚本，保留原单元测试。

## 证据

- 后端：`.venv312/bin/python -m pytest -q` → `33 passed`。
- 前端：`npm run typecheck` → 通过；`npm test -- --run` → `3 files / 4 tests passed`；`npm run build` → Vite 生产构建通过。
- 浏览器（ego-browser，本地 `http://127.0.0.1:5173`）：页面标题 `CreatorOS`；侧栏显示 CreatorOS 自有入口；工作流页面显示六阶段和三平台复选框；一次点击后在网关离线状态显示 `已阻断`，没有模拟产物；技能库、产物树、账号页和对话页均由 CreatorOS 自有页面承载，未配置能力显示 `BLOCKED`/“未登录”，没有自动重连或伪造回复。
- API：`GET /api/status` 200；`GET /api/accounts` 200 且只返回三平台；`GET /api/v1/status` 200；`GET /api/v1/connectors` 200；`POST /api/chat/stream` 在网关不可用时 503；越界路径、非目标平台、平台长度和排期目标均有错误回执。
- 文件安全：内容库跳过符号链接；输出和媒体路径限制在 `runtime/outputs/` 内；工作流作业 ID 限制为 12 位十六进制。

## 阻断与未宣称完成

- 当前环境没有可用模型/研究网关，六阶段在发现阶段阻断；没有真实研究、LLM 生成、图片/视频生成或质量检测证据。
- 三个平台没有登录态；没有调用扫码登录、短信验证、发布接口，也没有将草稿写入外部平台。
- 浏览器验收覆盖本地路由、主要页面、阻断和空状态；未进行外部平台登录、真机、真实发布或生产部署验收。
- 官方 Easel 的生产依赖、账号脚本和技能作为隔离 vendored 源保留；只对运行根目录、三平台集合、能力门禁和 CreatorOS 桥接做了窄改，后续官方升级应重新生成矩阵和文件指纹。
