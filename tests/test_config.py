import os

from meshradar.config import Settings
from meshradar.env import load_env_file


def test_settings_defaults():
    settings = Settings.from_env({})

    assert settings.meshtastic_host == "10.10.99.253"
    assert settings.meshtastic_port == 4403
    assert settings.bind_host == "0.0.0.0"
    assert settings.bind_port == 8000
    assert settings.db_path.name == "meshradar.db"
    assert settings.local_node_num is None
    assert settings.autotrace_enabled is False


def test_settings_override_from_env(tmp_path):
    settings = Settings.from_env(
        {
            "MESHRADAR_MESHTASTIC_HOST": "192.168.1.20",
            "MESHRADAR_MESHTASTIC_PORT": "1234",
            "MESHRADAR_BIND_HOST": "127.0.0.1",
            "MESHRADAR_BIND_PORT": "9000",
            "MESHRADAR_DB_PATH": str(tmp_path / "mesh.db"),
            "MESHRADAR_LOCAL_NODE_NUM": "456",
            "MESHRADAR_AUTOTRACE_ENABLED": "true",
        }
    )

    assert settings.meshtastic_host == "192.168.1.20"
    assert settings.meshtastic_port == 1234
    assert settings.bind_host == "127.0.0.1"
    assert settings.bind_port == 9000
    assert settings.db_path == tmp_path / "mesh.db"
    assert settings.local_node_num == 456
    assert settings.autotrace_enabled is True


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
