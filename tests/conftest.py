from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from creatoros.api.app import create_app
from creatoros.config import Settings


@pytest.fixture()
def app_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=Path(__file__).resolve().parents[1],
        data_dir=tmp_path / "data",
        host="127.0.0.1",
        port=0,
        frontend_origin="http://127.0.0.1:5173",
    )


@pytest.fixture()
def client(app_settings: Settings) -> Iterator[TestClient]:
    app = create_app(app_settings)
    with TestClient(app) as test_client:
        yield test_client
