import base64
import json
import logging
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from meshtastic.protobuf import mesh_pb2
from starlette import status
from starlette.websockets import WebSocketDisconnect

from meshseer.app import create_app
from meshseer.channels import BROADCAST_NODE_NUM
from meshseer.collector import CollectorStatus
from meshseer.config import Settings
from meshseer.models import NodeRecord, PacketRecord
from meshseer.storage import KPI_ACTIVE_NODES_WINDOW_MINUTES, MeshRepository


ADMIN_TOKEN = "test-admin-token"


class StubCollector:
    def __init__(self, *, local_node_num=None):
        self.started = False
        self.stopped = False
        self.status = CollectorStatus(state="connected", connected=True, detail=None)
        self._local_node_num = local_node_num

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def current_status(self):
        return self.status

    def local_node_num(self):
        return self._local_node_num


class StubAutotraceService:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.enabled = False
        self.snapshot = {
            "enabled": False,
            "running": False,
            "local_node_num": 101,
            "interval_seconds": 300,
            "cooldown_hours": 24,
            "ack_only_cooldown_hours": 6,
            "target_window_hours": 24,
            "response_timeout_seconds": 20,
            "eligible_targets": 2,
            "last_attempt": None,
            "recent_attempts": [],
        }

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def enable(self):
        self.enabled = True
        self.snapshot["enabled"] = True
        self.snapshot["running"] = True

    def disable(self):
        self.enabled = False
        self.snapshot["enabled"] = False
        self.snapshot["running"] = False

    def status(self):
        return dict(self.snapshot)


def encode_neighborinfo_payload(node_id: int, neighbors: list[tuple[int, float, int]]) -> str:
    message = mesh_pb2.NeighborInfo(node_id=node_id)
    for neighbor_node_id, snr, last_rx_time in neighbors:
        item = message.neighbors.add()
        item.node_id = neighbor_node_id
        item.snr = snr
        item.last_rx_time = last_rx_time
    return base64.b64encode(message.SerializeToString()).decode("ascii")


def encode_traceroute_payload(
    *,
    route: list[int] | None = None,
    snr_towards: list[int] | None = None,
    route_back: list[int] | None = None,
    snr_back: list[int] | None = None,
) -> str:
    message = mesh_pb2.RouteDiscovery()
    message.route.extend(route or [])
    message.snr_towards.extend(snr_towards or [])
    message.route_back.extend(route_back or [])
    message.snr_back.extend(snr_back or [])
    return base64.b64encode(message.SerializeToString()).decode("ascii")


def admin_headers(token: str = ADMIN_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def websocket_headers(origin: str = "http://testserver") -> dict[str, str]:
    return {"origin": origin}


def build_app(tmp_path, *, admin_token: str | None = None, extra_env: dict[str, str] | None = None):
    repo = MeshRepository(tmp_path / "mesh.db")
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=11,
            received_at="2026-03-30T12:00:00Z",
            from_node_num=101,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=3,
            hop_start=3,
            rx_snr=6.5,
            rx_rssi=-91,
            text_preview="hello mesh",
            payload_base64="aGVsbG8=",
            raw_json='{"id":11}',
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=12,
            received_at="2026-03-30T12:05:00Z",
            from_node_num=202,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=2,
            hop_limit=2,
            rx_snr=1.5,
            text_preview="other channel",
            payload_base64="b3RoZXI=",
            raw_json='{"id":12,"channel":2}',
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=101,
            node_id="!00000065",
            short_name="ALFA",
            long_name="Alpha Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:00:00Z",
            last_snr=6.5,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:00:00Z",
            hops_away=0,
            via_mqtt=False,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=202,
            node_id="!000000ca",
            short_name="BETA",
            long_name="Beta Node",
            hardware_model="HELTEC",
            role="CLIENT",
            channel_index=2,
            last_heard_at="2026-03-30T12:05:00Z",
            last_snr=1.5,
            latitude=11.0,
            longitude=-84.2,
            altitude=20.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202,"channel":2}',
            updated_at="2026-03-30T12:05:00Z",
        )
    )
    collector = StubCollector()
    env = {
        "MESHSEER_DB_PATH": str(tmp_path / "mesh.db"),
        "MESHSEER_LOCAL_NODE_NUM": "101",
    }
    if admin_token is not None:
        env["MESHSEER_ADMIN_BEARER_TOKEN"] = admin_token
    if extra_env is not None:
        env.update(extra_env)
    app = create_app(
        Settings.from_env(env),
        repository=repo,
        collector=collector,
        start_collector=False,
        start_autotrace_service=False,
    )
    return app, collector


def test_api_routes_and_filters(tmp_path):
    app, collector = build_app(tmp_path, admin_token=ADMIN_TOKEN)

    with TestClient(app) as client:
        health = client.get("/api/health")
        packets = client.get("/api/packets", params={"from_node": 101, "portnum": "TEXT_MESSAGE_APP"})
        chat = client.get("/api/chat")
        node = client.get("/api/nodes/101")
        hidden_node = client.get("/api/nodes/202")
        admin_packet = client.get("/api/admin/packets/1", headers=admin_headers())
        hidden_admin_packet = client.get("/api/admin/packets/2", headers=admin_headers())
        admin_nodes = client.get("/api/admin/nodes", headers=admin_headers())
        index = client.get("/")

    assert collector.started is False
    assert health.status_code == 200
    assert health.json()["collector"]["state"] == "connected"
    assert "detail" not in health.json()["collector"]
    assert health.json()["perspective"]["channel_name"] == "LongFast"
    assert health.json()["perspective"]["local_node_num"] == 101
    assert health.json()["perspective"]["label"] == "ALFA"
    assert "database" not in health.json()
    assert packets.json()[0]["text_preview"] == "hello mesh"
    assert packets.json()[0]["path_label"] == "Direct"
    assert packets.json()[0]["path_tone"] == "direct"
    assert "mesh_packet_id" not in packets.json()[0]
    assert "channel_index" not in packets.json()[0]
    assert "hop_limit" not in packets.json()[0]
    assert "hop_start" not in packets.json()[0]
    assert "rx_snr" not in packets.json()[0]
    assert "via_mqtt" not in packets.json()[0]
    assert "from_node_id" not in packets.json()[0]
    assert "payload_base64" not in packets.json()[0]
    assert "raw_json" not in packets.json()[0]
    assert len(chat.json()) == 1
    assert chat.json()[0]["text_preview"] == "hello mesh"
    assert chat.json()[0]["sender_label"] == "ALFA"
    assert chat.json()[0]["path_label"] == "Direct"
    assert "from_node_num" not in chat.json()[0]
    assert "mesh_packet_id" not in chat.json()[0]
    assert node.json()["node"]["node_num"] == 101
    assert "raw_json" not in node.json()["node"]
    assert node.json()["recent_packets"][0]["path_label"] == "Direct"
    assert "hop_limit" not in node.json()["recent_packets"][0]
    assert "payload_base64" not in node.json()["recent_packets"][0]
    assert hidden_node.status_code == 404
    assert admin_packet.json()["mesh_packet_id"] == 11
    assert admin_packet.json()["raw_json"] == '{"id":11}'
    assert hidden_admin_packet.status_code == 404
    assert len(admin_nodes.json()) == 1
    assert admin_nodes.json()[0]["short_name"] == "ALFA"
    assert admin_nodes.json()[0]["raw_json"] == '{"num":101}'
    assert "Meshseer" in index.text


def test_docs_routes_are_hidden_in_production(tmp_path):
    development_path = tmp_path / "development"
    production_path = tmp_path / "production"
    development_path.mkdir()
    production_path.mkdir()

    development_app, _collector = build_app(development_path)
    production_app, _collector = build_app(
        production_path,
        extra_env={"MESHSEER_ENV": "production"},
    )

    with TestClient(development_app) as client:
        docs = client.get("/docs")
        redoc = client.get("/redoc")
        openapi = client.get("/openapi.json")

    assert docs.status_code == 200
    assert redoc.status_code == 200
    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "Meshseer"

    with TestClient(production_app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_responses_include_security_headers_and_cache_policy(tmp_path):
    app, _collector = build_app(tmp_path, admin_token=ADMIN_TOKEN)

    with TestClient(app) as client:
        index = client.get("/")
        health = client.get("/api/health")
        static_js = client.get("/static/app.js")

    for response in (index, health, static_js):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "same-origin"
        assert response.headers["permissions-policy"] == "geolocation=(), microphone=(), camera=()"
        assert response.headers["x-frame-options"] == "DENY"

    assert "default-src 'self'" in index.headers["content-security-policy"]
    assert "connect-src 'self' ws: wss:" in health.headers["content-security-policy"]
    assert index.headers["cache-control"] == "no-store"
    assert health.headers["cache-control"] == "no-store"
    assert static_js.headers["cache-control"] == "no-cache"


def test_nodes_roster_exposes_supported_filter_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 3, 30, 12, 30, tzinfo=UTC),
    )

    repo = MeshRepository(tmp_path / "mesh.db")
    node_rows = [
        NodeRecord(
            node_num=101,
            node_id="!00000065",
            short_name="ALFA",
            long_name="Alpha Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:28:00Z",
            last_snr=6.5,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:28:00Z",
            hops_away=0,
            via_mqtt=False,
        ),
        NodeRecord(
            node_num=202,
            node_id="!000000ca",
            short_name="BETA",
            long_name="Beta Node",
            hardware_model="HELTEC",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:20:00Z",
            last_snr=4.8,
            latitude=10.3,
            longitude=-84.12,
            altitude=16.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202}',
            updated_at="2026-03-30T12:20:00Z",
            hops_away=1,
            via_mqtt=False,
        ),
        NodeRecord(
            node_num=303,
            node_id="!0000012f",
            short_name="TRKR",
            long_name="Tracker Node",
            hardware_model="TRACKER T1000",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-29T11:00:00Z",
            last_snr=2.1,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":303}',
            updated_at="2026-03-29T11:00:00Z",
            hops_away=2,
            via_mqtt=False,
        ),
        NodeRecord(
            node_num=404,
            node_id="!00000194",
            short_name="MQTT",
            long_name="MQTT Bridge",
            hardware_model="PI GATEWAY",
            role="ROUTER",
            channel_index=0,
            last_heard_at="2026-03-30T12:26:00Z",
            last_snr=None,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":404,"viaMqtt":true}',
            updated_at="2026-03-30T12:26:00Z",
            hops_away=None,
            via_mqtt=True,
        ),
        NodeRecord(
            node_num=505,
            node_id="!000001f9",
            short_name="MID",
            long_name="Midrange Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T10:31:00Z",
            last_snr=2.9,
            latitude=10.33,
            longitude=-84.15,
            altitude=17.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":505}',
            updated_at="2026-03-30T10:31:00Z",
            hops_away=2,
            via_mqtt=False,
        ),
        NodeRecord(
            node_num=909,
            node_id="!0000038d",
            short_name="HIDDEN",
            long_name="Other Channel",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=2,
            last_heard_at="2026-03-30T12:27:00Z",
            last_snr=1.0,
            latitude=10.5,
            longitude=-84.4,
            altitude=22.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":909,"channel":2}',
            updated_at="2026-03-30T12:27:00Z",
            hops_away=1,
            via_mqtt=False,
        ),
    ]
    for node in node_rows:
        repo.upsert_node(node)

    packet_rows = [
        PacketRecord(
            mesh_packet_id=20,
            received_at="2026-03-30T12:10:00Z",
            from_node_num=202,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=2,
            rx_snr=4.8,
            rx_rssi=-96,
            text_preview="beta text",
            payload_base64=None,
            raw_json='{"id":20}',
            via_mqtt=False,
        ),
        PacketRecord(
            mesh_packet_id=21,
            received_at="2026-03-30T12:12:00Z",
            from_node_num=202,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="POSITION_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=2,
            rx_snr=4.7,
            rx_rssi=-97,
            text_preview=None,
            payload_base64=None,
            raw_json='{"id":21}',
            via_mqtt=False,
        ),
        PacketRecord(
            mesh_packet_id=22,
            received_at="2026-03-30T02:00:00Z",
            from_node_num=303,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=3,
            rx_snr=2.0,
            rx_rssi=-104,
            text_preview="tracker text",
            payload_base64=None,
            raw_json='{"id":22}',
            via_mqtt=False,
        ),
        PacketRecord(
            mesh_packet_id=23,
            received_at="2026-03-30T12:25:00Z",
            from_node_num=404,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=None,
            hop_start=None,
            rx_snr=None,
            rx_rssi=None,
            text_preview="mqtt text",
            payload_base64=None,
            raw_json='{"id":23,"viaMqtt":true}',
            via_mqtt=True,
        ),
        PacketRecord(
            mesh_packet_id=24,
            received_at="2026-03-30T12:27:00Z",
            from_node_num=909,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=2,
            hop_limit=1,
            hop_start=1,
            rx_snr=1.1,
            rx_rssi=-105,
            text_preview="hidden",
            payload_base64=None,
            raw_json='{"id":24,"channel":2}',
            via_mqtt=False,
        ),
    ]
    for packet in packet_rows:
        repo.insert_packet(packet)

    app = create_app(
        Settings.from_env(
            {
                "MESHSEER_DB_PATH": str(tmp_path / "mesh.db"),
                "MESHSEER_LOCAL_NODE_NUM": "101",
            }
        ),
        repository=repo,
        collector=StubCollector(local_node_num=101),
        start_collector=False,
        start_autotrace_service=False,
    )

    with TestClient(app) as client:
        roster = client.get("/api/nodes/roster")

    assert roster.status_code == 200
    items = {item["node_num"]: item for item in roster.json()}
    assert set(items) == {101, 202, 303, 404, 505}
    assert items[101]["status"] == "local"
    assert items[101]["is_active"] is True
    assert items[101]["is_direct_rf"] is False
    assert items[101]["is_mapped"] is True
    assert items[202]["status"] == "direct"
    assert items[202]["is_direct_rf"] is True
    assert items[202]["is_active"] is True
    assert items[202]["activity_count_60m"] == 2
    assert items[303]["status"] == "relayed"
    assert items[303]["is_active"] is False
    assert items[303]["is_stale"] is True
    assert items[303]["activity_count_60m"] == 0
    assert items[404]["status"] == "mqtt"
    assert items[404]["is_mqtt"] is True
    assert items[404]["activity_count_60m"] == 1
    assert items[505]["status"] == "relayed"
    assert items[505]["is_active"] is True
    assert items[505]["activity_count_60m"] == 0
    assert "mobility" not in items[101]
    assert "has_text_traffic" not in items[202]


def test_health_uses_collector_local_node_num_when_env_override_is_absent(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    repo.upsert_node(
        NodeRecord(
            node_num=101,
            node_id="!00000065",
            short_name="ALFA",
            long_name="Alpha Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:00:00Z",
            last_snr=6.5,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:00:00Z",
            hops_away=0,
            via_mqtt=False,
        )
    )
    collector = StubCollector(local_node_num=101)
    app = create_app(
        Settings.from_env({"MESHSEER_DB_PATH": str(tmp_path / "mesh.db")}),
        repository=repo,
        collector=collector,
        start_collector=False,
        start_autotrace_service=False,
    )

    with TestClient(app) as client:
        health = client.get("/api/health")

    assert health.status_code == 200
    assert health.json()["perspective"]["local_node_num"] == 101
    assert health.json()["perspective"]["label"] == "ALFA"


def test_mesh_summary_and_node_insights_expose_passive_path_data(tmp_path):
    app, _collector = build_app(tmp_path)
    repo = app.state.repository

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=13,
            received_at="2026-03-30T12:08:00Z",
            from_node_num=303,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="POSITION_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=4,
            rx_snr=2.5,
            rx_rssi=-101,
            text_preview=None,
            payload_base64=None,
            raw_json='{"id":13,"hopStart":4,"relayNode":404}',
            relay_node=404,
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=14,
            received_at="2026-03-30T12:09:00Z",
            from_node_num=404,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="NODEINFO_APP",
            channel_index=0,
            hop_limit=1,
            hop_start=1,
            rx_snr=0.5,
            rx_rssi=-108,
            text_preview=None,
            payload_base64=None,
            raw_json='{"id":14,"viaMqtt":true}',
            via_mqtt=True,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=303,
            node_id="!0000012f",
            short_name="GAMMA",
            long_name="Gamma Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:08:00Z",
            last_snr=2.5,
            latitude=10.4,
            longitude=-84.15,
            altitude=18.0,
            battery_level=74.0,
            channel_utilization=5.2,
            air_util_tx=1.8,
            raw_json='{"num":303,"hopsAway":2}',
            updated_at="2026-03-30T12:08:00Z",
            hops_away=2,
            via_mqtt=False,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=404,
            node_id="!00000194",
            short_name="MQTT",
            long_name="MQTT Bridge",
            hardware_model="MQTT",
            role="ROUTER",
            channel_index=0,
            last_heard_at="2026-03-30T12:09:00Z",
            last_snr=0.5,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":404,"viaMqtt":true}',
            updated_at="2026-03-30T12:09:00Z",
            hops_away=None,
            via_mqtt=True,
        )
    )

    with TestClient(app) as client:
        summary = client.get("/api/mesh/summary")
        node = client.get("/api/nodes/303")

    assert summary.status_code == 200
    assert summary.json()["nodes"]["multi_hop"] == 1
    assert summary.json()["nodes"]["mqtt"] == 1
    assert summary.json()["traffic"]["direct"] == 1
    assert summary.json()["traffic"]["relayed"] == 1
    assert summary.json()["traffic"]["mqtt"] == 1
    assert "top_senders" not in summary.json()
    assert node.json()["node"]["hops_away"] == 2
    assert node.json()["insights"]["relayed_packets"] == 1
    assert node.json()["insights"]["last_path"] == "2 hops"


def test_mesh_summary_exposes_receiver_utilization_history(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 3, 30, 12, 15, tzinfo=UTC),
    )

    app, _collector = build_app(tmp_path)
    repo = app.state.repository

    repo.upsert_node(
        NodeRecord(
            node_num=101,
            node_id="!00000065",
            short_name="ALFA",
            long_name="Alpha Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:10:00Z",
            last_snr=6.8,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=88.0,
            channel_utilization=11.8,
            air_util_tx=1.4,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:10:00Z",
            hops_away=0,
            via_mqtt=False,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=101,
            node_id="!00000065",
            short_name="ALFA",
            long_name="Alpha Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:15:00Z",
            last_snr=7.1,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=87.0,
            channel_utilization=16.4,
            air_util_tx=2.1,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:15:00Z",
            hops_away=0,
            via_mqtt=False,
        )
    )

    with TestClient(app) as client:
        summary = client.get("/api/mesh/summary")

    assert summary.status_code == 200
    assert summary.json()["receiver"] == {
        "node_num": 101,
        "label": "ALFA",
        "updated_at": "2026-03-30T12:15:00Z",
        "channel_utilization": 16.4,
        "air_util_tx": 2.1,
        "history": [
            {
                "recorded_at": "2026-03-30T12:10:00Z",
                "channel_utilization": 11.8,
                "air_util_tx": 1.4,
            },
            {
                "recorded_at": "2026-03-30T12:15:00Z",
                "channel_utilization": 16.4,
                "air_util_tx": 2.1,
            },
        ],
        "windowed_utilization": {
            "window_minutes": 10,
            "channel_utilization_avg": 14.1,
            "air_util_tx_avg": 1.75,
            "sample_count": 2,
        },
    }


def test_mesh_summary_exposes_windowed_activity(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 3, 30, 12, 30, tzinfo=UTC),
    )

    repo = MeshRepository(tmp_path / "mesh.db")
    repo.upsert_node(
        NodeRecord(
            node_num=101,
            node_id="!00000065",
            short_name="ALFA",
            long_name="Alpha Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:28:00Z",
            last_snr=6.1,
            latitude=10.25,
            longitude=-84.10,
            altitude=15.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:28:00Z",
            hops_away=0,
            via_mqtt=False,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=202,
            node_id="!000000ca",
            short_name="BETA",
            long_name="Beta Node",
            hardware_model="HELTEC",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:12:00Z",
            last_snr=5.2,
            latitude=10.30,
            longitude=-84.11,
            altitude=16.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202}',
            updated_at="2026-03-30T12:12:00Z",
            hops_away=1,
            via_mqtt=False,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=303,
            node_id="!0000012f",
            short_name="GAMMA",
            long_name="Gamma Node",
            hardware_model="RAK4631",
            role="ROUTER",
            channel_index=0,
            last_heard_at="2026-03-30T12:22:00Z",
            last_snr=3.8,
            latitude=10.34,
            longitude=-84.13,
            altitude=18.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":303}',
            updated_at="2026-03-30T12:22:00Z",
            hops_away=2,
            via_mqtt=False,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=404,
            node_id="!00000194",
            short_name="MQTT",
            long_name="MQTT Bridge",
            hardware_model="PI GATEWAY",
            role="ROUTER",
            channel_index=0,
            last_heard_at="2026-03-30T12:25:00Z",
            last_snr=None,
            latitude=10.36,
            longitude=-84.14,
            altitude=19.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":404,"viaMqtt":true}',
            updated_at="2026-03-30T12:25:00Z",
            hops_away=None,
            via_mqtt=True,
        )
    )

    for node_num in (505, 606, 707):
        repo.upsert_node(
            NodeRecord(
                node_num=node_num,
                node_id=f"!{node_num:08x}",
                short_name=f"N{node_num}",
                long_name=f"Node {node_num}",
                hardware_model="TBEAM",
                role="CLIENT",
                channel_index=0,
                last_heard_at="2026-03-30T11:20:00Z",
                last_snr=2.0,
                latitude=10.40,
                longitude=-84.20,
                altitude=20.0,
                battery_level=None,
                channel_utilization=None,
                air_util_tx=None,
                raw_json=f'{{"num":{node_num}}}',
                updated_at="2026-03-30T11:20:00Z",
                hops_away=2,
                via_mqtt=False,
            )
        )

    packets = [
        PacketRecord(
            mesh_packet_id=20,
            received_at="2026-03-30T12:10:00Z",
            from_node_num=202,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=2,
            rx_snr=5.2,
            rx_rssi=-96,
            text_preview="direct current 1",
            payload_base64=None,
            raw_json='{"id":20}',
            via_mqtt=False,
        ),
        PacketRecord(
            mesh_packet_id=21,
            received_at="2026-03-30T12:12:00Z",
            from_node_num=202,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="POSITION_APP",
            channel_index=0,
            hop_limit=3,
            hop_start=3,
            rx_snr=4.8,
            rx_rssi=-97,
            text_preview=None,
            payload_base64=None,
            raw_json='{"id":21}',
            via_mqtt=False,
        ),
        PacketRecord(
            mesh_packet_id=22,
            received_at="2026-03-30T12:20:00Z",
            from_node_num=303,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="NODEINFO_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=4,
            rx_snr=3.8,
            rx_rssi=-102,
            text_preview=None,
            payload_base64=None,
            raw_json='{"id":22}',
            via_mqtt=False,
        ),
        PacketRecord(
            mesh_packet_id=23,
            received_at="2026-03-30T12:22:00Z",
            from_node_num=303,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=1,
            rx_snr=3.1,
            rx_rssi=-104,
            text_preview="invalid hops",
            payload_base64=None,
            raw_json='{"id":23}',
            via_mqtt=False,
        ),
        PacketRecord(
            mesh_packet_id=24,
            received_at="2026-03-30T12:25:00Z",
            from_node_num=404,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=None,
            hop_start=None,
            rx_snr=None,
            rx_rssi=None,
            text_preview="mqtt current",
            payload_base64=None,
            raw_json='{"id":24,"viaMqtt":true}',
            via_mqtt=True,
        ),
        PacketRecord(
            mesh_packet_id=25,
            received_at="2026-03-30T11:00:00Z",
            from_node_num=505,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=3,
            hop_start=3,
            rx_snr=4.0,
            rx_rssi=-98,
            text_preview="direct previous",
            payload_base64=None,
            raw_json='{"id":25}',
            via_mqtt=False,
        ),
        PacketRecord(
            mesh_packet_id=26,
            received_at="2026-03-30T11:15:00Z",
            from_node_num=606,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="NODEINFO_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=3,
            rx_snr=2.9,
            rx_rssi=-105,
            text_preview=None,
            payload_base64=None,
            raw_json='{"id":26}',
            via_mqtt=False,
        ),
        PacketRecord(
            mesh_packet_id=27,
            received_at="2026-03-30T11:20:00Z",
            from_node_num=707,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=None,
            hop_start=None,
            rx_snr=None,
            rx_rssi=None,
            text_preview="mqtt previous",
            payload_base64=None,
            raw_json='{"id":27,"viaMqtt":true}',
            via_mqtt=True,
        ),
    ]
    for packet in packets:
        repo.insert_packet(packet)

    app = create_app(
        Settings.from_env(
            {
                "MESHSEER_DB_PATH": str(tmp_path / "mesh.db"),
                "MESHSEER_LOCAL_NODE_NUM": "101",
            }
        ),
        repository=repo,
        collector=StubCollector(local_node_num=101),
        start_collector=False,
        start_autotrace_service=False,
    )

    with TestClient(app) as client:
        summary = client.get("/api/mesh/summary")

    assert summary.status_code == 200
    assert summary.json()["nodes"]["active_3h"] == 7
    assert summary.json()["nodes"]["active_window_minutes"] == KPI_ACTIVE_NODES_WINDOW_MINUTES
    assert summary.json()["windowed_activity"] == {
        "window_minutes": 60,
        "current": {
            "active_nodes": 3,
            "packet_count": 5,
            "direct_packets": 2,
            "relayed_packets": 1,
            "mqtt_packets": 1,
            "avg_hops": 2 / 3,
        },
        "previous": {
            "active_nodes": 3,
            "packet_count": 3,
            "direct_packets": 1,
            "relayed_packets": 1,
            "mqtt_packets": 1,
            "avg_hops": 0.5,
        },
    }


def test_mesh_summary_counts_active_nodes_over_last_3_hours(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 3, 30, 12, 30, tzinfo=UTC),
    )

    repo = MeshRepository(tmp_path / "mesh.db")
    for node_num, last_heard_at in (
        (101, "2026-03-30T12:29:00Z"),
        (202, "2026-03-30T09:30:00Z"),
        (303, "2026-03-30T09:29:00Z"),
        (404, "2026-03-30T11:45:00Z"),
    ):
        repo.upsert_node(
            NodeRecord(
                node_num=node_num,
                node_id=f"!{node_num:08x}",
                short_name=f"N{node_num}",
                long_name=f"Node {node_num}",
                hardware_model="TBEAM",
                role="CLIENT",
                channel_index=0,
                last_heard_at=last_heard_at,
                last_snr=5.0,
                latitude=10.0,
                longitude=-84.0,
                altitude=10.0,
                battery_level=None,
                channel_utilization=None,
                air_util_tx=None,
                raw_json=f'{{"num":{node_num}}}',
                updated_at=last_heard_at,
                hops_away=0,
                via_mqtt=False,
            )
        )

    app = create_app(
        Settings.from_env(
            {
                "MESHSEER_DB_PATH": str(tmp_path / "mesh.db"),
                "MESHSEER_LOCAL_NODE_NUM": "101",
            }
        ),
        repository=repo,
        collector=StubCollector(local_node_num=101),
        start_collector=False,
        start_autotrace_service=False,
    )

    with TestClient(app) as client:
        summary = client.get("/api/mesh/summary")

    assert summary.status_code == 200
    assert summary.json()["nodes"]["total"] == 4
    assert summary.json()["nodes"]["active_3h"] == 3
    assert summary.json()["nodes"]["active_window_minutes"] == KPI_ACTIVE_NODES_WINDOW_MINUTES


def test_mesh_summary_exposes_empty_receiver_windowed_utilization_when_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 3, 30, 12, 30, tzinfo=UTC),
    )

    app, _collector = build_app(tmp_path)
    repo = app.state.repository

    for updated_at, channel_utilization, air_util_tx in (
        ("2026-03-30T12:10:00Z", 11.8, 1.4),
        ("2026-03-30T12:15:00Z", 16.4, 2.1),
    ):
        repo.upsert_node(
            NodeRecord(
                node_num=101,
                node_id="!00000065",
                short_name="ALFA",
                long_name="Alpha Node",
                hardware_model="TBEAM",
                role="CLIENT",
                channel_index=0,
                last_heard_at=updated_at,
                last_snr=6.8,
                latitude=10.25,
                longitude=-84.1,
                altitude=15.0,
                battery_level=88.0,
                channel_utilization=channel_utilization,
                air_util_tx=air_util_tx,
                raw_json='{"num":101}',
                updated_at=updated_at,
                hops_away=0,
                via_mqtt=False,
            )
        )

    with TestClient(app) as client:
        summary = client.get("/api/mesh/summary")

    assert summary.status_code == 200
    assert summary.json()["receiver"]["windowed_utilization"] == {
        "window_minutes": 10,
        "channel_utilization_avg": None,
        "air_util_tx_avg": None,
        "sample_count": 0,
    }


def test_packet_ingest_updates_node_activity_without_node_update(tmp_path):
    app, _collector = build_app(tmp_path)
    repo = app.state.repository
    packet = PacketRecord(
        mesh_packet_id=77,
        received_at="2026-03-30T12:15:00Z",
        from_node_num=707,
        to_node_num=BROADCAST_NODE_NUM,
        portnum="TEXT_MESSAGE_APP",
        channel_index=None,
        hop_limit=1,
        rx_snr=4.2,
        text_preview="new sender",
        payload_base64=None,
        raw_json='{"fromId":"!000002c3"}',
    )
    repo.insert_packet(packet)
    repo.observe_packet_node_activity(packet)

    with TestClient(app) as client:
        node = client.get("/api/nodes/707")

    assert node.status_code == 200
    assert node.json()["node"]["node_id"] == "!000002c3"
    assert node.json()["node"]["last_heard_at"] == "2026-03-30T12:15:00Z"
    assert node.json()["node"]["last_snr"] == 4.2


def test_mesh_links_exposes_mutual_neighbor_reports(tmp_path):
    app, _collector = build_app(tmp_path, admin_token=ADMIN_TOKEN)
    repo = app.state.repository

    repo.upsert_node(
        NodeRecord(
            node_num=303,
            node_id="!0000012f",
            short_name="GAMMA",
            long_name="Gamma Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:11:00Z",
            last_snr=3.5,
            latitude=10.4,
            longitude=-84.15,
            altitude=18.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":303}',
            updated_at="2026-03-30T12:11:00Z",
            hops_away=1,
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=15,
            received_at="2026-03-30T12:10:00Z",
            from_node_num=101,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="NEIGHBORINFO_APP",
            channel_index=0,
            hop_limit=1,
            hop_start=1,
            rx_snr=4.5,
            rx_rssi=-95,
            text_preview=None,
            payload_base64=encode_neighborinfo_payload(101, [(303, 5.0, 1_743_337_800)]),
            raw_json='{"decoded":{"neighborinfo":{"neighbors":[{"nodeId":303,"snr":5.0}]}}}',
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=16,
            received_at="2026-03-30T12:11:00Z",
            from_node_num=303,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="NEIGHBORINFO_APP",
            channel_index=0,
            hop_limit=1,
            hop_start=1,
            rx_snr=3.5,
            rx_rssi=-96,
            text_preview=None,
            payload_base64=encode_neighborinfo_payload(303, [(101, 3.0, 1_743_337_860)]),
            raw_json='{"decoded":{"neighborinfo":{"neighbors":[{"nodeId":101,"snr":3.0}]}}}',
            via_mqtt=False,
        )
    )

    with TestClient(app) as client:
        links = client.get("/api/admin/mesh/links", headers=admin_headers())

    assert links.status_code == 200
    assert links.json()["stats"] == {"total": 1, "mutual": 1, "one_way": 0}
    assert links.json()["neighbor_links"][0]["node_a_num"] == 101
    assert links.json()["neighbor_links"][0]["node_b_num"] == 303
    assert links.json()["neighbor_links"][0]["mutual"] is True
    assert links.json()["neighbor_links"][0]["a_to_b"]["report_count"] == 1
    assert links.json()["neighbor_links"][0]["b_to_a"]["report_count"] == 1


def test_mesh_routes_expose_passive_traceroute_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "meshseer.app.utc_now",
        lambda: datetime(2026, 3, 30, 12, 30, tzinfo=UTC),
    )

    app, _collector = build_app(tmp_path)
    repo = app.state.repository

    repo.upsert_node(
        NodeRecord(
            node_num=202,
            node_id="!000000ca",
            short_name="BETA",
            long_name="Beta Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:11:30Z",
            last_snr=4.0,
            latitude=10.3,
            longitude=-84.12,
            altitude=16.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202}',
            updated_at="2026-03-30T12:11:30Z",
            hops_away=1,
            via_mqtt=False,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=303,
            node_id="!0000012f",
            short_name="GAMMA",
            long_name="Gamma Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:12:00Z",
            last_snr=3.5,
            latitude=10.4,
            longitude=-84.15,
            altitude=18.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":303}',
            updated_at="2026-03-30T12:12:00Z",
            hops_away=2,
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=17,
            received_at="2026-03-30T12:12:00Z",
            from_node_num=303,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=3,
            hop_start=3,
            rx_snr=4.5,
            rx_rssi=-95,
            text_preview=None,
            payload_base64=encode_traceroute_payload(
                route=[202],
                snr_towards=[20, 12],
                route_back=[202],
                snr_back=[16, 8],
            ),
            raw_json="{}",
            via_mqtt=False,
        )
    )

    with TestClient(app) as client:
        routes = client.get("/api/mesh/routes")

    assert routes.status_code == 200
    assert routes.json()["stats"] == {"total": 2, "forward": 1, "return": 1}
    assert routes.json()["routes"][0]["direction"] == "forward"
    assert routes.json()["routes"][0]["path_node_nums"] == [101, 202, 303]
    assert routes.json()["routes"][1]["direction"] == "return"
    assert routes.json()["routes"][1]["path_node_nums"] == [303, 202, 101]


def test_mesh_routes_support_since_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "meshseer.app.utc_now",
        lambda: datetime(2026, 3, 30, 12, 30, tzinfo=UTC),
    )

    app, _collector = build_app(tmp_path)
    repo = app.state.repository

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=17,
            received_at="2026-03-30T06:00:00Z",
            from_node_num=303,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=3,
            hop_start=3,
            rx_snr=4.5,
            rx_rssi=-95,
            text_preview=None,
            payload_base64=encode_traceroute_payload(
                route=[202],
                snr_towards=[20, 12],
                route_back=[202],
                snr_back=[16, 8],
            ),
            raw_json="{}",
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=18,
            received_at="2026-03-30T12:12:00Z",
            from_node_num=404,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=2,
            rx_snr=3.5,
            rx_rssi=-96,
            text_preview=None,
            payload_base64=encode_traceroute_payload(
                route=[202],
                snr_towards=[18, 10],
            ),
            raw_json="{}",
            via_mqtt=False,
        )
    )

    with TestClient(app) as client:
        routes = client.get("/api/mesh/routes", params={"since": "2026-03-30T10:00:00Z"})

    assert routes.status_code == 200
    assert routes.json()["stats"] == {"total": 1, "forward": 1, "return": 0}
    assert routes.json()["routes"][0]["mesh_packet_id"] == 18
    assert routes.json()["routes"][0]["path_node_nums"] == [101, 202, 404]


def test_mesh_routes_default_to_one_week_lookback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "meshseer.app.utc_now",
        lambda: datetime(2026, 3, 30, 12, 30, tzinfo=UTC),
    )

    app, _collector = build_app(tmp_path)
    repo = app.state.repository

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=17,
            received_at="2026-03-20T06:00:00Z",
            from_node_num=303,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=3,
            hop_start=3,
            rx_snr=4.5,
            rx_rssi=-95,
            text_preview=None,
            payload_base64=encode_traceroute_payload(route=[202]),
            raw_json="{}",
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=18,
            received_at="2026-03-28T12:12:00Z",
            from_node_num=404,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=2,
            rx_snr=3.5,
            rx_rssi=-96,
            text_preview=None,
            payload_base64=encode_traceroute_payload(route=[202]),
            raw_json="{}",
            via_mqtt=False,
        )
    )

    with TestClient(app) as client:
        routes = client.get("/api/mesh/routes")

    assert routes.status_code == 200
    assert routes.json()["stats"] == {"total": 1, "forward": 1, "return": 0}
    assert routes.json()["routes"][0]["mesh_packet_id"] == 18
    assert routes.json()["routes"][0]["path_node_nums"] == [101, 202, 404]


def test_mesh_routes_clamps_since_to_one_week_lookback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "meshseer.app.utc_now",
        lambda: datetime(2026, 3, 30, 12, 30, tzinfo=UTC),
    )

    app, _collector = build_app(tmp_path)
    repo = app.state.repository

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=17,
            received_at="2026-03-20T06:00:00Z",
            from_node_num=303,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=3,
            hop_start=3,
            rx_snr=4.5,
            rx_rssi=-95,
            text_preview=None,
            payload_base64=encode_traceroute_payload(route=[202]),
            raw_json="{}",
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=18,
            received_at="2026-03-28T12:12:00Z",
            from_node_num=404,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=2,
            rx_snr=3.5,
            rx_rssi=-96,
            text_preview=None,
            payload_base64=encode_traceroute_payload(route=[202]),
            raw_json="{}",
            via_mqtt=False,
        )
    )

    with TestClient(app) as client:
        routes = client.get("/api/mesh/routes", params={"since": "2026-03-01T00:00:00Z"})

    assert routes.status_code == 200
    assert routes.json()["stats"] == {"total": 1, "forward": 1, "return": 0}
    assert routes.json()["routes"][0]["mesh_packet_id"] == 18
    assert routes.json()["routes"][0]["path_node_nums"] == [101, 202, 404]


def test_admin_routes_require_bearer_and_are_absent_when_unconfigured(tmp_path):
    app_without_admin, _collector = build_app(tmp_path)

    with TestClient(app_without_admin) as client:
        missing_admin = client.get("/api/admin/health")

    assert missing_admin.status_code == 404

    app_with_admin, _collector = build_app(tmp_path, admin_token=ADMIN_TOKEN)

    with TestClient(app_with_admin) as client:
        missing_header = client.get("/api/admin/health")
        wrong_header = client.get("/api/admin/health", headers=admin_headers("wrong-token"))
        allowed = client.get("/api/admin/health", headers=admin_headers())

    assert missing_header.status_code == 401
    assert missing_header.headers["www-authenticate"] == "Bearer"
    assert wrong_header.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["database"]["path"].endswith("mesh.db")


def test_auth_websocket_and_autotrace_emit_audit_logs(tmp_path, caplog):
    repo = MeshRepository(tmp_path / "mesh.db")
    collector = StubCollector(local_node_num=101)
    autotrace_service = StubAutotraceService()
    app = create_app(
        Settings.from_env(
            {
                "MESHSEER_DB_PATH": str(tmp_path / "mesh.db"),
                "MESHSEER_ADMIN_BEARER_TOKEN": ADMIN_TOKEN,
            }
        ),
        repository=repo,
        collector=collector,
        autotrace_service=autotrace_service,
        start_collector=False,
        start_autotrace_service=False,
    )
    caplog.set_level(logging.INFO, logger="meshseer.audit")

    with TestClient(app) as client:
        for _ in range(5):
            response = client.get("/api/admin/health")
            assert response.status_code == 401

        allowed = client.get("/api/admin/health", headers=admin_headers())
        assert allowed.status_code == 200

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/events", headers=websocket_headers("https://evil.example")):
                pass

        with client.websocket_connect("/ws/events", headers=websocket_headers()) as websocket:
            client.app.state.event_broker.publish(
                {
                    "type": "packet_received",
                    "ts": "2026-03-30T12:00:00Z",
                    "data": {"mesh_packet_id": 77},
                }
            )
            assert websocket.receive_json()["data"]["mesh_packet_id"] == 77

        client.app.state.event_broker.publish(
            {
                "type": "packet_received",
                "ts": "2026-03-30T12:00:01Z",
                "data": {"mesh_packet_id": 78},
            }
        )
        client.get("/api/health")

        enabled = client.post("/api/admin/mesh/autotrace/enable", headers=admin_headers())
        disabled = client.post("/api/admin/mesh/autotrace/disable", headers=admin_headers())

    assert enabled.status_code == 200
    assert disabled.status_code == 200

    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "meshseer.audit"
    ]

    assert any(event["event"] == "admin_auth_decision" and event["result"] == "denied" for event in events)
    assert any(event["event"] == "admin_auth_decision" and event["result"] == "allowed" for event in events)
    assert any(event["event"] == "admin_auth_repeated_failure" and event["count"] >= 5 for event in events)
    assert any(event["event"] == "websocket_rejected" and event["reason"] == "origin_not_allowed" for event in events)
    assert any(event["event"] == "websocket_connected" for event in events)
    assert any(event["event"] == "websocket_disconnected" and event["reason"] == "client_disconnect" for event in events)
    assert any(event["event"] == "autotrace_enabled" and event["trigger"] == "admin_api" for event in events)
    assert any(event["event"] == "autotrace_disabled" and event["trigger"] == "admin_api" for event in events)


def test_admin_autotrace_api_exposes_status_and_runtime_toggle(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    collector = StubCollector(local_node_num=101)
    autotrace_service = StubAutotraceService()
    app = create_app(
        Settings.from_env(
            {
                "MESHSEER_DB_PATH": str(tmp_path / "mesh.db"),
                "MESHSEER_ADMIN_BEARER_TOKEN": ADMIN_TOKEN,
            }
        ),
        repository=repo,
        collector=collector,
        autotrace_service=autotrace_service,
        start_collector=False,
        start_autotrace_service=False,
    )

    with TestClient(app) as client:
        status_before = client.get("/api/admin/mesh/autotrace", headers=admin_headers())
        enabled = client.post("/api/admin/mesh/autotrace/enable", headers=admin_headers())
        disabled = client.post("/api/admin/mesh/autotrace/disable", headers=admin_headers())

    assert status_before.status_code == 200
    assert status_before.json()["enabled"] is False
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert enabled.json()["running"] is True
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["running"] is False


def test_lifespan_enables_autotrace_when_requested_by_settings(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    collector = StubCollector(local_node_num=101)
    autotrace_service = StubAutotraceService()
    app = create_app(
        Settings.from_env(
            {
                "MESHSEER_DB_PATH": str(tmp_path / "mesh.db"),
                "MESHSEER_ADMIN_BEARER_TOKEN": ADMIN_TOKEN,
                "MESHSEER_AUTOTRACE_ENABLED": "true",
            }
        ),
        repository=repo,
        collector=collector,
        autotrace_service=autotrace_service,
        start_collector=False,
        start_autotrace_service=True,
    )

    with TestClient(app) as client:
        status = client.get("/api/admin/mesh/autotrace", headers=admin_headers())
        assert autotrace_service.started is True
        assert status.status_code == 200
        assert status.json()["enabled"] is True
        assert status.json()["running"] is True

    assert autotrace_service.stopped is True


def test_websocket_receives_events(tmp_path):
    app, _collector = build_app(tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/events", headers=websocket_headers()) as websocket:
            client.app.state.event_broker.publish(
                {
                    "type": "packet_received",
                    "ts": "2026-03-30T12:00:00Z",
                    "data": {"mesh_packet_id": 11},
                }
            )
            message = websocket.receive_json()

    assert message["type"] == "packet_received"
    assert message["data"]["mesh_packet_id"] == 11


def test_default_collector_callbacks_persist_and_broadcast(tmp_path):
    app = create_app(
        Settings.from_env(
            {
                "MESHSEER_DB_PATH": str(tmp_path / "mesh.db"),
                "MESHSEER_ADMIN_BEARER_TOKEN": ADMIN_TOKEN,
            }
        ),
        start_collector=False,
        start_autotrace_service=False,
    )

    with TestClient(app) as client:
        collector = client.app.state.collector
        with client.websocket_connect("/ws/events", headers=websocket_headers()) as websocket:
            collector.callbacks.on_packet(
                {
                    "mesh_packet_id": 23,
                    "received_at": "2026-03-30T12:00:05Z",
                    "from_node_num": 8,
                    "to_node_num": BROADCAST_NODE_NUM,
                    "portnum": "TEXT_MESSAGE_APP",
                    "channel_index": 2,
                    "hop_limit": 1,
                    "rx_snr": 1.2,
                    "text_preview": "hidden",
                    "payload_base64": None,
                    "raw_json": "{}",
                }
            )
            collector.callbacks.on_node(
                {
                    "node_num": 8,
                    "node_id": "!00000008",
                    "short_name": "NODE8",
                    "long_name": "Node Eight",
                    "hardware_model": "TBEAM",
                    "role": "CLIENT",
                    "channel_index": 2,
                    "last_heard_at": "2026-03-30T12:00:05Z",
                    "last_snr": 1.2,
                    "latitude": None,
                    "longitude": None,
                    "altitude": None,
                    "battery_level": None,
                    "channel_utilization": None,
                    "air_util_tx": None,
                    "raw_json": "{}",
                    "updated_at": "2026-03-30T12:00:05Z",
                }
            )
            collector.callbacks.on_packet(
                {
                    "mesh_packet_id": 22,
                    "received_at": "2026-03-30T12:00:00Z",
                    "from_node_num": 7,
                    "to_node_num": BROADCAST_NODE_NUM,
                    "portnum": "TEXT_MESSAGE_APP",
                    "channel_index": 0,
                    "hop_limit": 1,
                    "rx_snr": 4.2,
                    "text_preview": "ping",
                    "payload_base64": None,
                    "raw_json": "{}",
                }
            )
            collector.callbacks.on_node(
                {
                    "node_num": 7,
                    "node_id": "!00000007",
                    "short_name": "NODE7",
                    "long_name": "Node Seven",
                    "hardware_model": "TBEAM",
                    "role": "CLIENT",
                    "channel_index": 0,
                    "last_heard_at": "2026-03-30T12:00:00Z",
                    "last_snr": 4.2,
                    "latitude": None,
                    "longitude": None,
                    "altitude": None,
                    "battery_level": None,
                    "channel_utilization": None,
                    "air_util_tx": None,
                    "raw_json": "{}",
                    "updated_at": "2026-03-30T12:00:00Z",
                }
            )
            collector.callbacks.on_status(CollectorStatus(state="disconnected", connected=False, detail="missing radio"))

            messages = [websocket.receive_json() for _ in range(3)]

        packet = client.get("/api/admin/packets/1", headers=admin_headers())
        node = client.get("/api/nodes/7")
        hidden_packet = client.get("/api/admin/packets/2", headers=admin_headers())
        hidden_node = client.get("/api/nodes/8")
        chat = client.get("/api/chat")
        missing_packet = client.get("/api/admin/packets/99", headers=admin_headers())
        missing_node = client.get("/api/nodes/999")

    message_types = {message["type"] for message in messages}
    packet_message = next(message for message in messages if message["type"] == "packet_received")
    node_message = next(message for message in messages if message["type"] == "node_updated")
    status_message = next(message for message in messages if message["type"] == "collector_status")

    assert message_types == {"packet_received", "node_updated", "collector_status"}
    assert packet_message["data"]["text_preview"] == "ping"
    assert packet_message["data"]["path_label"] == "Unknown"
    assert packet_message["data"]["path_tone"] == "unknown"
    assert "mesh_packet_id" not in packet_message["data"]
    assert "channel_index" not in packet_message["data"]
    assert "hop_limit" not in packet_message["data"]
    assert "via_mqtt" not in packet_message["data"]
    assert "payload_base64" not in packet_message["data"]
    assert "raw_json" not in packet_message["data"]
    assert node_message["data"]["short_name"] == "NODE7"
    assert "raw_json" not in node_message["data"]
    assert status_message["data"] == {"state": "disconnected", "connected": False}
    assert packet.json()["mesh_packet_id"] == 22
    assert packet.json()["raw_json"] == "{}"
    assert node.json()["node"]["short_name"] == "NODE7"
    assert hidden_packet.status_code == 404
    assert hidden_node.status_code == 404
    assert chat.json()[0]["text_preview"] == "ping"
    assert chat.json()[0]["sender_label"] == "NODE7"
    assert chat.json()[0]["path_label"] == "Unknown"
    assert "from_node_num" not in chat.json()[0]
    assert "raw_json" not in chat.json()[0]
    assert missing_packet.status_code == 404
    assert missing_node.status_code == 404


def test_websocket_rejects_missing_origin(tmp_path):
    app, _collector = build_app(tmp_path)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/events"):
                pass

    assert excinfo.value.code == status.WS_1008_POLICY_VIOLATION


def test_websocket_rejects_cross_origin(tmp_path):
    app, _collector = build_app(tmp_path)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/events", headers=websocket_headers("https://evil.example")):
                pass

    assert excinfo.value.code == status.WS_1008_POLICY_VIOLATION


def test_websocket_rejects_connections_over_capacity(tmp_path):
    app, _collector = build_app(tmp_path, extra_env={"MESHSEER_WS_MAX_CONNECTIONS": "1"})

    with TestClient(app) as client:
        with client.websocket_connect("/ws/events", headers=websocket_headers()) as websocket:
            with pytest.raises(WebSocketDisconnect) as excinfo:
                with client.websocket_connect("/ws/events", headers=websocket_headers()):
                    pass

            client.app.state.event_broker.publish(
                {
                    "type": "packet_received",
                    "ts": "2026-03-30T12:00:00Z",
                    "data": {"mesh_packet_id": 17},
                }
            )
            message = websocket.receive_json()

    assert excinfo.value.code == status.WS_1013_TRY_AGAIN_LATER
    assert message["data"]["mesh_packet_id"] == 17


def test_lifespan_starts_and_stops_collector(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    collector = StubCollector()
    autotrace_service = StubAutotraceService()
    app = create_app(
        Settings.from_env({"MESHSEER_DB_PATH": str(tmp_path / "mesh.db")}),
        repository=repo,
        collector=collector,
        autotrace_service=autotrace_service,
        start_collector=True,
        start_autotrace_service=True,
    )

    with TestClient(app):
        assert collector.started is True
        assert autotrace_service.started is True

    assert collector.stopped is True
    assert autotrace_service.stopped is True
