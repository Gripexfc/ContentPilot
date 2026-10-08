from __future__ import annotations

import argparse

import uvicorn

from creatoros.config import load_settings
from creatoros.db.migrations import run_migrations


def main() -> None:
    parser = argparse.ArgumentParser(prog="creatoros")
    subcommands = parser.add_subparsers(dest="command")
    web = subcommands.add_parser("web", help="启动 CreatorOS API 服务")
    web.add_argument("--host", default=None)
    web.add_argument("--port", type=int, default=None)
    db = subcommands.add_parser("db", help="管理本地数据库")
    db.add_argument("action", choices=["upgrade"])
    args = parser.parse_args()
    settings = load_settings()
    if args.command == "web":
        uvicorn.run(
            "creatoros.api.app:app",
            host=args.host or settings.host,
            port=args.port or settings.port,
            reload=False,
        )
        return
    if args.command == "db" and args.action == "upgrade":
        run_migrations(settings)
        print(f"数据库已升级：{settings.database_path}")
        return
    parser.print_help()
