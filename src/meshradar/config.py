from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_stripped(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _optional_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def _positive_int(value: str | None, *, default: int, name: str) -> int:
    parsed = default if value is None or value == "" else int(value)
    if parsed < 1:
        raise ValueError(f"{name} must be >= 1")
    return parsed


def _positive_float(value: str | None, *, default: float, name: str) -> float:
    parsed = default if value is None or value == "" else float(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be > 0")
    return parsed


def _environment(value: str | None) -> str:
    if value is None or value == "":
        return "development"

    normalized = value.strip().lower()
    if normalized in {"development", "dev"}:
        return "development"
    if normalized in {"production", "prod"}:
        return "production"
    raise ValueError("MESHRADAR_ENV must be one of: development, dev, production, prod")


@dataclass(frozen=True)
class Settings:
    environment: str
    meshtastic_host: str
    meshtastic_port: int
    bind_host: str
    bind_port: int
    db_path: Path
    local_node_num: int | None
    admin_bearer_token: str | None
    autotrace_enabled: bool
    autotrace_interval_seconds: int
    autotrace_target_window_hours: int
    autotrace_cooldown_hours: int
    autotrace_ack_only_cooldown_hours: int
    autotrace_response_timeout_seconds: int
    ws_max_connections: int
    ws_queue_size: int
    ws_send_timeout_seconds: float
    ws_ping_interval_seconds: float
    ws_ping_timeout_seconds: float

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env
        return cls(
            environment=_environment(values.get("MESHRADAR_ENV")),
            meshtastic_host=values.get("MESHRADAR_MESHTASTIC_HOST", "10.10.99.253"),
            meshtastic_port=int(values.get("MESHRADAR_MESHTASTIC_PORT", "4403")),
            bind_host=values.get("MESHRADAR_BIND_HOST", "0.0.0.0"),
            bind_port=int(values.get("MESHRADAR_BIND_PORT", "8000")),
            db_path=Path(values.get("MESHRADAR_DB_PATH", "./data/meshradar.db")),
            local_node_num=_optional_int(values.get("MESHRADAR_LOCAL_NODE_NUM")),
            admin_bearer_token=_optional_stripped(values.get("MESHRADAR_ADMIN_BEARER_TOKEN")),
            autotrace_enabled=_optional_bool(values.get("MESHRADAR_AUTOTRACE_ENABLED")),
            autotrace_interval_seconds=int(values.get("MESHRADAR_AUTOTRACE_INTERVAL_SECONDS", "300")),
            autotrace_target_window_hours=int(values.get("MESHRADAR_AUTOTRACE_TARGET_WINDOW_HOURS", "24")),
            autotrace_cooldown_hours=int(values.get("MESHRADAR_AUTOTRACE_COOLDOWN_HOURS", "24")),
            autotrace_ack_only_cooldown_hours=int(
                values.get("MESHRADAR_AUTOTRACE_ACK_ONLY_COOLDOWN_HOURS", "6")
            ),
            autotrace_response_timeout_seconds=int(
                values.get("MESHRADAR_AUTOTRACE_RESPONSE_TIMEOUT_SECONDS", "20")
            ),
            ws_max_connections=_positive_int(
                values.get("MESHRADAR_WS_MAX_CONNECTIONS"),
                default=32,
                name="MESHRADAR_WS_MAX_CONNECTIONS",
            ),
            ws_queue_size=_positive_int(
                values.get("MESHRADAR_WS_QUEUE_SIZE"),
                default=32,
                name="MESHRADAR_WS_QUEUE_SIZE",
            ),
            ws_send_timeout_seconds=_positive_float(
                values.get("MESHRADAR_WS_SEND_TIMEOUT_SECONDS"),
                default=5.0,
                name="MESHRADAR_WS_SEND_TIMEOUT_SECONDS",
            ),
            ws_ping_interval_seconds=_positive_float(
                values.get("MESHRADAR_WS_PING_INTERVAL_SECONDS"),
                default=20.0,
                name="MESHRADAR_WS_PING_INTERVAL_SECONDS",
            ),
            ws_ping_timeout_seconds=_positive_float(
                values.get("MESHRADAR_WS_PING_TIMEOUT_SECONDS"),
                default=20.0,
                name="MESHRADAR_WS_PING_TIMEOUT_SECONDS",
            ),
        )
