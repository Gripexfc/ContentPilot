# 分阶段交付与验收计划

每次只推进一个可验收的纵向切片；完成后记录实际文件、命令、测试、未验证外部行为和回滚方式，再开始下一切片。

## S1：需求分析与技术设计（本轮）

### 已完成

- 读取 ContentPilot README、PRODUCT、DESIGN、迁移范围、前后端目录、模型、API、测试、依赖与 Git 状态。
- 形成参考分析、产品定义、技术设计、数据/API 契约、许可证边界。
- 明确 CreatorOS 独立目录、分层、状态机、溯源、安全、平台与发布边界。

### 验收

- 文档能回答“借鉴什么、为什么不能复制、如何启动/测试/回滚、哪些外部行为尚未验证”。
- 不改 ContentPilot 或 `.easel`，不保存秘密，不声称任何运行时或平台成功。

### 当前证据与限制

- 修改文件见 `docs/05-phase-1-handoff.md`；验证仅为静态文件/依赖/Git 审阅。
- CreatorOS 当前无安装入口、数据库、前端、后端和测试。

## S2：可启动骨架 + 画像版本（已完成）

### 已交付

- Python package 与 `.venv` 安装入口、npm workspace 和 Vite API proxy。
- Alembic 初始迁移、SQLite WAL/外键/busy timeout 连接配置、可重复升级。
- FastAPI health/status、统一画像错误码、CORS 和静态前端入口。
- React 画像编辑界面、版本历史、差异查看和恢复操作。
- 画像快照包含身份、经历、领域、支柱、读者、语气、边界、三平台定位、目标和证据引用。

### 已验证场景

1. `make install`、`make db-upgrade`、后端启动和 Vite 启动均实际执行。
2. 创建一份包含身份、支柱、读者、语气、边界、三个平台定位和证据引用的画像。
3. 编辑并保存产生 version 2；API 返回 version 1/2 差异。
4. 恢复 version 1 产生 version 3，version 1/2 仍可读；临时 SQLite 数据库重启/重复迁移后仍可读取。
5. 过期基线返回 409；错误响应只含结构化 code/message，不含秘密。

### 验证结果

- 后端：6 个 pytest 用例通过。
- 前端：TypeScript typecheck、1 个 Vitest 用例、Vite production build 通过。
- HTTP smoke：status、创建 v1、创建 v2、diff、restore v3、当前版本查询通过。
- 外部模型/平台连接器未配置、未触发。

### 回滚

代码回滚到 S1 文档提交；临时数据目录可以废弃重建。数据库迁移只向前；如需回退使用开发库备份，不手工改用户库。

## S3：主题到三平台 + 待确认记忆（可运行返工版）

### 已交付

- 创建主题任务和 `idea → researching → briefed → drafting → adapted` 状态事件。
- 生成带画像版本、事实/来源空位、读者问题、作者角度和研究缺口的结构化简报。
- 离线 deterministic adapter 生成公众号、小红书、抖音三份独立结构化产物；各平台字段不同，不共享一份正文。
- 内容库读取任务、最新简报、当前产物版本和能力记忆来源链。
- 用户编辑创建新的 artifact revision 与 edit event，形成 `proposed` 能力记忆；用户确认后才变为 `confirmed`。
- 前端工作台可完成主题、简报、三平台生成、编辑和记忆确认。
- S3 原演示曾把追加固定句当成用户修改，且刷新后不能继续任务；2026-09-30 已改为真实字段编辑、乐观 revision 基线、内容库重开和 revision 差异查看，原结论“完整闭环已完成”撤回为“可运行返工版”。

### 已验证

- `CreatorOS/tests/test_api.py::test_content_vertical_slice_and_memory_confirmation` 和 `test_content_revisions_are_editable_and_status_is_explicit` 实际完成 profile → task → brief revision → confirm → three artifacts → library → real edit → revision history → reviewing/archive。
- 生成前未确认简报会返回结构化 409；三平台结构和内容不同；revision 2 保留 parent revision 与来源画像/简报 id。
- 前端 2 个 Vitest 用例、TypeScript typecheck、Vite production build 通过。

### 尚未实现与外部边界

- deterministic demo adapter 不代表 LLM 真实生成；真实模型密钥和调用待用户配置/明确触发，输出质量不以 smoke 证明。
- 当前主题输入只有文本入口；链接、图片、PDF、Markdown、Word、视频和热点选择在 S4/S5 处理。
- 事实来源和引用目前是空数组占位，尚未抓取或核验外部新闻；没有图片生成、卡片文件、视频渲染或发布接口。
- `adapted` 任务状态和本地保存不代表审核通过、草稿提交或发布成功。
- 当前模板编辑仍是结构化字段编辑器；没有富文本排版、图片渲染和真正的 LLM 生成，不应当标记为 final 或 ready。

### 回滚

任务/产物删除走软删除或清理测试库；适配器版本固定，历史 revision 不覆盖。

## S4：热点源和账号数据导入

拆为 S4a 热点手动/RSS/官方源、S4b CSV/JSON/截图人工录入、S4c 平台官方 API 只读连接。

验收重点：来源与抓取时间、事实/热度/读者证据分离；导入预检/映射/确认/逐行错误/去重；截图不自动变真实指标；无数据显示暂无数据。官方 API 的权限和字段必须以真实账号或模拟合同测试分别记录。

回滚：撤销一次 import 不删除原文件；作废 observation 和 analysis 快照。

## S5：图片、卡片、视频脚本与分镜导出

先实现图片提示词和 deterministic SVG/PNG 卡片，再接可替换图片服务；生成字幕/分镜/manifest，FFmpeg 只作为可选 media adapter，渲染失败保留脚本和错误。

验收：导出文件有 sha256、来源、适配器和状态；PNG/PDF/Markdown/JSON 读取验证；不能宣称视频发布。回滚：删除临时导出，保留源 revision。

## S6：分析、实验与长期能力库

加入结构性分析、真实指标趋势、实验记录、反馈、失败案例、记忆检索和依据面板。没有数据时不生成比例或增长率；单次样本不形成因果结论。

验收：导入真实/fixture 两类数据；结论带样本量和时间窗；接受/编辑/拒绝/撤销记忆的影响边界可观察；历史产物 trace 不变。回滚：分析/实验/记忆事件可撤销，原始指标和历史 revision 保留。

## 每个切片的交付模板

```text
修改文件：绝对路径 + 目的
模型/接口：新增或变更字段、状态和错误码
启动：实际执行过的命令与端口
测试：实际执行命令、通过/失败和证据
已完成：只列本切片验收通过项
尚未实现：下一切片或明确排除项
外部行为：未配置/未触发/未验证的账号、模型、平台、媒体能力
回滚：代码、数据、资产和迁移的可逆操作
```
