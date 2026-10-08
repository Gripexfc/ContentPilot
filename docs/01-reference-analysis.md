# 对照实现分析

日期：2026-09-29（Asia/Shanghai）。结论来自本轮本地静态审阅，未执行真实账号操作。

## 1. 参考快照与证据范围

| 项目 | 当前核查结果 |
| --- | --- |
| 路径 | `对照目录` |
| 分支 / HEAD | `main` / `0e9e9dd2880227802843c24c5cce2fe0ed4772fe` |
| 工作区 | 审阅开始时 `git status --short` 无变更 |
| Git 远端 | 未配置远端 |
| 跟踪文件 | 31 个 |
| 项目级许可证 | 当前文件树及可见 Git 历史中未发现 LICENSE / NOTICE |
| 运行验证 | 本轮未安装、构建、启动或运行参考项目测试 |

已完整阅读 README.md、PRODUCT.md、DESIGN.md、docs/MIGRATION_SCOPE.md、Python 包的领域模型/存储/API/配置/CLI/公众号适配器、两个测试文件，以及前端 App、API 客户端、入口、样式、Vite 和 TypeScript 配置。另解析了依赖清单及前端锁文件的包/许可证元数据。

未读取 `data/login/` 内容、浏览器会话、Cookie、密钥或账号原始数据。未读取或改动 `.easel`。

历史记忆中的三平台工作台与当前源码不一致，当前分析不沿用历史版本的功能、测试数量或许可证结论。

## 2. 当前产品实际边界

当前 README 和 PRODUCT 明确把第一版限定为微信公众号：本地文章、封面路径、管理员登录、草稿箱提交、基础数据读取入口。小红书、抖音、画像、热点和长期记忆均不在当前版本范围内。

DESIGN 把产品定义成安静的编辑室：文章占主要空间，旁侧显示下一步和账号状态。可借鉴的是“围绕创作任务组织界面、让状态和恢复动作可见”，不复制配色、CSS、组件、版式或品牌材料。

## 3. 结构与数据流

| 层 | 当前实现 | 可以提取的思路 |
| --- | --- | --- |
| 前端 | React + TypeScript + Vite；一个 App.tsx，少量 useState/useEffect | 使用类型化前端；文章与下一步放在同一工作上下文 |
| API | FastAPI，`baseline-module/api/app.py` 内集中定义 | 后端统一校验、前端通过 API 访问 |
| 领域 | Pydantic Draft / DraftCreate / AccountStatus | 平台状态与文章数据分别建模 |
| 存储 | 每篇草稿一个 JSON 文件，进程内线程锁 | 本地可持久化、可恢复；CreatorOS 改为事务型 SQLite |
| 外部平台 | WeChatAdapter 封装浏览器登录、后台请求、数据解析 | 平台细节放到适配器内；不能把此实现视作官方 API |
| 配置 | 环境变量指定 data 和浏览器 profile | 数据目录可以独立配置 |
| 测试 | 仓库 round-trip；API scope 断言 | 新项目从最小持久化用例起步，扩展行为和失败测试 |

实际流向为：表单 → API → JSON 草稿；显式按钮 → WeChatAdapter → 后台会话/请求。当前没有统一任务状态机、持久化作业队列或版本化产物。

## 4. 当前模型与 API 清单

`Draft`：id、title、digest、author、content_html、cover_path、status、created_at、updated_at、submitted_at、publish_error。状态为 `writing / ready / submitted / failed`。

`AccountStatus`：固定平台 wechat-oa、logged_in、nickname、message、checked_at。它无法完整表达“已配置、已连接、读取成功、提交成功、发布成功”的独立证据。

| 方法 | 路由 | 行为 |
| --- | --- | --- |
| GET | `/` | 有构建文件时返回前端，否则提示未构建 |
| GET | `/api/v1/status` | 项目版本及 wechat-oa 范围 |
| GET | `/api/v1/account` | 真实浏览器会话检查，并非纯本地状态查询 |
| POST | `/api/v1/account/login` | 启动后台登录线程 |
| GET | `/api/v1/account/login/status` | 读取登录状态文件 |
| GET / POST | `/api/v1/drafts` | 列表 / 新建本地草稿 |
| GET | `/api/v1/drafts/{id}` | 读取草稿 |
| POST | `/api/v1/drafts/{id}/publish` | 实际是提交草稿，未执行群发 |
| GET | `/api/v1/analytics` | 调用浏览器适配器读取后台数据 |

没有编辑已有草稿的 PATCH/PUT 接口；没有素材上传 API；没有画像、简报、三平台产物、编辑记录、记忆或导出 API。

## 5. 已确认的源码限制与 CreatorOS 对策

以下为静态结论，不是本轮运行复现，也不对参考项目作修复。

| 证据 | 观察 | CreatorOS 对策 |
| --- | --- | --- |
| `web/frontend/src/App.tsx:41–47`；`baseline-module/api/app.py` | 已有草稿保存分支只返回前端 active 对象，没有请求后端 | 每次保存生成持久化修订；成功后回读并展示 revision；刷新/重启验收 |
| `web/frontend/src/api.ts:19–32`；`web/frontend/vite.config.ts` | API 使用相对路径，Vite 仅设置端口，未配置 `/api` 代理 | 开发代理与生产同源服务都纳入烟测 |
| `App.tsx:55–61`；`integrations/wechat.py:start_login/whoami` | 登录线程启动后立即进行另一会话检查，缺少完整轮询交互 | 长操作返回 job_id；查询本地作业，不重复打开同一会话 |
| `integrations/wechat.py:_parse_stats` | 缺失字段常被转为 0；解析异常被忽略 | null、原生零值、解析失败分开；保留导入行和错误 |
| `api/app.py:79–94` | `/publish` 实为草稿提交；submitted_at 取的是更新前的时间 | `draft-submissions` 单独命名；事件发生时记录时间及回读证据 |
| `storage/repository.py:_write` | JSON 直接覆盖；锁只在进程内，没有事务与历史 | SQLite 事务、不可变版本、并发修订检查；资产原子落盘 |
| `api/app.py:24–25`；config.py | 导入模块即初始化仓库和适配器，并创建运行目录 | 应用工厂/lifespan；测试注入临时目录；读模型不触发外部动作 |
| `App.tsx:91–95,125` | 部分导航和“查看全部”没有页面行为 | 首个切片只暴露已可用入口，其余标明后续阶段 |
| `tests/test_api.py`、`tests/test_repository.py` | 仅 2 个基础测试；无前端或真实平台测试 | 建立领域、数据库/API、组件和端到端四层必要测试 |

静态资源路径经计算为正确的 `对照实现/web/frontend/dist`；不把它列为缺陷。存在真实浏览器调用代码不代表真实登录、草稿提交或统计读取已通过验收。

## 6. 产品差异清单

| 能力 | 对照实现 当前 | CreatorOS 目标 |
| --- | --- | --- |
| 中心对象 | 一篇公众号草稿 | 创作者画像 + 任务 + 证据 + 独立平台产物 |
| 画像 | 草稿 author 字段 | 版本、确认建议、差异、恢复、平台差异、真实经历与证据 |
| 输入 | 手工正文和封面路径 | 主题、链接、文本、文件、热点 |
| 任务 | 草稿粗粒度状态 | 七步业务进度 + 独立审核状态 + 作业状态 |
| 平台 | 公众号 | 公众号、小红书、抖音三个独立内容契约 |
| 事实 | HTML 内自由文本 | 来源快照、主张、核验事件、引用定位 |
| 生成 | 未实现 | 可替换 LLM；明确缺材料、失败、演示与真实生成边界 |
| 媒体 | 封面路径 | 图片适配器、卡片、字幕、脚本、分镜、可选渲染 |
| 热点 | 未实现 | 来源适配器、采集记录、热度证据、核验状态 |
| 分析 | 公众号实时读取入口 | 三平台导入、观察时间、口径、可解释比较与实验 |
| 沉淀 | 未实现 | 编辑/标题取舍/结构/失败 → 建议 → 用户确认 → 可撤销记忆 |
| 连接器 | logged_in 布尔值 | 配置、授权、读取、草稿提交、发布各有独立回执 |
| 持久化 | JSON 文件 | SQLite + 文件资产 + 可追踪修订 + 可恢复作业 |

## 7. 复用结论

复用产品思路：本地优先、编辑任务优先、明确下一步、平台适配器隔离、人工触发外部操作、失败可恢复。

独立设计与实现：数据模型、API、三平台结构、生成与溯源逻辑、所有源码和测试、视觉设计、模板和提示词。旧浏览器请求、接口参数、品牌、示例稿、样式和锁文件不迁入新项目。

许可证核查与依赖处理见[来源与许可证边界](04-provenance-and-licenses.md)。
