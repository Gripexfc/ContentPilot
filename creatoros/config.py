from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    host: str
    port: int
    frontend_origin: str
    wechat_adapter: str = "mock"
    wechat_profile_dir: Path | None = None

    @property
    def database_path(self) -> Path:
        return self.data_dir / "creatoros.sqlite3"

    @property
    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path}"

    @property
    def asset_dir(self) -> Path:
        return self.data_dir / "assets"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.asset_dir.mkdir(parents=True, exist_ok=True)

    def __post_init__(self) -> None:
        if self.wechat_profile_dir is None:
            object.__setattr__(self, "wechat_profile_dir", self.data_dir / "wechat-profile")


def load_settings() -> Settings:
    data_dir = Path(os.getenv("CREATOROS_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser()
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        host=os.getenv("CREATOROS_HOST", "127.0.0.1"),
        port=int(os.getenv("CREATOROS_PORT", "8000")),
        frontend_origin=os.getenv("CREATOROS_FRONTEND_ORIGIN", "http://127.0.0.1:5173"),
        wechat_adapter=os.getenv("CREATOROS_WECHAT_ADAPTER", "mock").strip().lower(),
        wechat_profile_dir=Path(os.getenv("CREATOROS_WECHAT_PROFILE_DIR", str(data_dir / "wechat-profile"))).expanduser(),
    )
