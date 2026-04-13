from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from meshseer.clock import to_utc_iso, utc_now


@dataclass(frozen=True)
class AutoTracerouteConfig:
    interval_seconds: int
    target_window_hours: int
    cooldown_hours: int
    ack_only_cooldown_hours: int
    response_timeout_seconds: int
    recent_attempt_limit: int = 10


class AutoTracerouteService:
    def __init__(
        self,
        *,
        repository: Any,
        collector: Any,
        local_node_num_getter: Callable[[], int | None],
        config: AutoTracerouteConfig,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._collector = collector
        self._local_node_num_getter = local_node_num_getter
        self._config = config
        self._now_provider = now_provider
        self._enabled = False
        self._lock = threading.Lock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="meshseer-autotrace", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.join(timeout=2)

    def enable(self) -> None:
        with self._lock:
            self._enabled = True
        self._wake_event.set()

    def disable(self) -> None:
        with self._lock:
            self._enabled = False
        self._wake_event.set()

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def _wait(self, seconds: float) -> None:
        self._wake_event.wait(seconds)
        self._wake_event.clear()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self.is_enabled():
                self._wait(1.0)
                continue

            collector_status = self._collector.current_status()
            if not getattr(collector_status, "connected", False):
                self._wait(5.0)
                continue

            local_node_num = self._local_node_num_getter()
            if local_node_num is None:
                self._wait(5.0)
                continue

            self.run_cycle()
            self._wait(float(self._config.interval_seconds))

    def run_cycle(self) -> dict[str, Any] | None:
        if not self.is_enabled():
            return None

        collector_status = self._collector.current_status()
        if not getattr(collector_status, "connected", False):
            return None

        local_node_num = self._local_node_num_getter()
        if local_node_num is None:
            return None

        target = self._repository.get_next_autotrace_target(
            local_node_num=local_node_num,
            target_window_hours=self._config.target_window_hours,
            cooldown_hours=self._config.cooldown_hours,
            ack_only_cooldown_hours=self._config.ack_only_cooldown_hours,
            primary_only=True,
            now=self._now_provider(),
        )
        if target is None:
            return None

        target_node_num = target["node_num"]
        hops_away = target.get("hops_away")
        hop_limit = max(1, min(hops_away if isinstance(hops_away, int) else 1, 7))
        requested_at = to_utc_iso(self._now_provider())
        attempt_id = self._repository.start_traceroute_attempt(
            target_node_num=target_node_num,
            requested_at=requested_at,
            hop_limit=hop_limit,
        )

        status = "error"
        detail: str | None = None
        request_mesh_packet_id: int | None = None
        response_mesh_packet_id: int | None = None
        try:
            result = self._collector.trace_route(
                target_node_num,
                hop_limit=hop_limit,
                channel_index=0,
                timeout_seconds=self._config.response_timeout_seconds,
            )
            status = result.status
            detail = result.detail
            request_mesh_packet_id = result.request_mesh_packet_id
            response_mesh_packet_id = result.response_mesh_packet_id
        except Exception as exc:  # pragma: no cover - exercised by tests through behavior
            detail = str(exc)

        self._repository.complete_traceroute_attempt(
            attempt_id,
            completed_at=to_utc_iso(self._now_provider()),
            status=status,
            request_mesh_packet_id=request_mesh_packet_id,
            response_mesh_packet_id=response_mesh_packet_id,
            detail=detail,
        )
        return self._repository.get_last_traceroute_attempt()

    def status(self) -> dict[str, Any]:
        local_node_num = self._local_node_num_getter()
        return {
            "enabled": self.is_enabled(),
            "running": self.is_enabled() and self._thread is not None and self._thread.is_alive(),
            "local_node_num": local_node_num,
            "interval_seconds": self._config.interval_seconds,
            "cooldown_hours": self._config.cooldown_hours,
            "ack_only_cooldown_hours": self._config.ack_only_cooldown_hours,
            "target_window_hours": self._config.target_window_hours,
            "response_timeout_seconds": self._config.response_timeout_seconds,
            "eligible_targets": self._repository.count_autotrace_candidates(
                local_node_num=local_node_num,
                target_window_hours=self._config.target_window_hours,
                cooldown_hours=self._config.cooldown_hours,
                ack_only_cooldown_hours=self._config.ack_only_cooldown_hours,
                primary_only=True,
                now=self._now_provider(),
            ),
            "last_attempt": self._repository.get_last_traceroute_attempt(),
            "recent_attempts": self._repository.list_recent_traceroute_attempts(
                limit=self._config.recent_attempt_limit
            ),
        }
