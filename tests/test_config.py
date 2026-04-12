import os

import pytest

from meshradar.config import Settings
from meshradar.env import load_env_file


def test_settings_defaults():
    settings = Settings.from_env({})

    assert settings.environment == "development"
    assert settings.meshtastic_host == "10.10.99.253"
    assert settings.meshtastic_port == 4403
    assert settings.bind_host == "0.0.0.0"
    assert settings.bind_port == 8000
    assert settings.db_path.name == "meshradar.db"
    assert settings.local_node_num is None
    assert settings.admin_bearer_token is None
    assert settings.autotrace_enabled is False
    assert settings.ws_max_connections == 32
    assert settings.ws_queue_size == 32
    assert settings.ws_send_timeout_seconds == 5.0
    assert settings.ws_ping_interval_seconds == 20.0
    assert settings.ws_ping_timeout_seconds == 20.0
    assert settings.is_production is False


def test_settings_override_from_env(tmp_path):
    settings = Settings.from_env(
        {
            "MESHRADAR_ENV": "prod",
            "MESHRADAR_MESHTASTIC_HOST": "192.168.1.20",
            "MESHRADAR_MESHTASTIC_PORT": "1234",
            "MESHRADAR_BIND_HOST": "127.0.0.1",
            "MESHRADAR_BIND_PORT": "9000",
            "MESHRADAR_DB_PATH": str(tmp_path / "mesh.db"),
            "MESHRADAR_LOCAL_NODE_NUM": "456",
            "MESHRADAR_ADMIN_BEARER_TOKEN": "  secret-token  ",
            "MESHRADAR_AUTOTRACE_ENABLED": "true",
            "MESHRADAR_WS_MAX_CONNECTIONS": "12",
            "MESHRADAR_WS_QUEUE_SIZE": "8",
            "MESHRADAR_WS_SEND_TIMEOUT_SECONDS": "7.5",
            "MESHRADAR_WS_PING_INTERVAL_SECONDS": "25",
            "MESHRADAR_WS_PING_TIMEOUT_SECONDS": "15",
        }
    )

    assert settings.environment == "production"
    assert settings.meshtastic_host == "192.168.1.20"
    assert settings.meshtastic_port == 1234
    assert settings.bind_host == "127.0.0.1"
    assert settings.bind_port == 9000
    assert settings.db_path == tmp_path / "mesh.db"
    assert settings.local_node_num == 456
    assert settings.admin_bearer_token == "secret-token"
    assert settings.autotrace_enabled is True
    assert settings.ws_max_connections == 12
    assert settings.ws_queue_size == 8
    assert settings.ws_send_timeout_seconds == 7.5
    assert settings.ws_ping_interval_seconds == 25.0
    assert settings.ws_ping_timeout_seconds == 15.0
    assert settings.is_production is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("dev", "development"),
        ("development", "development"),
        ("prod", "production"),
        ("production", "production"),
    ],
)
def test_settings_environment_aliases(value, expected):
    settings = Settings.from_env({"MESHRADAR_ENV": value})

    assert settings.environment == expected


def test_settings_invalid_environment_raises():
    with pytest.raises(ValueError, match="MESHRADAR_ENV must be one of"):
        Settings.from_env({"MESHRADAR_ENV": "staging"})


def test_load_env_file_sets_missing_values_without_overriding_existing_env(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MESHRADAR_AUTOTRACE_ENABLED=true\nMESHRADAR_BIND_PORT=7000\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("MESHRADAR_AUTOTRACE_ENABLED", raising=False)
    monkeypatch.setenv("MESHRADAR_BIND_PORT", "9100")

    loaded = load_env_file(env_path)

    assert loaded == env_path
    assert os.environ["MESHRADAR_AUTOTRACE_ENABLED"] == "true"
    assert os.environ["MESHRADAR_BIND_PORT"] == "9100"
