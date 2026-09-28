# Suibo · 随波逐流

A local content workbench for real engineering stories, AI tools and personal projects.

Research → planning → creation → independent platform adaptation → quality review → delivery.

The workbench includes chat, account profiles, trends, topic storage, calendars, skills, content previews, publishing preparation and analytics. The one-click workflow targets WeChat articles, Juejin technical articles and Xiaohongshu notes. Juejin currently uses manual publishing.

## Start

```bash
bash setup.sh
source .venv/bin/activate
easel doctor
easel ping
easel web
```

Open http://localhost:7860. Windows users can run `setup.ps1`.

The existing CLI, Python modules, environment variables, storage keys and OpenClaw profile remain compatible. Workflow status currently lives in the server process; generated files survive a restart, but automatic job recovery is not implemented.

See the [Chinese guide](README.md) for setup and development. Licenses and required source notices are recorded in [LICENSE](LICENSE) and [NOTICE](NOTICE). Bundled components retain their own licenses. This customized version does not claim original authorship of upstream code.
