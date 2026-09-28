# 随波逐流

一个属于创作者的本地内容工作台。围绕真实的软件工程、AI 工具和个人项目，从选题研究到成稿、平台适配和复盘，把内容和经验留在自己的机器上。

<img src="web/static/suibo-icon.svg" width="96" alt="随波逐流">

## 工作流

研究与核查 → 选题与结构 → 创作 → 独立平台改编 → 质量检查 → 归档交付。

“一键工作流”可以输入主题，选择公众号、掘金和小红书，依次执行六个阶段。当前任务状态保存在服务进程中，刷新页面可查看运行状态；服务重启后应查看内容文件，尚未实现自动恢复任务。每个阶段能否完成取决于素材、模型和工具的实际可用性。

## 工作台能力

- 对话：多轮会话、附件、流式回复和中止操作。
- 账号画像：定位、受众、风格、平台、偏好和独立长期记忆。
- 发现与策划：热点雷达、选题库、竞品拆解和内容日历。
- 技能库：研究、写作、图文卡片、音频、视频、平台适配和数据分析。
- 内容库：项目文件、成品预览、素材浏览和归档。
- 发布中心：格式适配、附件、预览、账号状态与平台发布准备。
- 设置：模型配置、运行环境和依赖检查。

账号页展示小红书、抖音、微信公众号和掘金。其它平台的底层技能仍保留。掘金负责技术内容适配和本地成稿，当前没有自动登录或自动发布。微信公众号创建草稿需明确授权，并通过项目发布包门禁。真实账号登录和发布须单独验收。

## 安装与启动

需要 Python 3.10+、Git、Node.js 22.19+ 和 FFmpeg。安装器准备虚拟环境、前端依赖、OpenClaw 和 Playwright Chromium。

```bash
bash setup.sh
source .venv/bin/activate
easel doctor
easel ping
easel web
```

Windows 使用 PowerShell 执行 `setup.ps1`。工作台默认地址为 http://localhost:7860，网关为 http://localhost:18789。

安装可使用已有的 OpenClaw 模型认证；有 API 配置时按 `.env.example` 设置。图片、视频和音乐等额外生成服务需要各自可用的配置。不要提交个人凭证、Cookie、登录目录或账号内容。

## 兼容性

本版本继续兼容现有 `easel` 命令、Python 模块、`EASEL_*` 环境变量、`.easel.json` 项目元数据、浏览器存储键和隔离的 OpenClaw profile。保留这些内部标识是为了延续现有安装、会话和内容数据。对外产品名称统一为“随波逐流”。

## 内容与平台

每个平台独立成稿。技术教程和工程实践默认面向掘金；公众号强调读者收益和实际证据；小红书使用自己的笔记与卡片结构。项目内使用 Asia/Shanghai 日期归档。原始事实可共享，标题、开头、结构和最终文案分别编写。

## 开发

前端：React + TypeScript + Vite。后端：FastAPI。Agent 运行：OpenClaw。

```bash
cd web/frontend
npm ci
npm run build
cd ../..
python scripts/validate_skills.py
python scripts/validate_skill_commands.py
python -m pytest tests -q
```

详细能力见 [能力地图](docs/skill-function-mapping.md)，接口见 [技能规范](docs/SKILL-SPEC.md)，运行架构见 [提示词分层](docs/prompt-stack.md)。

## 开源与来源

本版本包含界面、产品文案和平台适配修改。许可证与来源通知见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。部分内置组件使用独立许可证，须遵循各组件原有许可；发布前请按组件目录中的许可文件核对使用范围。
