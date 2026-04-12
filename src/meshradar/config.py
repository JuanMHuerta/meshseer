from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


@dataclass(frozen=True)
class Settings:
    meshtastic_host: str
    meshtastic_port: int
    bind_host: str
    bind_port: int
    db_path: Path
    local_node_num: int | None
    autotrace_enabled: bool
    autotrace_interval_seconds: int
    autotrace_target_window_hours: int
    autotrace_cooldown_hours: int
    autotrace_ack_only_cooldown_hours: int
    autotrace_response_timeout_seconds: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env
        return cls(
            meshtastic_host=values.get("MESHRADAR_MESHTASTIC_HOST", "10.10.99.253"),
            meshtastic_port=int(values.get("MESHRADAR_MESHTASTIC_PORT", "4403")),
            bind_host=values.get("MESHRADAR_BIND_HOST", "0.0.0.0"),
            bind_port=int(values.get("MESHRADAR_BIND_PORT", "8000")),
            db_path=Path(values.get("MESHRADAR_DB_PATH", "./data/meshradar.db")),
            local_node_num=_optional_int(values.get("MESHRADAR_LOCAL_NODE_NUM")),
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
        )
