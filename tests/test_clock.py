from datetime import UTC, datetime

from meshseer.clock import timestamp_to_utc_iso, to_utc_iso, utc_now_iso


def test_to_utc_iso_normalizes_timezone():
    value = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)

    assert to_utc_iso(value) == "2026-03-30T12:00:00Z"


def test_timestamp_to_utc_iso_uses_fallback():
    assert timestamp_to_utc_iso(None, fallback="2026-03-30T12:00:00Z") == "2026-03-30T12:00:00Z"
    assert utc_now_iso().endswith("Z")

