from __future__ import annotations

import json
import logging
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from meshseer.clock import utc_now_iso


LOGGER_NAME = "meshseer.audit"
_logger = logging.getLogger(LOGGER_NAME)
_logger.setLevel(logging.INFO)


def audit_log(event: str, **fields: Any) -> None:
    payload = {
        "ts": utc_now_iso(),
        "event": event,
        **fields,
    }
    _logger.info(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def request_source(headers: Mapping[str, str], client_host: str | None) -> str:
    forwarded_for = headers.get("x-forwarded-for", "")
    if forwarded_for:
        source = forwarded_for.split(",", 1)[0].strip()
        if source:
            return source

    real_ip = headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip

    if client_host:
        return client_host

    return "unknown"


@dataclass
class FailedAccessTracker:
    threshold: int = 5
    window: timedelta = timedelta(minutes=10)

    def __post_init__(self) -> None:
        self._attempts: dict[tuple[str, str], deque[datetime]] = {}
        self._last_alerted_at: dict[tuple[str, str], datetime] = {}
        self._lock = threading.Lock()

    def record(self, *, source: str, path: str, now: datetime | None = None) -> dict[str, Any]:
        current = datetime.now(tz=UTC) if now is None else now.astimezone(UTC)
        key = (source, path)
        cutoff = current - self.window

        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            while attempts and attempts[0] < cutoff:
                attempts.popleft()
            attempts.append(current)

            repeated = False
            count = len(attempts)
            last_alerted_at = self._last_alerted_at.get(key)
            if count >= self.threshold and (last_alerted_at is None or last_alerted_at < cutoff):
                self._last_alerted_at[key] = current
                repeated = True

            stale_keys = [candidate for candidate, values in self._attempts.items() if not values or values[-1] < cutoff]
            for stale_key in stale_keys:
                self._attempts.pop(stale_key, None)
                self._last_alerted_at.pop(stale_key, None)

        return {
            "count": count,
            "repeated": repeated,
            "window_seconds": int(self.window.total_seconds()),
        }
