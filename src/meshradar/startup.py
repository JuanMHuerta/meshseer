from __future__ import annotations

import argparse
import json
import socket
from dataclasses import dataclass
from typing import Literal, Sequence
from urllib.error import URLError
from urllib.request import urlopen


ProbeStatus = Literal["free", "meshradar", "busy"]


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    health_url: str


def _probe_host(bind_host: str) -> str:
    if bind_host in {"", "0.0.0.0"}:
        return "127.0.0.1"
    if bind_host == "::":
        return "::1"
    return bind_host


def _health_url(host: str, port: int) -> str:
    if ":" in host and not host.startswith("["):
        return f"http://[{host}]:{port}/api/health"
    return f"http://{host}:{port}/api/health"


def probe_existing_server(bind_host: str, bind_port: int) -> ProbeResult:
    probe_host = _probe_host(bind_host)
    health_url = _health_url(probe_host, bind_port)

    try:
        with socket.create_connection((probe_host, bind_port), timeout=0.5):
            pass
    except OSError:
        return ProbeResult(status="free", health_url=health_url)

    try:
        with urlopen(health_url, timeout=1.0) as response:
            if response.status == 200 and json.load(response).get("status") == "ok":
                return ProbeResult(status="meshradar", health_url=health_url)
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        pass

    return ProbeResult(status="busy", health_url=health_url)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Meshradar startup preflight")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args(argv)

    result = probe_existing_server(args.host, args.port)
    if result.status == "free":
        return 0

    print(result.health_url)
    if result.status == "meshradar":
        return 10
    return 11


if __name__ == "__main__":
    raise SystemExit(main())
