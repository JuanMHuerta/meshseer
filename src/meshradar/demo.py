from __future__ import annotations

import argparse
import base64
import json
from datetime import timedelta
from pathlib import Path
from typing import Sequence

import uvicorn
from fastapi import FastAPI
from meshtastic.protobuf import mesh_pb2

from meshradar.app import create_app
from meshradar.channels import BROADCAST_NODE_NUM
from meshradar.clock import to_utc_iso, utc_now
from meshradar.collector import CollectorStatus
from meshradar.config import Settings
from meshradar.models import NodeRecord, PacketRecord
from meshradar.storage import MeshRepository


DEMO_LOCAL_NODE_NUM = 101


class DemoCollector:
    def __init__(self, *, local_node_num: int = DEMO_LOCAL_NODE_NUM) -> None:
        self.started = False
        self.stopped = False
        self._local_node_num = local_node_num
        self._status = CollectorStatus(
            state="connected",
            connected=True,
            detail="Demo dataset loaded for headless preview",
        )

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def current_status(self) -> CollectorStatus:
        return self._status

    def local_node_num(self) -> int:
        return self._local_node_num


class DemoAutotraceService:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.enabled = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "running": self.enabled,
            "local_node_num": DEMO_LOCAL_NODE_NUM,
            "interval_seconds": 300,
            "cooldown_hours": 24,
            "ack_only_cooldown_hours": 6,
            "target_window_hours": 24,
            "response_timeout_seconds": 20,
            "eligible_targets": 3,
            "last_attempt": {
                "target_node_num": 1405,
                "target_short_name": "NOVA",
                "status": "success",
                "requested_at": _iso_minutes_ago(12),
                "completed_at": _iso_minutes_ago(12),
                "hop_limit": 4,
                "request_mesh_packet_id": 7102,
                "response_mesh_packet_id": 7103,
                "detail": "Observed demo route reply",
            },
            "recent_attempts": [
                {
                    "id": 2,
                    "target_node_num": 1405,
                    "target_short_name": "NOVA",
                    "status": "success",
                    "requested_at": _iso_minutes_ago(12),
                    "completed_at": _iso_minutes_ago(12),
                    "hop_limit": 4,
                    "request_mesh_packet_id": 7102,
                    "response_mesh_packet_id": 7103,
                    "detail": "Observed demo route reply",
                },
                {
                    "id": 1,
                    "target_node_num": 505,
                    "target_short_name": "ECHO",
                    "status": "ack_only",
                    "requested_at": _iso_minutes_ago(65),
                    "completed_at": _iso_minutes_ago(65),
                    "hop_limit": 5,
                    "request_mesh_packet_id": 7008,
                    "response_mesh_packet_id": 7009,
                    "detail": "Routing ACK arrived without return payload",
                },
            ],
        }


def _iso_minutes_ago(minutes: int) -> str:
    return to_utc_iso(utc_now() - timedelta(minutes=minutes))


def _encode_route_discovery_payload(
    *,
    route: list[int],
    snr_towards: list[int],
    route_back: list[int],
    snr_back: list[int],
) -> str:
    message = mesh_pb2.RouteDiscovery()
    message.route.extend(route)
    message.snr_towards.extend(snr_towards)
    message.route_back.extend(route_back)
    message.snr_back.extend(snr_back)
    return base64.b64encode(message.SerializeToString()).decode("ascii")


def _node_record(
    *,
    node_num: int,
    short_name: str,
    long_name: str,
    hardware_model: str,
    role: str,
    heard_minutes_ago: int,
    latitude: float | None,
    longitude: float | None,
    altitude: float | None,
    hops_away: int | None,
    via_mqtt: bool = False,
    battery_level: float | None = None,
    channel_utilization: float | None = None,
    air_util_tx: float | None = None,
    last_snr: float | None = None,
) -> NodeRecord:
    updated_at = _iso_minutes_ago(heard_minutes_ago)
    raw_json = {
        "num": node_num,
        "hopsAway": hops_away,
        "viaMqtt": via_mqtt,
        "position": (
            {"latitude": latitude, "longitude": longitude, "altitude": altitude}
            if latitude is not None and longitude is not None
            else None
        ),
    }
    return NodeRecord(
        node_num=node_num,
        node_id=f"!{node_num:08x}",
        short_name=short_name,
        long_name=long_name,
        hardware_model=hardware_model,
        role=role,
        channel_index=0,
        last_heard_at=updated_at,
        last_snr=last_snr,
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        battery_level=battery_level,
        channel_utilization=channel_utilization,
        air_util_tx=air_util_tx,
        raw_json=json.dumps(raw_json, separators=(",", ":")),
        updated_at=updated_at,
        hops_away=hops_away,
        via_mqtt=via_mqtt,
    )


def _packet_record(
    *,
    mesh_packet_id: int,
    minutes_ago: int,
    from_node_num: int,
    to_node_num: int,
    portnum: str,
    hop_start: int | None,
    hop_limit: int | None,
    rx_snr: float | None,
    text_preview: str | None = None,
    payload_base64: str | None = None,
    rx_rssi: int | None = None,
    relay_node: int | None = None,
    next_hop: int | None = None,
    via_mqtt: bool = False,
    raw_decoded: dict[str, object] | None = None,
) -> PacketRecord:
    raw_json = {
        "id": mesh_packet_id,
        "hopStart": hop_start,
        "rxRssi": rx_rssi,
        "relayNode": relay_node,
        "nextHop": next_hop,
        "viaMqtt": via_mqtt,
    }
    if raw_decoded is not None:
        raw_json["decoded"] = raw_decoded
    return PacketRecord(
        mesh_packet_id=mesh_packet_id,
        received_at=_iso_minutes_ago(minutes_ago),
        from_node_num=from_node_num,
        to_node_num=to_node_num,
        portnum=portnum,
        channel_index=0,
        hop_limit=hop_limit,
        hop_start=hop_start,
        rx_snr=rx_snr,
        rx_rssi=rx_rssi,
        relay_node=relay_node,
        next_hop=next_hop,
        via_mqtt=via_mqtt,
        text_preview=text_preview,
        payload_base64=payload_base64,
        raw_json=json.dumps(raw_json, separators=(",", ":")),
    )


def seed_demo_data(repository: MeshRepository) -> None:
    receiver_history = [
        _node_record(
            node_num=101,
            short_name="ALFA",
            long_name="Receiver Alpha",
            hardware_model="TBEAM",
            role="CLIENT",
            heard_minutes_ago=50,
            latitude=-34.6037,
            longitude=-58.3816,
            altitude=27.0,
            hops_away=0,
            battery_level=95.0,
            channel_utilization=9.8,
            air_util_tx=1.1,
            last_snr=11.2,
        ),
        _node_record(
            node_num=101,
            short_name="ALFA",
            long_name="Receiver Alpha",
            hardware_model="TBEAM",
            role="CLIENT",
            heard_minutes_ago=38,
            latitude=-34.6037,
            longitude=-58.3816,
            altitude=27.0,
            hops_away=0,
            battery_level=94.0,
            channel_utilization=12.7,
            air_util_tx=1.5,
            last_snr=11.8,
        ),
        _node_record(
            node_num=101,
            short_name="ALFA",
            long_name="Receiver Alpha",
            hardware_model="TBEAM",
            role="CLIENT",
            heard_minutes_ago=26,
            latitude=-34.6037,
            longitude=-58.3816,
            altitude=27.0,
            hops_away=0,
            battery_level=93.0,
            channel_utilization=14.9,
            air_util_tx=1.9,
            last_snr=12.0,
        ),
        _node_record(
            node_num=101,
            short_name="ALFA",
            long_name="Receiver Alpha",
            hardware_model="TBEAM",
            role="CLIENT",
            heard_minutes_ago=14,
            latitude=-34.6037,
            longitude=-58.3816,
            altitude=27.0,
            hops_away=0,
            battery_level=92.0,
            channel_utilization=16.5,
            air_util_tx=2.2,
            last_snr=12.2,
        ),
    ]
    nodes = [
        _node_record(
            node_num=101,
            short_name="ALFA",
            long_name="Receiver Alpha",
            hardware_model="TBEAM",
            role="CLIENT",
            heard_minutes_ago=2,
            latitude=-34.6037,
            longitude=-58.3816,
            altitude=27.0,
            hops_away=0,
            battery_level=91.0,
            channel_utilization=18.2,
            air_util_tx=2.6,
            last_snr=12.4,
        ),
        _node_record(
            node_num=202,
            short_name="BRVO",
            long_name="Puerto Madero",
            hardware_model="HELTEC V3",
            role="CLIENT",
            heard_minutes_ago=4,
            latitude=-34.6072,
            longitude=-58.3638,
            altitude=19.0,
            hops_away=1,
            battery_level=78.0,
            channel_utilization=14.1,
            air_util_tx=1.8,
            last_snr=9.6,
        ),
        _node_record(
            node_num=303,
            short_name="CIRA",
            long_name="Caballito Relay",
            hardware_model="RAK4631",
            role="ROUTER",
            heard_minutes_ago=6,
            latitude=-34.6186,
            longitude=-58.4323,
            altitude=33.0,
            hops_away=2,
            battery_level=65.0,
            channel_utilization=21.5,
            air_util_tx=3.4,
            last_snr=6.2,
        ),
        _node_record(
            node_num=404,
            short_name="DLT4",
            long_name="Belgrano Rooftop",
            hardware_model="T-ECHO",
            role="ROUTER",
            heard_minutes_ago=8,
            latitude=-34.5636,
            longitude=-58.4569,
            altitude=42.0,
            hops_away=1,
            battery_level=88.0,
            channel_utilization=12.8,
            air_util_tx=1.4,
            last_snr=10.8,
        ),
        _node_record(
            node_num=505,
            short_name="ECHO",
            long_name="Lanus East",
            hardware_model="RAK4631",
            role="CLIENT",
            heard_minutes_ago=11,
            latitude=-34.7061,
            longitude=-58.4015,
            altitude=18.0,
            hops_away=3,
            battery_level=54.0,
            channel_utilization=23.0,
            air_util_tx=4.6,
            last_snr=3.7,
        ),
        _node_record(
            node_num=606,
            short_name="FOXT",
            long_name="MQTT Bridge South",
            hardware_model="PI GATEWAY",
            role="CLIENT",
            heard_minutes_ago=13,
            latitude=-34.6406,
            longitude=-58.5157,
            altitude=16.0,
            hops_away=None,
            via_mqtt=True,
            battery_level=None,
            channel_utilization=8.4,
            air_util_tx=0.4,
            last_snr=None,
        ),
        _node_record(
            node_num=707,
            short_name="GOLF",
            long_name="San Cristobal",
            hardware_model="HELTEC V3",
            role="CLIENT",
            heard_minutes_ago=14,
            latitude=-34.6210,
            longitude=-58.3998,
            altitude=25.0,
            hops_away=2,
            battery_level=72.0,
            channel_utilization=17.2,
            air_util_tx=2.1,
            last_snr=5.1,
        ),
        _node_record(
            node_num=808,
            short_name="HTL8",
            long_name="Vicente Lopez",
            hardware_model="TRACKER T1000-E",
            role="CLIENT",
            heard_minutes_ago=16,
            latitude=-34.5276,
            longitude=-58.4785,
            altitude=14.0,
            hops_away=1,
            battery_level=69.0,
            channel_utilization=10.4,
            air_util_tx=1.1,
            last_snr=8.9,
        ),
        _node_record(
            node_num=909,
            short_name="INDI",
            long_name="Moron Mobile",
            hardware_model="TBEAM",
            role="CLIENT",
            heard_minutes_ago=21,
            latitude=-34.6533,
            longitude=-58.6198,
            altitude=28.0,
            hops_away=None,
            battery_level=41.0,
            channel_utilization=11.9,
            air_util_tx=1.3,
            last_snr=2.2,
        ),
        _node_record(
            node_num=1001,
            short_name="JULT",
            long_name="Parque Chas",
            hardware_model="HELTEC V3",
            role="CLIENT",
            heard_minutes_ago=24,
            latitude=-34.5898,
            longitude=-58.4869,
            altitude=31.0,
            hops_away=2,
            battery_level=63.0,
            channel_utilization=12.3,
            air_util_tx=1.5,
            last_snr=4.4,
        ),
        _node_record(
            node_num=1102,
            short_name="KILO",
            long_name="Avellaneda North",
            hardware_model="RAK4631",
            role="ROUTER",
            heard_minutes_ago=26,
            latitude=-34.6663,
            longitude=-58.3657,
            altitude=24.0,
            hops_away=1,
            battery_level=84.0,
            channel_utilization=16.7,
            air_util_tx=2.0,
            last_snr=9.1,
        ),
        _node_record(
            node_num=1203,
            short_name="LIMA",
            long_name="Olivos Tower",
            hardware_model="T-ECHO",
            role="CLIENT",
            heard_minutes_ago=29,
            latitude=-34.5070,
            longitude=-58.4876,
            altitude=39.0,
            hops_away=3,
            battery_level=74.0,
            channel_utilization=13.0,
            air_util_tx=1.7,
            last_snr=5.4,
        ),
        _node_record(
            node_num=1304,
            short_name="MIKE",
            long_name="Quilmes West",
            hardware_model="HELTEC V3",
            role="CLIENT",
            heard_minutes_ago=32,
            latitude=-34.7242,
            longitude=-58.2650,
            altitude=17.0,
            hops_away=2,
            battery_level=57.0,
            channel_utilization=15.4,
            air_util_tx=2.2,
            last_snr=4.8,
        ),
        _node_record(
            node_num=1405,
            short_name="NOVA",
            long_name="Liniers Relay",
            hardware_model="RAK4631",
            role="ROUTER",
            heard_minutes_ago=37,
            latitude=-34.6394,
            longitude=-58.5233,
            altitude=29.0,
            hops_away=2,
            battery_level=82.0,
            channel_utilization=19.8,
            air_util_tx=2.9,
            last_snr=6.9,
        ),
        _node_record(
            node_num=1506,
            short_name="ORCA",
            long_name="Cordoba Gateway",
            hardware_model="TBEAM",
            role="CLIENT",
            heard_minutes_ago=43,
            latitude=-31.4167,
            longitude=-64.1833,
            altitude=395.0,
            hops_away=4,
            battery_level=48.0,
            channel_utilization=9.7,
            air_util_tx=0.9,
            last_snr=1.9,
        ),
        _node_record(
            node_num=1607,
            short_name="PICO",
            long_name="No Fix Tracker",
            hardware_model="TRACKER T1000-E",
            role="CLIENT",
            heard_minutes_ago=48,
            latitude=None,
            longitude=None,
            altitude=None,
            hops_away=2,
            battery_level=52.0,
            channel_utilization=6.4,
            air_util_tx=0.8,
            last_snr=3.1,
        ),
    ]

    packets = [
        _packet_record(
            mesh_packet_id=7001,
            minutes_ago=3,
            from_node_num=202,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            hop_start=3,
            hop_limit=3,
            rx_snr=9.6,
            rx_rssi=-92,
            text_preview="South riverfront clear. Two nodes active.",
        ),
        _packet_record(
            mesh_packet_id=7002,
            minutes_ago=5,
            from_node_num=303,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            hop_start=5,
            hop_limit=3,
            rx_snr=6.2,
            rx_rssi=-101,
            relay_node=404,
            next_hop=404,
            text_preview="Caballito heard downtown with moderate noise.",
        ),
        _packet_record(
            mesh_packet_id=7003,
            minutes_ago=7,
            from_node_num=404,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="POSITION_APP",
            hop_start=3,
            hop_limit=3,
            rx_snr=10.8,
            rx_rssi=-89,
            text_preview="Belgrano rooftop beacon",
        ),
        _packet_record(
            mesh_packet_id=7004,
            minutes_ago=10,
            from_node_num=606,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            hop_start=None,
            hop_limit=None,
            rx_snr=None,
            via_mqtt=True,
            text_preview="Bridge mirrored one packet from south cluster.",
        ),
        _packet_record(
            mesh_packet_id=7005,
            minutes_ago=12,
            from_node_num=505,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            hop_start=6,
            hop_limit=3,
            rx_snr=3.7,
            rx_rssi=-108,
            next_hop=303,
            payload_base64=_encode_route_discovery_payload(
                route=[404, 303],
                snr_towards=[32, 24, 16],
                route_back=[202],
                snr_back=[28, 20],
            ),
            text_preview="Passive traceroute route discovery",
        ),
        _packet_record(
            mesh_packet_id=7006,
            minutes_ago=15,
            from_node_num=707,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TELEMETRY_APP",
            hop_start=4,
            hop_limit=2,
            rx_snr=5.1,
            rx_rssi=-104,
            relay_node=202,
            next_hop=202,
            text_preview="Battery 72%, air util 2.1%",
        ),
        _packet_record(
            mesh_packet_id=7007,
            minutes_ago=18,
            from_node_num=808,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            hop_start=3,
            hop_limit=3,
            rx_snr=8.9,
            rx_rssi=-94,
            text_preview="North shore direct path stable.",
        ),
        _packet_record(
            mesh_packet_id=7008,
            minutes_ago=22,
            from_node_num=101,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            hop_start=3,
            hop_limit=3,
            rx_snr=12.4,
            rx_rssi=-87,
            text_preview="Receiver alpha online for demo render.",
        ),
        _packet_record(
            mesh_packet_id=7009,
            minutes_ago=27,
            from_node_num=1102,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="NODEINFO_APP",
            hop_start=3,
            hop_limit=3,
            rx_snr=9.1,
            rx_rssi=-91,
            text_preview="Avellaneda router telemetry refresh",
        ),
        _packet_record(
            mesh_packet_id=7010,
            minutes_ago=31,
            from_node_num=1304,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            hop_start=5,
            hop_limit=3,
            rx_snr=4.8,
            rx_rssi=-106,
            relay_node=1102,
            next_hop=1102,
            text_preview="Quilmes path remains two hops tonight.",
        ),
        _packet_record(
            mesh_packet_id=7011,
            minutes_ago=35,
            from_node_num=1405,
            to_node_num=101,
            portnum="ROUTING_APP",
            hop_start=5,
            hop_limit=3,
            rx_snr=6.9,
            rx_rssi=-99,
            next_hop=707,
            raw_decoded={
                "routing": {
                    "routeReply": {
                        "route": [1102, 707],
                        "snrTowards": [28, 24, 20],
                        "routeBack": [808],
                        "snrBack": [24, 20],
                    }
                }
            },
            text_preview="Passive route reply",
        ),
        _packet_record(
            mesh_packet_id=7012,
            minutes_ago=41,
            from_node_num=1506,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            hop_start=7,
            hop_limit=3,
            rx_snr=1.9,
            rx_rssi=-113,
            relay_node=1405,
            next_hop=1405,
            text_preview="Cordoba gateway barely making the frame.",
        ),
        _packet_record(
            mesh_packet_id=7013,
            minutes_ago=46,
            from_node_num=909,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            hop_start=4,
            hop_limit=4,
            rx_snr=2.2,
            rx_rssi=-109,
            text_preview="Moron mobile on the move, GPS drifting.",
        ),
        _packet_record(
            mesh_packet_id=7014,
            minutes_ago=52,
            from_node_num=1607,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            hop_start=5,
            hop_limit=3,
            rx_snr=3.1,
            rx_rssi=-107,
            relay_node=303,
            next_hop=303,
            text_preview="Tracker heard without a location fix.",
        ),
    ]

    with repository._connect() as connection:
        connection.execute("DELETE FROM traceroute_attempts")
        connection.execute("DELETE FROM packets")
        connection.execute("DELETE FROM nodes")
        connection.execute("DELETE FROM node_metric_history")

    for node in receiver_history:
        repository.upsert_node(node)

    for node in nodes:
        repository.upsert_node(node)

    for packet in packets:
        repository.insert_packet(packet)

    attempt_id = repository.start_traceroute_attempt(
        target_node_num=1405,
        requested_at=_iso_minutes_ago(12),
        hop_limit=4,
    )
    repository.complete_traceroute_attempt(
        attempt_id,
        completed_at=_iso_minutes_ago(12),
        status="success",
        request_mesh_packet_id=7102,
        response_mesh_packet_id=7103,
        detail="Observed demo route reply",
    )


def build_demo_app(db_path: Path) -> FastAPI:
    repository = MeshRepository(db_path)
    seed_demo_data(repository)
    settings = Settings.from_env(
        {
            "MESHRADAR_DB_PATH": str(db_path),
            "MESHRADAR_LOCAL_NODE_NUM": str(DEMO_LOCAL_NODE_NUM),
        }
    )
    return create_app(
        settings,
        repository=repository,
        collector=DemoCollector(),
        autotrace_service=DemoAutotraceService(),
        start_collector=False,
        start_autotrace_service=False,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a seeded Meshradar demo app for headless rendering.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db-path", default="data/demo-headless.db")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    app = build_demo_app(db_path)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    run()
