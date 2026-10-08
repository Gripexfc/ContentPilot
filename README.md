# CreatorOS

CreatorOS 是一个本地优先的内容创作工作台：从热点和主题开始，完成研究、写作、平台适配、质量检查和交付。

## 功能

- 热点发现、选题保存和素材导入
- 公众号、小红书、抖音三平台独立成稿
- 本地写作偏好、草稿版本和内容产物管理
- 工作流阶段进度、流式生成和调试日志
- 模型连接、平台连接和发布前状态检查

没有真实模型、研究源或平台账号时，界面会明确显示未配置、待核验或失败状态，不把模板内容标成真实生成或已发布。

## 启动

需要 Python 3.10+、Node.js 和可选的 FFmpeg。

```bash
make install
make db-upgrade
make backend       # 另一个终端运行 make frontend
```

默认 API 地址是 `http://127.0.0.1:8000`，前端开发服务地址是 `http://127.0.0.1:5173`。

数据默认保存在项目的 `data/`，可以通过 `CREATOROS_DATA_DIR` 和 `CREATOROS_ASSET_DIR` 指定隔离目录。运行时配置写入 `runtime/`，不会提交到 Git。

## 开发检查

```bash
make test
make lint
cd web/frontend
npm ci
npm run build
```

后端使用 FastAPI、SQLAlchemy 和 Alembic，前端使用 React、TypeScript 和 Vite。详细接口约定见 `docs/02-data-and-api.md`，产品边界见 `PRODUCT.md`，技术设计见 `DESIGN.md`。

## 数据与账号边界

密钥、Cookie、登录目录、数据库和生成产物都保留在本地运行目录，不写入仓库。平台登录、真实数据读取、草稿提交和发布均由用户主动触发，系统不会自动登录或群发。
