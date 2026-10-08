# S4a/S4b：热点线索与账号数据导入交付记录

日期：2026-09-30（Asia/Shanghai）。这一轮把“热点参考”和“账号数据”从未接入占位页变成可操作的本地闭环，范围仍然限定在用户主动输入和导入，不触发外部抓取、登录或发布。

## 已完成

- 热点池：手动保存标题、原始链接、来源名称、来源类型、摘要、热度信号、画像相关理由；每条默认 `unverified`、`needs_human_review=true`，原始链接作为未核验证据保存。
- 账号数据：选择公众号/小红书/抖音，上传或粘贴 CSV/JSON，保存导入批次、观察时间、来源、逐行指标和去重哈希。
- 结构性摘要：展示观察条数、导入批次、平台分布、内容支柱分布和分析限制；没有数据时显示“暂无数据”。不生成行业基准、增长率或成功结论。
- 页面：热点与新闻、账号分析不再显示“待实现”占位；导航明确标出“手动可用”“导入可用”。

## 数据模型和接口

迁移 `migrations/versions/0003_sources_metrics.py` 新增 `hotspots`、`hotspot_evidence`、`metric_imports`、`metric_observations`。

- `POST/GET /api/v1/hotspots`
- `POST/GET /api/v1/metrics/imports`
- `GET /api/v1/metrics/summary`

前端入口为 `web/frontend/src/Pages.tsx`，客户端契约在 `web/frontend/src/api.ts`；服务逻辑在 `creatoros/services/ops_service.py`。

## 启动与测试

```bash
cd CreatorOS
make db-upgrade
make backend       # 另一个终端运行 make frontend
make test
make lint
```

本轮实际结果：当时后端 `9 passed`；前端 `2 passed`；TypeScript typecheck 通过；Vite build 通过；`make lint` 通过。输入资产、热点入任务和文本导出在后续 S4c 记录，见 `docs/10-git-parity-audit.md`。

## 未完成和不能验证的行为

- 未接入 RSS、BetterOPC、政府/监管/企业公告自动采集；未验证任何外部源的真实抓取、发布时间、热度信号或反爬行为。
- 当前前端解析支持引号字段和逗号；平台专有导出格式仍需列映射模块。
- 未接入平台官方 API、后台截图 OCR、图片生成、卡片图片导出、真实 LLM、FFmpeg 或发布能力；文章、脚本和分镜已有 Markdown/JSON/HTML 文本导出。
- 指标摘要只做导入数据的计数和分布，不能代表账号增长、行业基准或因果关系。

## 回滚方式

停止本地服务后，删除或迁移 `CreatorOS/data/creatoros.sqlite3` 到备份目录，再从旧版本启动；代码回滚到 0003 时需同时执行 Alembic downgrade `0004_input_metadata`，不能只删除字段。测试使用临时 SQLite，不会写入默认数据目录。

没有修改 `对照目录` 或 `.easel`，没有引入第三方源码、密钥、Cookie、二维码、令牌或外部账号数据。
