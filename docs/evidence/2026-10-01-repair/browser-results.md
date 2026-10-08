# CreatorOS 修复浏览器验收记录

日期：2026-10-01（Asia/Shanghai）  
浏览器：Ego Lite TaskSpace 2（沿用既有空间；p1=ContentPilot，p2=CreatorOS）  
CreatorOS：`http://127.0.0.1:18310`  
数据：`/private/tmp/creatoros-ui-20261001-repair`（隔离目录，未触碰 CreatorOS/data）

## 复现与结果

1. **主题→简报→三平台→本地草稿**：保存画像“QA 修复作者”，创建“修复验收流程一致性”，输入 `QA-REPAIR-2026-10-01`，生成并确认简报、创建三平台模板，从当前公众号 revision 创建本地草稿。页面显示来源任务/产物/revision。
2. **时间与标题**：草稿 API 返回 `created_at=2026-10-01T02:00:09.213604+00:00`、`updated_at=2026-10-01T02:02:07.653634+00:00`；页面显示 `2026/10/1 10:00:09`、`2026/10/1 10:02:07`。路由页签依次显示 `CreatorOS · 内容工作台`、`CreatorOS · 公众号草稿中心`、`CreatorOS · 账号分析`。
3. **无效/有效封面**：选择 `cover-invalid.txt`，页面即时显示“封面必须是 PNG、JPEG 或 WebP 图片”；选择隔离 PNG 后显示“封面已保存”，标题和正文未被覆盖。
4. **未连接提交（B1）**：直接点击“模拟提交失败”时页面即时显示“请先连接并读取账号”和“去设置与连接器”；草稿列表/编辑器同时变为“失败”，提交记录从 2 变为 3。API 事件为 `submit: writing→failed, success=false`。
5. **Mock 连接恢复**：设置页对微信公众号依次点击“配置本地 Mock”→“连接”→“读取账号”，状态显示“读取成功”；“模拟失败”后显示“失败 / Mock Connector 模拟提交失败，可重试”，再点“重试提交”显示“提交成功”。
6. **草稿重试**：返回草稿中心点击“重试提交”，页面显示“Mock 提交成功已记录，状态只是本地适配器回执”，状态变为“已提交”，事件数为 4。未调用真实微信。
7. **B2**：无效封面后不残留“封面已保存”；提交失败时旧成功提示会被清掉，当前页面只有与当前操作对应的错误/状态。
8. **B5 跨任务记忆**：用浏览器同源 API 建立三次同输入任务。第一次编辑公众号并生成待确认 memory，采纳后第二任务的 `revision.memory_ids=["3badbfff-e364-4d8c-951f-f8abb48afd69"]`、`memory_guidance=["公众号开头保留真实现场"]`；撤销后第三任务 `memory_ids=[]`。拒绝/撤销不进入后续生成。
9. **A3 入口**：分析页有“读取公众号后台数据”按钮；在 Mock 模式点击后显示“真实公众号数据读取未启用；当前可使用 CSV/JSON 主动导入”，没有把 Mock 或导入显示成真实后台数据。
10. **视口**：390、1024、1440 均完成截图复核；本目录 `screens/` 保存实际 PNG。

## 证据文件

- `pre-change-sha256.txt`：修改前 CreatorOS 源码/测试/报告清单。
- `screens/draft-failed-1440.png`：提交失败即时状态、错误入口和失败事件。
- `screens/draft-submitted-1440.png`：Mock 重试后已提交状态。
- `screens/settings-1440.png`：连接器状态页及本地/真实边界文案。
- `screens/analytics-390.png`、`screens/analytics-1024.png`：账号分析入口在窄屏/中屏的显示。
- `18-acceptance-report.before.md`、`19-handoff.before.md`：本轮修改前报告/交接单快照。

## 外部边界

本轮没有启动真实 browser adapter、没有扫码/验证码、没有调用公众号真实上传或草稿写入，也没有发布/群发。`CREATOROS_WECHAT_ADAPTER=browser` 的依赖检查、会话状态和适配器隔离测试已完成；真实账号现场验收留待用户提供授权和登录动作。
