from __future__ import annotations

import io
from urllib.error import URLError

from meshseer.startup import ProbeResult, main, probe_existing_server


class _FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeResponse(io.BytesIO):
    def __init__(self, status: int, body: bytes):
        super().__init__(body)
        self.status = status


def test_probe_existing_server_returns_free_when_port_is_closed(monkeypatch):
    def fake_create_connection(address, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr("meshseer.startup.socket.create_connection", fake_create_connection)

    result = probe_existing_server("0.0.0.0", 8000)

    assert result == ProbeResult(status="free", health_url="http://127.0.0.1:8000/api/health")


def test_probe_existing_server_detects_meshseer(monkeypatch):
    def fake_create_connection(address, timeout):
        return _FakeSocket()

    def fake_urlopen(url, timeout):
        assert url == "http://127.0.0.1:8000/api/health"
        return _FakeResponse(status=200, body=b'{"status":"ok"}')

    monkeypatch.setattr("meshseer.startup.socket.create_connection", fake_create_connection)
    monkeypatch.setattr("meshseer.startup.urlopen", fake_urlopen)

    result = probe_existing_server("0.0.0.0", 8000)

    assert result == ProbeResult(status="meshseer", health_url="http://127.0.0.1:8000/api/health")


def test_probe_existing_server_reports_busy_for_other_service(monkeypatch):
    def fake_create_connection(address, timeout):
        return _FakeSocket()

    def fake_urlopen(url, timeout):
        raise URLError("wrong service")

    monkeypatch.setattr("meshseer.startup.socket.create_connection", fake_create_connection)
    monkeypatch.setattr("meshseer.startup.urlopen", fake_urlopen)

    result = probe_existing_server("127.0.0.1", 9000)

    assert result == ProbeResult(status="busy", health_url="http://127.0.0.1:9000/api/health")


def test_main_returns_already_running_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        "meshseer.startup.probe_existing_server",
        lambda host, port: ProbeResult(status="meshseer", health_url="http://127.0.0.1:8000/api/health"),
    )

    exit_code = main(["--host", "0.0.0.0", "--port", "8000"])

    assert exit_code == 10
    assert capsys.readouterr().out.strip() == "http://127.0.0.1:8000/api/health"
