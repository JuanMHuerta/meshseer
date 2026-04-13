from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any


class TooManySubscribers(RuntimeError):
    pass


class EventSubscriptionOverflow(RuntimeError):
    pass


@dataclass(slots=True)
class EventSubscription:
    queue: asyncio.Queue[dict[str, Any]]
    overflowed: asyncio.Event = field(default_factory=asyncio.Event)

    @classmethod
    def create(cls, *, queue_size: int) -> "EventSubscription":
        return cls(queue=asyncio.Queue(maxsize=queue_size))

    async def get(self) -> dict[str, Any]:
        if self.overflowed.is_set():
            raise EventSubscriptionOverflow

        get_task = asyncio.create_task(self.queue.get())
        overflow_task = asyncio.create_task(self.overflowed.wait())
        _done, pending = await asyncio.wait(
            {get_task, overflow_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        if self.overflowed.is_set():
            raise EventSubscriptionOverflow
        return get_task.result()


class EventBroker:
    def __init__(self, *, max_connections: int = 32, queue_size: int = 32) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: list[EventSubscription] = []
        self._max_connections = max_connections
        self._queue_size = queue_size
        self._lock = threading.Lock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._publish_on_loop, event)
        except RuntimeError:
            return

    @asynccontextmanager
    async def subscription(self) -> AsyncIterator[EventSubscription]:
        subscriber = EventSubscription.create(queue_size=self._queue_size)
        with self._lock:
            if len(self._subscribers) >= self._max_connections:
                raise TooManySubscribers("websocket subscriber limit reached")
            self._subscribers.append(subscriber)
        try:
            yield subscriber
        finally:
            self._remove_subscriber(subscriber)

    def _publish_on_loop(self, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)

        dropped: list[EventSubscription] = []
        for subscriber in subscribers:
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                subscriber.overflowed.set()
                dropped.append(subscriber)

        for subscriber in dropped:
            self._remove_subscriber(subscriber)

    def _remove_subscriber(self, subscriber: EventSubscription) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)
