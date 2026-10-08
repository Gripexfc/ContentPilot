> 2026-10-01 能力迁移版：默认入口是 CreatorOS 自有页面，官方 Easel 仅作为 `vendor/easel/` 下的只读参考。运行使用 Python 3.12 的 `.venv312`：`make backend`（8000）和 `make frontend`（5173）。官方运行数据、账号会话和配置仅写入隔离的 `runtime/`，不会复用 `.easel` 的登录状态。差异矩阵见 `docs/22-easel-official-parity-matrix.md`，验收结果见 `docs/23-easel-parity-validation.md`。

# CreatorOS

面向个人内容创作者的本地优先内容操作系统。

**当前阶段：参考 [ZJU-REAL/Easel](https://github.com/ZJU-REAL/Easel)，把产品收缩成一条易上手的创作链路：看热点 → 选感兴趣的话题 → 选择平台和内容类型 → 调用对应 Skill/Agent 输出文章或配图。默认入口只保留“看热点 / 开始创作 / 我的内容”三页；公众号、小红书、抖音由平台选择决定结构和风格。真实 LLM、图片/视频生成与外部平台发布仍按真实连接状态显示，不会把本地模板标成高质量成稿或“越用越强”。**

项目位置：`/Users/fc/Desktop/随波逐流/CreatorOS`。本目录与 ContentPilot、`.easel` 独立。S1 只新增设计文档，S2 新增了自己的骨架和测试；没有复制参考项目代码、提示词、素材、用户数据或凭据。

## 阅读顺序

1. [Easel 三平台界面恢复记录](docs/21-easel-three-platform-ui-restore.md)：当前界面与官方 Easel 主链路、三平台白名单和真实能力边界。
2. [参考项目分析与差异](docs/01-reference-analysis.md)：当前源码实际有什么、哪些思路可以借鉴、哪些问题不应沿用。
3. [产品定义与边界](PRODUCT.md)：用户任务、三平台交付物、质量与操作边界、需求验收映射。
4. [技术与交互设计](DESIGN.md)：架构、页面、状态机、适配器、恢复与安全。
5. [数据模型与接口契约](docs/02-data-and-api.md)：分阶段模型、版本/溯源关系、接口和失败语义。
6. [切片实施与测试计划](docs/03-delivery-plan.md)：按指定六步推进，每次只实现一个可验收切片。
7. [许可证与来源边界](docs/04-provenance-and-licenses.md)：当前参考仓库的许可证核查结果与后续依赖登记规则。
8. [本阶段交付记录](docs/05-phase-1-handoff.md)：文件清单、检查结果、限制和回滚。
9. [S3 垂直切片交付记录](docs/07-s3-handoff.md)：主题、简报、三平台草稿、用户修改和能力记忆。
10. [S3 可用性返工记录](docs/08-usability-rework.md)：为什么原演示不满足验收，以及本次返工边界。
11. [S4a/S4b 交付记录](docs/09-s4-ops-handoff.md)：手动热点池、CSV/JSON 账号导入、结构性分析和边界。
12. [Git 基线功能核对](docs/10-git-parity-audit.md)：参考项目实际能力、本轮补齐、验收证据和未实现边界。
13. [功能差异矩阵](docs/11-feature-parity-matrix.md)：参考能力、CreatorOS 扩展、连接器状态和外部限制。
14. [视觉重设计与原型](docs/12-design-system-and-prototype.md)：SaaS token、信息架构、路由和可运行原型。
15. [公众号草稿中心切片](docs/13-slice-2-draft-center-handoff.md)：封面、提交事件、失败重试和回滚。
16. [第一阶段体验审计](docs/14-experience-audit.md)：只读核对现有页面、API、模型、测试和外部边界。
17. [全功能差异矩阵](docs/15-full-feature-parity.md)：ContentPilot 能力、文章生成项、Skills 映射和第二阶段入口。
18. [UX 重构记录](docs/16-ux-redesign.md)：总览恢复快照、输入自动保存和状态设计。
19. [文章生成系统](docs/17-generation-system.md)：当前模板边界、三平台字段和后续适配器契约。
20. [当前验收报告](docs/18-acceptance-report.md)：修改文件、测试、外部限制、回滚清单和下一条切片。

## 预期核心流程

发现热点或输入主题 → 确认选题与研究简报 → 创建公众号/小红书/抖音三份平台草稿 → 分平台编辑与质量检查 → 进入发布中心预览 → 用户明确连接账号后执行对应平台动作 → 回看可用的数据与修改记录。未接入真实模型、研究源或平台账号时，界面只显示本地模板、待核验或未连接状态。

内容库保存不等于审核通过，审核通过不等于草稿提交，草稿提交不等于发布。默认没有自动发布、自动群发或自动登录。

## 当前如何启动与测试

```bash
cd /Users/fc/Desktop/随波逐流/CreatorOS
make install
make db-upgrade
make backend       # 另一个终端运行 make frontend
```

API 默认在 `http://127.0.0.1:8000`，前端默认在 `http://127.0.0.1:5173`。数据默认写入 `CreatorOS/data/`；可通过 `CREATOROS_DATA_DIR` 指向独立目录。

```bash
make test
make lint
```

S2/S3/S4a/S4b/S4c 的安装、迁移幂等、画像版本/差异/恢复、简报版本、内容修订冲突、平台编辑、内容库回读、热点/指标 API、输入资产、热点入任务、导出、前端类型检查、前端单元测试、生产构建和 API 测试已经实际执行。当前生成仍使用离线模板适配器，不代表接入真实模型或发布平台。

公众号真实适配器是显式选择的可选能力：设置 `CREATOROS_WECHAT_ADAPTER=browser` 后安装 `pip install -e '.[dev,wechat]'`，登录会话保存在本地 `CREATOROS_WECHAT_PROFILE_DIR`，不写入数据库或日志。扫码、登录过期恢复、封面上传、草稿提交和账号读取均由用户点击触发；Mock 状态和 CSV/JSON 导入不会被标为真实成功。

## 下一次开发范围

已完成本轮 S4c 的本地输入、网页链接、公开热榜、热点入任务、文件资产保存和产物导出；RSS 与更多官方源仍可继续扩展。

完整内容生产闭环在 S3；本地输入、公开热榜、热点入任务和导出在 S4c；手动热点与 CSV/JSON 导入在 S4a/S4b；RSS、真实媒体生成、实验和记忆增强仍待后续阶段。详见[实施计划](docs/03-delivery-plan.md)。

## 本地数据与授权

未来默认使用 `CreatorOS/data/creatoros.sqlite3` 和 `CreatorOS/data/assets/`，支持配置独立数据目录。内容资产默认只写入此项目；导出到其它目录必须由用户主动选择。

密钥只通过系统凭据存储或进程内输入使用；仓库、应用日志、生成文本、导出包不保存凭据。没有模型配置时明确显示未配置；演示数据和测试替身不冒充真实生成或账号表现。

## 许可证状态

本轮没有引入第三方源码，也没有给参考项目补设或更换许可证。当前 ContentPilot 仓库未找到项目级 LICENSE/NOTICE，因此不以其源码为复制模板。CreatorOS 的对外分发许可在正式分发前确定；当前文档不构成对参考项目再许可。
