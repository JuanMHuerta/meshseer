from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette import status

from meshseer import __version__
from meshseer.audit import FailedAccessTracker, audit_log, request_source
from meshseer.autotrace import AutoTracerouteConfig, AutoTracerouteService
from meshseer.channels import BROADCAST_NODE_NUM, is_primary_channel
from meshseer.clock import to_utc_iso, utc_now, utc_now_iso
from meshseer.collector import CollectorCallbacks, CollectorStatus, MeshtasticReceiver
from meshseer.config import Settings
from meshseer.events import EventBroker, EventSubscriptionOverflow, TooManySubscribers
from meshseer.models import NodeRecord, PacketRecord
from meshseer.public_api import (
    collector_status_payload,
    public_chat_message_payload,
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
ROUTES_MAX_LOOKBACK_DAYS = 7
PUBLIC_MESH_ROUTES_LIMIT = 250
PUBLIC_MESH_ROUTES_LIMIT_MAX = 500
PUBLIC_CHAT_LIMIT = 40
PUBLIC_NODE_RECENT_PACKETS_LIMIT = 12
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


def _is_primary_channel_packet(packet: dict[str, Any]) -> bool:
    return is_primary_channel(packet.get("channel_index"))


def _is_primary_channel_node(node: dict[str, Any]) -> bool:
    return is_primary_channel(node.get("channel_index"))


def _status_payload(status: CollectorStatus) -> dict[str, Any]:
    return {
        "state": status.state,
        "connected": status.connected,
        "detail": status.detail,
    }


def _autotrace_position_tracking_enabled(
    settings: Settings,
    service: Any | None,
) -> bool:
    enabled_getter = None if service is None else getattr(service, "is_enabled", None)
    if callable(enabled_getter):
        try:
            return bool(enabled_getter())
        except Exception:
            return False
    return bool(settings.autotrace_enabled)


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
    channel_name_getter = None if collector is None else getattr(collector, "primary_channel_name", None)
    channel_name = channel_name_getter() if callable(channel_name_getter) else None
    channel_description = (
        f"Everything shown here is what this receiver has heard on {channel_name}."
        if isinstance(channel_name, str) and channel_name.strip()
        else "Everything shown here is what this receiver has heard on its primary channel."
    )
    return {
        "mode": "receiver_perspective",
        "channel_name": channel_name,
        "channel_scope": "primary_only",
        "local_node_num": local_node_num,
        "label": label,
        "description": f"{channel_description} This is still a local vantage point, not an authoritative view of the whole mesh.",
    }


def _public_status_payload(settings: Settings, repository: MeshRepository, collector: Any) -> dict[str, Any]:
    status = collector.current_status()
    perspective = _perspective_payload(settings, repository, collector)
    return {
        "collector": collector_status_payload(_status_payload(status)),
        "perspective": {
            "local_node_num": perspective["local_node_num"],
            "label": perspective["label"],
            "channel_name": perspective["channel_name"],
        },
        "ui": {
            "default_style": settings.ui_default_style,
        },
        "version": __version__,
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


def _parse_query_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid since timestamp") from exc
    if parsed.tzinfo is None:
        raise HTTPException(status_code=400, detail="invalid since timestamp")
    return parsed.astimezone(UTC)


def _bounded_routes_since(since: str | None) -> str:
    cutoff = utc_now() - timedelta(days=ROUTES_MAX_LOOKBACK_DAYS)
    if since is None:
        return to_utc_iso(cutoff)

    parsed = _parse_query_timestamp(since)
    if parsed < cutoff:
        return to_utc_iso(cutoff)
    return to_utc_iso(parsed)


def _is_public_chat_packet(packet: Mapping[str, Any]) -> bool:
    text_preview = packet.get("text_preview")
    return (
        packet.get("portnum") == "TEXT_MESSAGE_APP"
        and isinstance(text_preview, str)
        and bool(text_preview.strip())
        and packet.get("to_node_num") == BROADCAST_NODE_NUM
    )


def _packet_position(packet: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        raw_json = json.loads(packet.get("raw_json") or "{}")
    except (TypeError, ValueError):
        return None
    decoded = raw_json.get("decoded")
    if not isinstance(decoded, dict):
        return None
    position = decoded.get("position")
    if not isinstance(position, dict):
        return None
    latitude = position.get("latitude")
    longitude = position.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None
    return float(latitude), float(longitude)


def _traceroute_attempt_with_route(
    repository: MeshRepository,
    *,
    target_node_num: int,
    attempt: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if attempt is None:
        return None
    return {
        **attempt,
        "route": repository.get_traceroute_route_for_attempt(
            target_node_num=target_node_num,
            response_mesh_packet_id=attempt.get("response_mesh_packet_id"),
        ),
    }


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
        if not _is_primary_channel_packet(packet):
            return
        packet_record = PacketRecord.from_mapping(packet)
        packet_id = repository.insert_packet(packet_record)
        repository.observe_packet_node_activity(packet_record)
        stored = repository.get_packet(packet_id)
        if stored is None:
            return
        local_node_num = _resolved_local_node_num(settings, collector)
        event_broker.publish(
            {
                "type": "packet_received",
                "ts": utc_now_iso(),
                "data": public_packet_payload(stored, local_node_num=local_node_num),
            }
        )
        if _is_public_chat_packet(stored):
            chat_packet = dict(stored)
            from_node_num = chat_packet.get("from_node_num")
            if isinstance(from_node_num, int):
                sender_node = repository.get_node(from_node_num, primary_only=True)
                if sender_node is not None:
                    chat_packet.setdefault("from_short_name", sender_node.get("short_name"))
                    chat_packet.setdefault("from_long_name", sender_node.get("long_name"))
                    chat_packet.setdefault("from_node_id", sender_node.get("node_id"))
            event_broker.publish(
                {
                    "type": "chat_message_received",
                    "ts": utc_now_iso(),
                    "data": public_chat_message_payload(chat_packet, local_node_num=local_node_num),
                }
        )
        if (
            _autotrace_position_tracking_enabled(settings, autotrace_service)
            and
            packet_record.portnum == "POSITION_APP"
            and isinstance(packet_record.from_node_num, int)
            and not packet_record.via_mqtt
        ):
            position = _packet_position(stored)
            if position is not None:
                repository.mark_position_trace_candidate(
                    node_num=packet_record.from_node_num,
                    triggered_at=packet_record.received_at,
                    latitude=position[0],
                    longitude=position[1],
                    movement_distance_meters=settings.autotrace_position_movement_distance_meters,
                    cooldown_hours=settings.autotrace_cooldown_hours,
                    primary_only=True,
                )

    def handle_node(node: dict[str, Any]) -> None:
        if not _is_primary_channel_node(node):
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
            position_priority_window_minutes=settings.autotrace_position_priority_window_minutes,
            position_movement_distance_meters=settings.autotrace_position_movement_distance_meters,
            position_movement_cooldown_minutes=settings.autotrace_position_movement_cooldown_minutes,
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
        ready = repository.healthcheck()
        return {"status": "ok" if ready else "error"}

    @public_router.get("/api/status")
    async def public_status() -> dict[str, Any]:
        return _public_status_payload(settings, repository, collector)

    @public_router.get("/api/packets")
    async def list_packets(
        limit: int = Query(default=50, ge=1, le=500),
        since: str | None = None,
        from_node: int | None = None,
        portnum: str | None = None,
    ) -> list[dict[str, Any]]:
        local_node_num = _resolved_local_node_num(settings, collector)
        return public_packets_payload(
            repository.list_packets(
                limit=limit,
                since=since,
                from_node=from_node,
                portnum=portnum,
                primary_only=True,
            ),
            local_node_num=local_node_num,
        )

    @public_router.get("/api/chat")
    async def list_chat_messages(limit: int = Query(default=PUBLIC_CHAT_LIMIT, ge=1, le=500)) -> list[dict[str, Any]]:
        local_node_num = _resolved_local_node_num(settings, collector)
        return public_chat_messages_payload(
            repository.list_chat_messages(limit=min(limit, PUBLIC_CHAT_LIMIT), primary_only=True),
            local_node_num=local_node_num,
        )

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
    async def mesh_routes(
        since: str | None = None,
        limit: int = Query(default=PUBLIC_MESH_ROUTES_LIMIT, ge=1, le=PUBLIC_MESH_ROUTES_LIMIT_MAX),
    ) -> dict[str, Any]:
        return repository.get_mesh_routes(
            since=_bounded_routes_since(since),
            limit=limit,
            primary_only=True,
        )

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
        local_node_num = _resolved_local_node_num(settings, collector)
        node = repository.get_node(node_num, primary_only=True)
        if node is None:
            raise HTTPException(status_code=404, detail="node not found")
        last_traceroute_attempt = _traceroute_attempt_with_route(
            repository,
            target_node_num=node_num,
            attempt=repository.get_last_traceroute_attempt_for_node(node_num),
        )
        last_successful_traceroute_attempt = _traceroute_attempt_with_route(
            repository,
            target_node_num=node_num,
            attempt=repository.get_last_successful_traceroute_attempt_for_node(node_num),
        )
        latest_complete_traceroute = repository.get_latest_complete_traceroute_for_node(
            node_num,
            primary_only=True,
        )
        return public_node_detail_payload(
            node,
            insights=repository.get_node_insights(node_num, primary_only=True),
            recent_packets=repository.list_recent_packets_from_node(
                node_num,
                limit=PUBLIC_NODE_RECENT_PACKETS_LIMIT,
                primary_only=True,
            ),
            metric_history=repository.list_node_metric_history(
                node_num,
                primary_only=True,
                limit=24,
            ),
            local_node_num=local_node_num,
            last_traceroute_attempt=last_traceroute_attempt,
            last_successful_traceroute_attempt=last_successful_traceroute_attempt,
            latest_complete_traceroute=latest_complete_traceroute,
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
