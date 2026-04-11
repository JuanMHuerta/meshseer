from __future__ import annotations

import os

import uvicorn

from meshradar.app import create_app
from meshradar.config import Settings


def build_app():
    return create_app(Settings.from_env(os.environ))


app = build_app()


def run() -> None:
    settings = Settings.from_env(os.environ)
    uvicorn.run(app, host=settings.bind_host, port=settings.bind_port)

