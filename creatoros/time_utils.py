from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def utc_iso(value: Optional[datetime]) -> Optional[str]:
    """Serialize database datetimes as explicit UTC ISO-8601 values.

    SQLite drops timezone metadata for DateTime columns. Treating a naive value
    as local time in one page and UTC in another caused the eight-hour drift
    seen in the draft center. All API timestamps now carry an explicit offset.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
