# CreatorOS SaaS 视觉重设计与可运行原型

日期：2026-09-30  
范围：第一切片（控制台 shell、状态表达、连接器状态）

## 信息架构

侧栏固定九个入口：总览、个人画像、内容工作台、内容库、公众号草稿中心、能力记忆、热点与新闻、账号分析、设置与连接器。主区根据 hash 路由加载真实 React 页面；页面的数据来自 `/api/v1`，没有静态演示数据兜底。

## 用户流程

```text
总览 → 个人画像 → 内容工作台 → 简报 → 三平台产物 → 内容库
  │         │                           └→ 能力记忆
  ├→ 热点与新闻 → 以此创建内容任务
  ├→ 账号分析（CSV/JSON 导入）
  ├→ 已保存公众号产物 → 保存为本地草稿 → 预览/封面 → Mock 提交/重试
  └→ 设置与连接器 → 配置 Mock → 连接 → 读取 → 模拟提交/失败 → 重试
```

## 设计 Token

| Token | 值 | 用途 |
| --- | --- | --- |
| Base | `#080d18` | 深色海军蓝背景 |
| Surface | `#101827` / `#141e30` | 工作区、卡片、编辑器 |
| Accent | `#9b8cff` / `#4cd9e8` | 电光紫、青色交互强调 |
| Positive | `#55d6a2` | 在线、成功、已读取 |
| Warning | `#f5bf63` | 待核验、空数据限制 |
| Danger | `#ff7589` | 失败、离线、可重试 |
| Radius | `12px` / `16px` | 控件与主要容器 |
| Motion | `180ms ease` | hover、焦点、状态反馈 |
| Type | Inter + Manrope + 系统中文 | 控件、数字与标题 |

所有状态均有文字标签；颜色只做辅助。焦点使用 2px 青色外轮廓，窄屏侧栏收缩为图标栏，编辑器按证据→简报→产物→审核顺序继续访问。

## 组件清单

`RailNav`（内联 SVG 图标）、`PageHeader`、`Message`、`Empty`、`StatusPill`、`MetricCard`、`TaskLine`、`ConnectorCard`、`PlatformTabs`、`ArtifactCard`、`HistoryList`。空数据、错误、离线、未连接、模拟数据和成功状态均有对应文案。

## 路由与 API 映射

| 页面 | 路由 | 真实接口 |
| --- | --- | --- |
| 总览 | `#/overview` | `/status`、`/profile`、`/tasks`、`/memories` |
| 个人画像 | `#/profile` | `/profile/*` |
| 内容工作台 | `#/workspace/:taskId` | `/tasks/*`、`/artifacts/*`、`/memories/*` |
| 内容库 | `#/library` | `/tasks`、`/tasks/:id` |
| 热点与新闻 | `#/hotspots` | `/hotspots`、`/hotspots/:id/task` |
| 账号分析 | `#/analytics` | `/metrics/imports`、`/metrics/summary` |
| 设置与连接器 | `#/settings` | `/connectors`、`/connectors/:key/{configure,connect,read,submit}` |
| 公众号草稿中心 | `#/drafts/:draftId?` | `/drafts`、`/artifacts/:id/draft`、`/drafts/:id`、`/drafts/:id/cover`、`/drafts/:id/submit` |

## 可运行原型与验收证据

原型就是 `web/frontend` 的 Vite 应用，后端会在构建产物存在时从同一服务提供入口。第一切片已在隔离数据目录启动后端，并通过 API 与浏览器检查：导航可达、热点/分析不再显示 FuturePage 占位、设置页能读取三个 Mock Connector，状态动作会持久化到 SQLite。

真实公众号扫码、封面上传到微信后台、草稿提交、账号读取和发布仍显示为未配置/不支持；Mock 提交成功只证明本地状态机，不是外部平台成功。草稿预览使用无脚本、无同源权限的 sandbox iframe 和 CSP，不能替代后续真实富文本清洗策略。
