from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from meshradar.normalizers import normalize_node, normalize_packet


@dataclass(frozen=True)
class CollectorStatus:
    state: str
    connected: bool
    detail: str | None


@dataclass(frozen=True)
class CollectorCallbacks:
    on_packet: Callable[[dict[str, Any]], None]
    on_node: Callable[[dict[str, Any]], None]
    on_status: Callable[[CollectorStatus], None]


@dataclass(frozen=True)
class TraceRouteResult:
    status: str
    request_mesh_packet_id: int | None
    response_mesh_packet_id: int | None
    detail: str | None


class PubSubLike(Protocol):
    def subscribe(self, callback: Callable[..., None], topic: str) -> None: ...


class MeshtasticReceiver:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        callbacks: CollectorCallbacks,
        interface_factory: Callable[[str, int], Any] | None = None,
        pubsub: PubSubLike | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.callbacks = callbacks
        self._interface_factory = interface_factory or self._default_interface_factory
        self._pubsub = pubsub
        self._sleeper = sleeper or self._default_sleeper
        self._status = CollectorStatus(state="idle", connected=False, detail=None)
        self._status_lock = threading.Lock()
        self._interface_lock = threading.Lock()
        self._subscribed = False
        self._interface: Any = None
        self._stop_event = threading.Event()
        self._reconnect_event = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _default_pubsub() -> PubSubLike:
        from pubsub import pub

        return pub

    @staticmethod
    def _default_sleeper(seconds: float) -> None:
        threading.Event().wait(seconds)

    @staticmethod
    def _default_interface_factory(host: str, port: int) -> Any:
        from meshtastic.tcp_interface import TCPInterface

        return TCPInterface(hostname=host, portNumber=port)

    def _set_status(self, state: str, connected: bool, detail: str | None) -> None:
        status = CollectorStatus(state=state, connected=connected, detail=detail)
        with self._status_lock:
            self._status = status
        self.callbacks.on_status(status)

    def current_status(self) -> CollectorStatus:
        with self._status_lock:
            return self._status

    def local_node_num(self) -> int | None:
        with self._interface_lock:
            interface = self._interface
        if interface is None:
            return None
        my_info = getattr(interface, "myInfo", None)
        node_num = getattr(my_info, "my_node_num", None)
        return node_num if isinstance(node_num, int) else None

    def _subscribe_once(self) -> None:
        if self._subscribed:
            return
        pubsub = self._pubsub or self._default_pubsub()
        self._pubsub = pubsub
        pubsub.subscribe(self._handle_packet, "meshtastic.receive")
        pubsub.subscribe(self._handle_node, "meshtastic.node.updated")
        pubsub.subscribe(self._handle_connection_established, "meshtastic.connection.established")
        pubsub.subscribe(self._handle_connection_lost, "meshtastic.connection.lost")
        self._subscribed = True

    def _handle_packet(self, packet: dict[str, Any], interface: Any | None = None, **_: Any) -> None:
        if interface is not None and self._interface is not None and interface is not self._interface:
            return
        self.callbacks.on_packet(normalize_packet(packet))

    def _handle_node(self, node: dict[str, Any], interface: Any | None = None, **_: Any) -> None:
        if interface is not None and self._interface is not None and interface is not self._interface:
            return
        self.callbacks.on_node(normalize_node(node))

    def _handle_connection_established(self, interface: Any | None = None, **_: Any) -> None:
        if interface is None or self._interface is interface:
            self._set_status("connected", True, None)

    def _handle_connection_lost(self, interface: Any | None = None, **_: Any) -> None:
        if interface is not None and self._interface is not None and interface is not self._interface:
            return
        self._set_status("disconnected", False, "connection lost")
        self._reconnect_event.set()

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        return min(float(2 ** max(attempt - 1, 0)), 30.0)

    def connect_once(self) -> Any:
        self._subscribe_once()
        self._set_status("connecting", False, None)
        interface = self._interface_factory(self.host, self.port)
        with self._interface_lock:
            self._interface = interface
        self._set_status("connected", True, None)
        return interface

    def connect_with_retry(self, *, max_attempts: int | None = None) -> Any | None:
        attempt = 0
        while not self._stop_event.is_set():
            if max_attempts is not None and attempt >= max_attempts:
                return None
            attempt += 1
            try:
                return self.connect_once()
            except Exception as exc:  # pragma: no cover - exercised by tests through behavior
                self._set_status("disconnected", False, str(exc))
                if max_attempts is not None and attempt >= max_attempts:
                    return None
                self._sleeper(self._backoff_delay(attempt))
        return None

    def _close_interface(self) -> None:
        with self._interface_lock:
            interface = self._interface
            self._interface = None
        if interface is None:
            return
        interface.close()

    @staticmethod
    def _traceroute_status(response_packet: dict[str, Any] | None) -> tuple[str, str | None]:
        if response_packet is None:
            return ("timeout", "Timed out waiting for traceroute response")

        decoded = response_packet.get("decoded", {})
        if not isinstance(decoded, dict):
            return ("error", "Traceroute response missing decoded payload")

        portnum = decoded.get("portnum")
        if portnum == "TRACEROUTE_APP":
            return ("success", None)

        if portnum == "ROUTING_APP":
            routing = decoded.get("routing", {})
            if not isinstance(routing, dict):
                return ("ack_only", "Routing response contained no route payload")
            if isinstance(routing.get("routeReply"), dict) or isinstance(routing.get("route_reply"), dict):
                return ("success", None)
            error_reason = routing.get("errorReason", routing.get("error_reason"))
            if isinstance(error_reason, str):
                if error_reason == "NONE":
                    return ("ack_only", "Routing ACK did not include a route")
                return ("no_route", f"Routing error: {error_reason}")
            return ("ack_only", "Routing response contained no route payload")

        return ("error", f"Unexpected traceroute response port: {portnum}")

    def trace_route(
        self,
        dest_node_num: int,
        *,
        hop_limit: int,
        channel_index: int = 0,
        timeout_seconds: int = 20,
    ) -> TraceRouteResult:
        from meshtastic.protobuf import mesh_pb2, portnums_pb2

        response_event = threading.Event()
        response_packet: dict[str, Any] = {}

        def on_response(packet: dict[str, Any]) -> None:
            response_packet["packet"] = packet
            response_event.set()

        with self._interface_lock:
            interface = self._interface
            if interface is None or not self.current_status().connected:
                raise RuntimeError("collector not connected")
            sent_packet = interface.sendData(
                mesh_pb2.RouteDiscovery(),
                destinationId=dest_node_num,
                portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
                wantResponse=True,
                onResponse=on_response,
                onResponseAckPermitted=True,
                channelIndex=channel_index,
                hopLimit=hop_limit,
            )

        response_event.wait(timeout_seconds)
        raw_response = response_packet.get("packet")
        status, detail = self._traceroute_status(raw_response if isinstance(raw_response, dict) else None)
        normalized = normalize_packet(raw_response) if isinstance(raw_response, dict) else None
        return TraceRouteResult(
            status=status,
            request_mesh_packet_id=getattr(sent_packet, "id", None),
            response_mesh_packet_id=None if normalized is None else normalized.get("mesh_packet_id"),
            detail=detail,
        )

    def _run_loop(self) -> None:
        failure_count = 0
        while not self._stop_event.is_set():
            if self._interface is None:
                try:
                    self.connect_once()
                    failure_count = 0
                except Exception as exc:
                    failure_count += 1
                    self._set_status("disconnected", False, str(exc))
                    self._sleeper(self._backoff_delay(failure_count))
                    continue
            should_reconnect = self._reconnect_event.wait(0.25)
            if should_reconnect:
                self._reconnect_event.clear()
                self._close_interface()
        self._close_interface()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="meshradar-collector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._reconnect_event.set()
        self._close_interface()
        if self._thread is not None:
            self._thread.join(timeout=2)
