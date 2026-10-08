from __future__ import annotations

from alembic import command
from alembic.config import Config
from creatoros.config import Settings


def run_migrations(settings: Settings) -> None:
    config = Config(str(settings.project_root / "alembic.ini"))
    config.set_main_option("script_location", str(settings.project_root / "migrations"))
    config.set_main_option("prepend_sys_path", str(settings.project_root))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
