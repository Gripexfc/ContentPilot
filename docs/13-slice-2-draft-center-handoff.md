# S2 公众号草稿中心切片交付记录

日期：2026-10-01（Asia/Shanghai）

## 已交付

* `wechat_drafts`、`wechat_draft_events` SQLite 表与 `0006_wechat_drafts`、`0007_draft_sources` 迁移。
* 草稿字段：标题、摘要、作者、正文 HTML、封面路径、状态、提交时间、错误原因。
* 草稿来源字段：`source_task_id`、`source_artifact_id`、`source_revision_id`；从已保存公众号当前版本转入时幂等。
* API：`GET/POST /api/v1/drafts`、`GET/PATCH /api/v1/drafts/{id}`、`POST /api/v1/artifacts/{id}/draft`、复制、封面上传/读取、`POST /submit`。
* React 公众号草稿中心：列表、脏状态保护、编辑、sandbox iframe + CSP 预览、封面预览、事件记录、失败重试和已提交复制。
* 提交动作与 `wechat-oa` Mock Connector 读取状态绑定；未完成配置/连接/读取时不允许提交。

## 验收证据

隔离数据目录：`/tmp/creatoros-slice-20260930`。

1. 浏览器创建草稿“把一次失败复盘写成可执行方法”，正文 HTML 保存并回读。
2. 上传本地 PNG 封面，预览显示并在 SQLite 关联路径保存。
3. Mock 微信连接器完成配置、连接、读取。
4. 草稿“模拟提交失败”后状态为 `failed`，错误文案为“Mock Connector 模拟提交失败，可重试”。
5. “重试提交”后状态为 `submitted`，提交事件保留失败与成功两次记录。
6. 截图：`docs/evidence/2026-09-30/draft-center-empty.png`、`draft-center-submitted.png`。

本轮补充验收：公众号产物当前 revision 转入草稿后保存来源三元组；封面上传不重置未保存正文；已提交草稿编辑和换封面均被拒绝；刷新与导航有脏状态保护；预览 iframe 无脚本、外部资源、表单提交或同源权限。

## 测试

* 后端：覆盖迁移升级、真实 PNG 校验、无效/缺失封面、来源幂等、提交门禁、失败重试和已提交不可变。
* 前端：草稿脏状态/预览隔离纯函数回归；TypeScript typecheck 和 Vite production build 通过。

## 未实现与限制

草稿提交当前只调用本地 Mock Connector；不会打开微信后台、上传真实封面、写入公众号草稿箱或发布。真实适配器下一切片仍缺：用户点击后的授权/扫码入口、凭据安全存储、账号读取 API、草稿写接口、封面上传接口、平台错误映射和真实回执回读。授权与写接口授权必须分开。HTML 预览已隔离，但真实平台 HTML 规则和白名单清洗仍需另行实现。

## 回滚

本轮修改前快照保存在 `/tmp/creatoros-pre-draft-center-20260930`（不含数据、凭据和依赖）。代码回退时可恢复该快照，或将 Alembic 回退到 `0006_wechat_drafts` 并移除 `0007_draft_sources`、来源转入路由和前端入口；隔离验收目录可直接删除。对照实现 与 `.easel` 未修改。
