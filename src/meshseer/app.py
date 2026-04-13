from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette import status

from meshseer.audit import FailedAccessTracker, audit_log, request_source
from meshseer.autotrace import AutoTracerouteConfig, AutoTracerouteService
from meshseer.channels import LONGFAST_CHANNEL_NAME, is_primary_channel
from meshseer.clock import utc_now_iso
from meshseer.collector import CollectorCallbacks, CollectorStatus, MeshtasticReceiver
from meshseer.config import Settings
from meshseer.events import EventBroker, EventSubscriptionOverflow, TooManySubscribers
from meshseer.models import NodeRecord, PacketRecord
from meshseer.public_api import (
    collector_status_payload,
    public_chat_messages_payload,
    public_mesh_summary_payload,
    public_node_detail_payload,
    public_nodes_payload,
    public_packet_payload,
    public_packets_payload,
    public_receiver_payload,
)
from meshseer.storage import MeshRepository


STATIC_DIR = Path(__file__).resolve().parent / "static"
RECEIVER_UTILIZATION_WINDOW_MINUTES = 10
PRODUCTION_CSP = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: https://*.basemaps.cartocdn.com",
        "font-src 'self'",
        "connect-src 'self' ws: wss:",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    )
)


def _is_longfast_packet(packet: dict[str, Any]) -> bool:
    return is_primary_channel(packet.get("channel_index"))


def _is_longfast_node(node: dict[str, Any]) -> bool:
    return is_primary_channel(node.get("channel_index"))


def _status_payload(status: CollectorStatus) -> dict[str, Any]:
    return {
        "state": status.state,
        "connected": status.connected,
        "detail": status.detail,
    }


def _perspective_label(local_node_num: int | None, local_node: dict[str, Any] | None) -> str:
    if local_node is not None:
        return str(
            local_node.get("short_name")
            or local_node.get("long_name")
            or local_node.get("node_id")
            or f"Node {local_node['node_num']}"
        )
    if local_node_num is not None:
        return f"Node {local_node_num}"
    return "This receiver"


def _resolved_local_node_num(settings: Settings, collector: Any | None) -> int | None:
    if settings.local_node_num is not None:
        return settings.local_node_num
    getter = getattr(collector, "local_node_num", None)
    if not callable(getter):
        return None
    try:
        node_num = getter()
    except Exception:
        return None
    return node_num if isinstance(node_num, int) else None


def _perspective_payload(settings: Settings, repository: MeshRepository, collector: Any | None) -> dict[str, Any]:
    local_node_num = _resolved_local_node_num(settings, collector)
    local_node = None
    if local_node_num is not None:
        local_node = repository.get_node(local_node_num, primary_only=True)
    label = _perspective_label(local_node_num, local_node)
    return {
        "mode": "receiver_perspective",
        "channel_name": LONGFAST_CHANNEL_NAME,
        "channel_scope": "primary_only",
        "local_node_num": local_node_num,
        "label": label,
        "description": f"Everything shown here is what this receiver has heard on {LONGFAST_CHANNEL_NAME}. This is still a local vantage point, not an authoritative view of the whole mesh.",
    }


def _normalized_http_scheme(value: str) -> str:
    normalized = value.strip().split(",", 1)[0].lower()
    if normalized == "ws":
        return "http"
    if normalized == "wss":
        return "https"
    return normalized


def _default_port_for_scheme(scheme: str) -> int | None:
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    return None


def _websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")
    if not origin or not host:
        return False

    expected_scheme = _normalized_http_scheme(websocket.headers.get("x-forwarded-proto") or websocket.url.scheme)
    if expected_scheme not in {"http", "https"}:
        return False

    try:
        parsed_origin = urlsplit(origin)
        parsed_host = urlsplit(f"//{host}")
    except ValueError:
        return False

    if parsed_origin.scheme.lower() != expected_scheme:
        return False
    if parsed_origin.hostname is None or parsed_host.hostname is None:
        return False

    default_port = _default_port_for_scheme(expected_scheme)
    return (
        parsed_origin.hostname.lower() == parsed_host.hostname.lower()
        and (parsed_origin.port or default_port) == (parsed_host.port or default_port)
    )


async def _close_websocket(websocket: WebSocket, *, code: int) -> None:
    try:
        await websocket.close(code=code)
    except (RuntimeError, WebSocketDisconnect):
        return


def _http_cache_control(path: str) -> str:
    return "no-cache" if path.startswith("/static/") else "no-store"


def _request_client_source(request: Request) -> str:
    client_host = request.client.host if request.client is not None else None
    return request_source(request.headers, client_host)


def _websocket_client_source(websocket: WebSocket) -> str:
    client_host = websocket.client.host if websocket.client is not None else None
    return request_source(websocket.headers, client_host)


def _security_headers(path: str) -> dict[str, str]:
    headers = {
        "Cache-Control": _http_cache_control(path),
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Referrer-Policy": "same-origin",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }
    if path not in {"/docs", "/redoc", "/openapi.json"}:
        headers["Content-Security-Policy"] = PRODUCTION_CSP
    return headers


def create_app(
    settings: Settings,
    *,
    repository: MeshRepository | None = None,
    event_broker: EventBroker | None = None,
    collector: Any | None = None,
    autotrace_service: Any | None = None,
    start_collector: bool = True,
    start_autotrace_service: bool = True,
) -> FastAPI:
    docs_url = None if settings.is_production else "/docs"
    redoc_url = None if settings.is_production else "/redoc"
    openapi_url = None if settings.is_production else "/openapi.json"

    repository = repository or MeshRepository(
        settings.db_path,
        packets_retention_days=settings.retention_packets_days,
        node_metric_history_retention_days=settings.retention_node_metric_history_days,
        traceroute_attempts_retention_days=settings.retention_traceroute_attempts_days,
        prune_interval_seconds=settings.retention_prune_interval_seconds,
    )
    event_broker = event_broker or EventBroker(
        max_connections=settings.ws_max_connections,
        queue_size=settings.ws_queue_size,
    )

    def handle_packet(packet: dict[str, Any]) -> None:
        if not _is_longfast_packet(packet):
            return
        packet_record = PacketRecord.from_mapping(packet)
        packet_id = repository.insert_packet(packet_record)
        repository.observe_packet_node_activity(packet_record)
        stored = repository.get_packet(packet_id)
        if stored is None:
            return
        event_broker.publish(
            {
                "type": "packet_received",
                "ts": utc_now_iso(),
                "data": public_packet_payload(stored),
            }
        )

    def handle_node(node: dict[str, Any]) -> None:
        if not _is_longfast_node(node):
            return
        repository.upsert_node(NodeRecord.from_mapping(node))
        stored = repository.get_node(node["node_num"], primary_only=True)
        if stored is None:
            return
        event_broker.publish(
            {
                "type": "node_updated",
                "ts": utc_now_iso(),
                "data": public_nodes_payload([stored])[0],
            }
        )

    def handle_status(status: CollectorStatus) -> None:
        event_broker.publish(
            {
                "type": "collector_status",
                "ts": utc_now_iso(),
                "data": collector_status_payload(_status_payload(status)),
            }
        )

    collector = collector or MeshtasticReceiver(
        host=settings.meshtastic_host,
        port=settings.meshtastic_port,
        callbacks=CollectorCallbacks(
            on_packet=handle_packet,
            on_node=handle_node,
            on_status=handle_status,
        ),
    )
    autotrace_service = autotrace_service or AutoTracerouteService(
        repository=repository,
        collector=collector,
        local_node_num_getter=lambda: _resolved_local_node_num(settings, collector),
        config=AutoTracerouteConfig(
            interval_seconds=settings.autotrace_interval_seconds,
            target_window_hours=settings.autotrace_target_window_hours,
            cooldown_hours=settings.autotrace_cooldown_hours,
            ack_only_cooldown_hours=settings.autotrace_ack_only_cooldown_hours,
            response_timeout_seconds=settings.autotrace_response_timeout_seconds,
        ),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        event_broker.attach_loop(asyncio.get_running_loop())
        repository.run_maintenance(force=True)
        if start_collector:
            collector.start()
            app.state.collector_started = True
        if start_autotrace_service:
            autotrace_service.start()
            app.state.autotrace_service_started = True
            if settings.autotrace_enabled:
                autotrace_service.enable()
                audit_log(
                    "autotrace_enabled",
                    path="startup",
                    source="startup",
                    trigger="settings",
                )
        try:
            yield
        finally:
            if app.state.autotrace_service_started:
                autotrace_service.stop()
                app.state.autotrace_service_started = False
            if app.state.collector_started:
                collector.stop()
                app.state.collector_started = False

    app = FastAPI(
        title="Meshseer",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.settings = settings
    app.state.repository = repository
    app.state.event_broker = event_broker
    app.state.collector = collector
    app.state.start_collector = start_collector
    app.state.collector_started = False
    app.state.autotrace_service = autotrace_service
    app.state.start_autotrace_service = start_autotrace_service
    app.state.autotrace_service_started = False
    app.state.admin_api_enabled = settings.admin_bearer_token is not None
    app.state.failed_admin_access_tracker = FailedAccessTracker()

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        for header_name, header_value in _security_headers(request.url.path).items():
            response.headers[header_name] = header_value
        return response

    def admin_unauthorized() -> HTTPException:
        return HTTPException(
            status_code=401,
            detail="admin authorization required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def require_admin_bearer(request: Request, authorization: str | None = Header(default=None)) -> None:
        expected = settings.admin_bearer_token
        if expected is None:
            raise HTTPException(status_code=404, detail="not found")
        source = _request_client_source(request)
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token or not secrets.compare_digest(token, expected):
            failure = app.state.failed_admin_access_tracker.record(source=source, path=request.url.path)
            audit_log(
                "admin_auth_decision",
                method=request.method,
                path=request.url.path,
                result="denied",
                reason="invalid_bearer_token",
                source=source,
            )
            if failure["repeated"]:
                audit_log(
                    "admin_auth_repeated_failure",
                    count=failure["count"],
                    method=request.method,
                    path=request.url.path,
                    source=source,
                    window_seconds=failure["window_seconds"],
                )
            raise admin_unauthorized()
        audit_log(
            "admin_auth_decision",
            method=request.method,
            path=request.url.path,
            result="allowed",
            source=source,
        )

    public_router = APIRouter()

    @public_router.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @public_router.get("/api/health")
    async def health() -> dict[str, Any]:
        status = collector.current_status()
        ready = repository.healthcheck()
        return {
            "status": "ok" if ready else "error",
            "collector": collector_status_payload(_status_payload(status)),
            "perspective": _perspective_payload(settings, repository, collector),
        }

    @public_router.get("/api/packets")
    async def list_packets(
        limit: int = Query(default=50, ge=1, le=500),
        since: str | None = None,
        from_node: int | None = None,
        portnum: str | None = None,
    ) -> list[dict[str, Any]]:
        return public_packets_payload(
            repository.list_packets(
                limit=limit,
                since=since,
                from_node=from_node,
                portnum=portnum,
                primary_only=True,
            )
        )

    @public_router.get("/api/chat")
    async def list_chat_messages(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
        return public_chat_messages_payload(repository.list_chat_messages(limit=limit, primary_only=True))

    @public_router.get("/api/mesh/summary")
    async def mesh_summary() -> dict[str, Any]:
        local_node_num = _resolved_local_node_num(settings, collector)
        summary = repository.get_mesh_summary(primary_only=True)
        receiver_node = None
        receiver_history: list[dict[str, Any]] = []
        receiver_windowed_utilization = {
            "window_minutes": RECEIVER_UTILIZATION_WINDOW_MINUTES,
            "channel_utilization_avg": None,
            "air_util_tx_avg": None,
            "sample_count": 0,
        }
        if local_node_num is not None:
            receiver_node = repository.get_node(local_node_num, primary_only=True)
            receiver_history = repository.list_node_metric_history(
                local_node_num,
                primary_only=True,
                limit=24,
            )
            receiver_windowed_utilization = repository.summarize_node_metric_window(
                local_node_num,
                primary_only=True,
                window_minutes=RECEIVER_UTILIZATION_WINDOW_MINUTES,
            )

        receiver = public_receiver_payload(
            local_node_num=local_node_num,
            label=_perspective_label(local_node_num, receiver_node),
            receiver_node=receiver_node,
            history=receiver_history,
            windowed_utilization=receiver_windowed_utilization,
        )
        return public_mesh_summary_payload(summary, receiver=receiver)

    @public_router.get("/api/mesh/routes")
    async def mesh_routes(since: str | None = None) -> dict[str, Any]:
        return repository.get_mesh_routes(since=since, primary_only=True)

    @public_router.get("/api/nodes/roster")
    async def list_nodes_roster() -> list[dict[str, Any]]:
        return public_nodes_payload(
            repository.list_nodes_roster(
                primary_only=True,
                local_node_num=_resolved_local_node_num(settings, collector),
            )
        )

    @public_router.get("/api/nodes/{node_num}")
    async def get_node(node_num: int) -> dict[str, Any]:
        node = repository.get_node(node_num, primary_only=True)
        if node is None:
            raise HTTPException(status_code=404, detail="node not found")
        return public_node_detail_payload(
            node,
            recent_packets=repository.list_packets_for_node(node_num, limit=20, primary_only=True),
            insights=repository.get_node_insights(node_num, primary_only=True),
        )

    @public_router.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket) -> None:
        source = _websocket_client_source(websocket)
        origin = websocket.headers.get("origin")
        disconnect_logged = False

        def log_disconnect(reason: str, close_code: int) -> None:
            nonlocal disconnect_logged
            if disconnect_logged:
                return
            disconnect_logged = True
            audit_log(
                "websocket_disconnected",
                close_code=close_code,
                origin=origin,
                path=websocket.url.path,
                reason=reason,
                source=source,
            )

        if not _websocket_origin_allowed(websocket):
            audit_log(
                "websocket_rejected",
                close_code=status.WS_1008_POLICY_VIOLATION,
                origin=origin,
                path=websocket.url.path,
                reason="origin_not_allowed",
                source=source,
            )
            await _close_websocket(websocket, code=status.WS_1008_POLICY_VIOLATION)
            return

        try:
            async with event_broker.subscription() as subscription:
                await websocket.accept()
                audit_log(
                    "websocket_connected",
                    origin=origin,
                    path=websocket.url.path,
                    source=source,
                )
                while True:
                    event_task = asyncio.create_task(subscription.get())
                    receive_task = asyncio.create_task(websocket.receive())
                    done, pending = await asyncio.wait(
                        {event_task, receive_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)

                    if receive_task in done:
                        message = receive_task.result()
                        if message.get("type") == "websocket.disconnect":
                            close_code = int(message.get("code") or status.WS_1000_NORMAL_CLOSURE)
                            log_disconnect("client_disconnect", close_code)
                            return
                        continue

                    event = event_task.result()
                    await asyncio.wait_for(
                        websocket.send_text(json.dumps(event)),
                        timeout=settings.ws_send_timeout_seconds,
                    )
        except TooManySubscribers:
            audit_log(
                "websocket_rejected",
                close_code=status.WS_1013_TRY_AGAIN_LATER,
                origin=origin,
                path=websocket.url.path,
                reason="too_many_subscribers",
                source=source,
            )
            await _close_websocket(websocket, code=status.WS_1013_TRY_AGAIN_LATER)
            return
        except EventSubscriptionOverflow:
            log_disconnect("subscriber_overflow", status.WS_1013_TRY_AGAIN_LATER)
            await _close_websocket(websocket, code=status.WS_1013_TRY_AGAIN_LATER)
            return
        except TimeoutError:
            log_disconnect("send_timeout", status.WS_1013_TRY_AGAIN_LATER)
            await _close_websocket(websocket, code=status.WS_1013_TRY_AGAIN_LATER)
            return
        except WebSocketDisconnect:
            log_disconnect("client_disconnect", status.WS_1000_NORMAL_CLOSURE)
            return
        except asyncio.CancelledError:
            log_disconnect("client_disconnect", status.WS_1000_NORMAL_CLOSURE)
            return

    app.include_router(public_router)

    if settings.admin_bearer_token is not None:
        admin_router = APIRouter(
            prefix="/api/admin",
            dependencies=[Depends(require_admin_bearer)],
        )

        @admin_router.get("/health")
        async def admin_health() -> dict[str, Any]:
            status = collector.current_status()
            return {
                "status": "ok" if repository.healthcheck() else "error",
                "collector": _status_payload(status),
                "perspective": _perspective_payload(settings, repository, collector),
                "database": {
                    "ready": repository.healthcheck(),
                    "path": str(settings.db_path),
                },
            }

        @admin_router.get("/mesh/links")
        async def admin_mesh_links() -> dict[str, Any]:
            return repository.get_mesh_links(primary_only=True)

        @admin_router.get("/mesh/autotrace")
        async def admin_autotrace_status() -> dict[str, Any]:
            return autotrace_service.status()

        @admin_router.post("/mesh/autotrace/enable")
        async def admin_autotrace_enable(request: Request) -> dict[str, Any]:
            autotrace_service.enable()
            audit_log(
                "autotrace_enabled",
                path=request.url.path,
                source=_request_client_source(request),
                trigger="admin_api",
            )
            return autotrace_service.status()

        @admin_router.post("/mesh/autotrace/disable")
        async def admin_autotrace_disable(request: Request) -> dict[str, Any]:
            autotrace_service.disable()
            audit_log(
                "autotrace_disabled",
                path=request.url.path,
                source=_request_client_source(request),
                trigger="admin_api",
            )
            return autotrace_service.status()

        @admin_router.get("/packets/{packet_id}")
        async def admin_get_packet(packet_id: int) -> dict[str, Any]:
            packet = repository.get_packet(packet_id, primary_only=True)
            if packet is None:
                raise HTTPException(status_code=404, detail="packet not found")
            return packet

        @admin_router.get("/nodes")
        async def admin_list_nodes() -> list[dict[str, Any]]:
            return repository.list_nodes(primary_only=True)

        app.include_router(admin_router)

    return app
