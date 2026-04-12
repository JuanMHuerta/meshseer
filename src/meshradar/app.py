from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from meshradar.autotrace import AutoTracerouteConfig, AutoTracerouteService
from meshradar.channels import LONGFAST_CHANNEL_NAME, is_primary_channel
from meshradar.clock import utc_now_iso
from meshradar.collector import CollectorCallbacks, CollectorStatus, MeshtasticReceiver
from meshradar.config import Settings
from meshradar.events import EventBroker
from meshradar.models import NodeRecord, PacketRecord
from meshradar.public_api import (
    collector_status_payload,
    public_mesh_summary_payload,
    public_node_detail_payload,
    public_nodes_payload,
    public_packet_payload,
    public_packets_payload,
    public_receiver_payload,
)
from meshradar.storage import MeshRepository


STATIC_DIR = Path(__file__).resolve().parent / "static"
RECEIVER_UTILIZATION_WINDOW_MINUTES = 10


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
    repository = repository or MeshRepository(settings.db_path)
    event_broker = event_broker or EventBroker()

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
        if start_collector:
            collector.start()
            app.state.collector_started = True
        if start_autotrace_service:
            autotrace_service.start()
            app.state.autotrace_service_started = True
            if settings.autotrace_enabled:
                autotrace_service.enable()
        try:
            yield
        finally:
            if app.state.autotrace_service_started:
                autotrace_service.stop()
                app.state.autotrace_service_started = False
            if app.state.collector_started:
                collector.stop()
                app.state.collector_started = False

    app = FastAPI(title="Meshradar", lifespan=lifespan)
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

    def admin_unauthorized() -> HTTPException:
        return HTTPException(
            status_code=401,
            detail="admin authorization required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def require_admin_bearer(authorization: str | None = Header(default=None)) -> None:
        expected = settings.admin_bearer_token
        if expected is None:
            raise HTTPException(status_code=404, detail="not found")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token or not secrets.compare_digest(token, expected):
            raise admin_unauthorized()

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
        return public_packets_payload(repository.list_chat_messages(limit=limit, primary_only=True))

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
        await websocket.accept()
        try:
            async with event_broker.subscription() as queue:
                while True:
                    event = await queue.get()
                    await websocket.send_text(json.dumps(event))
        except WebSocketDisconnect:
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
        async def admin_autotrace_enable() -> dict[str, Any]:
            autotrace_service.enable()
            return autotrace_service.status()

        @admin_router.post("/mesh/autotrace/disable")
        async def admin_autotrace_disable() -> dict[str, Any]:
            autotrace_service.disable()
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
