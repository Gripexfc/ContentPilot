# ContentPilot 严格功能对齐记录

日期：2026-10-01（Asia/Shanghai）

本轮按 `/Users/fc/Desktop/随波逐流/ContentPilot` 作为唯一产品基准，收缩 CreatorOS 的默认可见功能范围。目标是复现原项目的单页公众号编辑台，而不是继续扩展为多平台内容运营系统。

## 已对齐

- 前端单页入口、侧栏文案、编辑区字段、进度提示、账号卡片、下一步清单、最近草稿和说明区与参考项目逐字一致。
- 保留公众号草稿的标题、摘要、作者、正文 HTML、封面路径、状态和错误提示。
- 补齐参考项目使用的账号状态、登录启动、登录状态、草稿列表/创建、明确提交和基础数据接口路径。
- 兼容接口的登录、草稿提交和数据读取直接走真实 `WeChatBrowserAdapter`；Mock 状态不会被转换成真实成功。
- 三平台、个人画像、热点、能力记忆和扩展分析入口从默认界面移除，但既有后端接口仍保留，避免破坏已有数据和测试。

## 证据与边界

- `web/frontend/src/App.tsx`、`api.ts`、`styles.css`、`index.html` 与参考项目对应文件逐字校验一致。
- CreatorOS 前端 typecheck、production build 和后端测试通过。
- 真实公众号登录、封面上传、草稿写入和后台数据读取仍需要 Playwright、管理员扫码和公众号后台会话；本轮没有伪造外部成功。
- 真实 LLM、研究采集、图片/视频生成和质量门禁不属于参考项目能力，也没有被标记为已实现。

修改前文件备份位于 `/private/tmp/creatoros-before-contentpilot-restore-20261001/`。
