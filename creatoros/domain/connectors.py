from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


ConnectorStateName = Literal[
    "not_configured", "configured", "connecting", "connected", "read_succeeded",
    "submit_succeeded", "publish_succeeded", "failed", "unsupported", "expired",
]


class ConnectorRead(BaseModel):
    id: str
    connector_key: str
    platform: str
    label: str
    adapter_kind: str
    state: ConnectorStateName
    last_operation: Optional[str]
    last_error_code: Optional[str]
    last_error: Optional[str]
    updated_at: str


class ConnectorAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulate_failure: bool = False
