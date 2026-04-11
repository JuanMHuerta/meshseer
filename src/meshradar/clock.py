from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def to_utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return to_utc_iso(utc_now())


def timestamp_to_utc_iso(timestamp: int | float | None, fallback: str | None = None) -> str:
    if timestamp is None:
        if fallback is None:
            fallback = utc_now_iso()
        return fallback
    return to_utc_iso(datetime.fromtimestamp(timestamp, tz=UTC))

