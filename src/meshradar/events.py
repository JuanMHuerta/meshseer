from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


class EventBroker:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            queues = list(self._queues)
        if self._loop is None:
            return
        for queue in queues:
            self._loop.call_soon_threadsafe(queue.put_nowait, event)

    @asynccontextmanager
    async def subscription(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        with self._lock:
            self._queues.append(queue)
        try:
            yield queue
        finally:
            with self._lock:
                if queue in self._queues:
                    self._queues.remove(queue)

