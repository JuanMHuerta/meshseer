import base64
import sqlite3
from datetime import UTC, datetime

from meshtastic.protobuf import mesh_pb2

from meshseer.channels import BROADCAST_NODE_NUM
from meshseer.clock import timestamp_to_utc_iso
from meshseer.models import NodeRecord, PacketRecord
from meshseer.storage import MeshRepository, SQLITE_BUSY_TIMEOUT_MS


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


def encode_routing_reply_payload(
    *,
    route: list[int] | None = None,
    snr_towards: list[int] | None = None,
    route_back: list[int] | None = None,
    snr_back: list[int] | None = None,
) -> str:
    discovery = mesh_pb2.RouteDiscovery()
    discovery.route.extend(route or [])
    discovery.snr_towards.extend(snr_towards or [])
    discovery.route_back.extend(route_back or [])
    discovery.snr_back.extend(snr_back or [])
    routing = mesh_pb2.Routing()
    routing.route_reply.CopyFrom(discovery)
    return base64.b64encode(routing.SerializeToString()).decode("ascii")


def test_repository_enables_wal_and_busy_timeout(tmp_path):
    db_path = tmp_path / "mesh.db"
    repo = MeshRepository(db_path)

    with sqlite3.connect(db_path) as raw_connection:
        journal_mode = raw_connection.execute("PRAGMA journal_mode").fetchone()

    with repo._connect() as managed_connection:
        busy_timeout = managed_connection.execute("PRAGMA busy_timeout").fetchone()

    assert journal_mode is not None
    assert str(journal_mode[0]).lower() == "wal"
    assert busy_timeout is not None
    assert busy_timeout[0] == SQLITE_BUSY_TIMEOUT_MS


def test_repository_stores_packets_and_nodes(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")

    packet = PacketRecord(
        mesh_packet_id=77,
        received_at="2026-03-30T12:00:00Z",
        from_node_num=101,
        to_node_num=202,
        portnum="TEXT_MESSAGE_APP",
        channel_index=0,
        hop_limit=3,
        rx_snr=6.5,
        text_preview="hello mesh",
        payload_base64="aGVsbG8=",
        raw_json='{"id":77}',
    )
    packet_id = repo.insert_packet(packet)

    node = NodeRecord(
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
        battery_level=97.0,
        channel_utilization=4.4,
        air_util_tx=1.1,
        raw_json='{"num":101}',
        updated_at="2026-03-30T12:00:00Z",
    )
    repo.upsert_node(node)

    packets = repo.list_packets(limit=10)
    nodes = repo.list_nodes()
    node_detail = repo.get_node(101)
    recent_packets = repo.list_packets(limit=10, from_node=101, primary_only=True)

    assert packet_id == 1
    assert packets[0]["text_preview"] == "hello mesh"
    assert nodes[0]["short_name"] == "ALFA"
    assert node_detail["node_id"] == "!00000065"
    assert recent_packets[0]["mesh_packet_id"] == 77


def test_repository_tracks_node_metric_history(tmp_path):
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
            battery_level=97.0,
            channel_utilization=4.4,
            air_util_tx=1.1,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:00:00Z",
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
            last_heard_at="2026-03-30T12:05:00Z",
            last_snr=5.7,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=96.0,
            channel_utilization=6.8,
            air_util_tx=1.6,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:05:00Z",
        )
    )

    assert repo.list_node_metric_history(101) == [
        {
            "recorded_at": "2026-03-30T12:00:00Z",
            "channel_utilization": 4.4,
            "air_util_tx": 1.1,
        },
        {
            "recorded_at": "2026-03-30T12:05:00Z",
            "channel_utilization": 6.8,
            "air_util_tx": 1.6,
        },
    ]


def test_repository_tracks_daily_node_totals_by_utc_day(tmp_path, monkeypatch):
    repo = MeshRepository(tmp_path / "mesh.db")

    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
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
            last_heard_at="2026-03-30T12:05:00Z",
            last_snr=5.9,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:05:00Z",
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
            last_heard_at="2026-03-30T12:06:00Z",
            last_snr=4.1,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202}',
            updated_at="2026-03-30T12:06:00Z",
        )
    )

    assert repo.list_daily_node_totals(window_days=30) == [
        {"day": "2026-03-30", "total": 2, "mapped": 1},
    ]

    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 3, 31, 0, 5, tzinfo=UTC),
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
            last_heard_at="2026-03-31T00:05:00Z",
            last_snr=4.4,
            latitude=10.4,
            longitude=-84.3,
            altitude=18.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202}',
            updated_at="2026-03-31T00:05:00Z",
        )
    )

    assert repo.list_daily_node_totals(window_days=30) == [
        {"day": "2026-03-30", "total": 2, "mapped": 1},
        {"day": "2026-03-31", "total": 2, "mapped": 2},
    ]


def test_repository_updates_daily_coverage_when_primary_node_gains_coordinates(tmp_path, monkeypatch):
    repo = MeshRepository(tmp_path / "mesh.db")

    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
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
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:00:00Z",
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
            last_heard_at="2026-03-30T12:10:00Z",
            last_snr=6.7,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:10:00Z",
        )
    )

    assert repo.list_daily_node_totals(window_days=30) == [
        {"day": "2026-03-30", "total": 1, "mapped": 1},
    ]


def test_repository_daily_node_totals_include_anchor_before_window(tmp_path, monkeypatch):
    repo = MeshRepository(tmp_path / "mesh.db")

    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 3, 10, 8, 0, tzinfo=UTC),
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
            last_heard_at="2026-03-10T08:00:00Z",
            last_snr=6.5,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-10T08:00:00Z",
        )
    )

    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 4, 10, 8, 0, tzinfo=UTC),
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
            last_heard_at="2026-04-10T08:00:00Z",
            last_snr=6.8,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-04-10T08:00:00Z",
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
            last_heard_at="2026-04-10T08:05:00Z",
            last_snr=4.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202}',
            updated_at="2026-04-10T08:05:00Z",
        )
    )

    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 4, 14, 8, 0, tzinfo=UTC),
    )

    assert repo.list_daily_node_totals(window_days=3) == [
        {"day": "2026-04-10", "total": 2, "mapped": 1},
    ]
    assert repo.list_daily_node_totals(window_days=30) == [
        {"day": "2026-03-10", "total": 1, "mapped": 1},
        {"day": "2026-04-10", "total": 2, "mapped": 1},
    ]


def test_repository_filters_packets_and_chat(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=1,
            received_at="2026-03-30T11:00:00Z",
            from_node_num=1,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=None,
            rx_snr=None,
            text_preview="one",
            payload_base64=None,
            raw_json="{}",
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=2,
            received_at="2026-03-30T12:00:00Z",
            from_node_num=3,
            to_node_num=4,
            portnum="NODEINFO_APP",
            channel_index=1,
            hop_limit=None,
            rx_snr=None,
            text_preview=None,
            payload_base64=None,
            raw_json="{}",
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=3,
            received_at="2026-03-30T12:30:00Z",
            from_node_num=5,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=2,
            hop_limit=None,
            rx_snr=None,
            text_preview="off channel",
            payload_base64=None,
            raw_json="{}",
        )
    )

    filtered = repo.list_packets(limit=10, since="2026-03-30T11:30:00Z", portnum="NODEINFO_APP")
    primary_only = repo.list_packets(limit=10, primary_only=True)
    chat = repo.list_chat_messages(limit=10, primary_only=True)

    assert [item["mesh_packet_id"] for item in filtered] == [2]
    assert [item["mesh_packet_id"] for item in primary_only] == [1]
    assert [item["mesh_packet_id"] for item in chat] == [1]


def test_repository_excludes_admin_packets_from_node_activity(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=1,
            received_at="2026-03-30T12:00:00Z",
            from_node_num=101,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=None,
            rx_snr=None,
            text_preview="hello",
            payload_base64=None,
            raw_json="{}",
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=2,
            received_at="2026-03-30T12:01:00Z",
            from_node_num=101,
            to_node_num=202,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=None,
            rx_snr=None,
            text_preview=None,
            payload_base64=None,
            raw_json="{}",
        )
    )

    visible_packets = repo.list_packets_for_node(101, primary_only=True, exclude_admin=True)
    all_packets = repo.list_packets_for_node(101, primary_only=True)

    assert [item["mesh_packet_id"] for item in visible_packets] == [1]
    assert [item["mesh_packet_id"] for item in all_packets] == [2, 1]


def test_repository_backfills_node_channel_index_from_raw_json(tmp_path):
    db_path = tmp_path / "mesh.db"

    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE nodes (
            node_num INTEGER PRIMARY KEY,
            node_id TEXT,
            short_name TEXT,
            long_name TEXT,
            hardware_model TEXT,
            role TEXT,
            last_heard_at TEXT,
            last_snr REAL,
            latitude REAL,
            longitude REAL,
            altitude REAL,
            battery_level REAL,
            channel_utilization REAL,
            air_util_tx REAL,
            raw_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO nodes (
            node_num,
            node_id,
            short_name,
            long_name,
            hardware_model,
            role,
            last_heard_at,
            last_snr,
            latitude,
            longitude,
            altitude,
            battery_level,
            channel_utilization,
            air_util_tx,
            raw_json,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            202,
            "!000000ca",
            "BETA",
            "Beta Node",
            "TBEAM",
            "CLIENT",
            "2026-03-30T12:00:00Z",
            2.5,
            10.0,
            -84.0,
            15.0,
            None,
            None,
            None,
            '{"num":202,"channel":2}',
            "2026-03-30T12:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    repo = MeshRepository(db_path)
    all_nodes = repo.list_nodes()
    primary_nodes = repo.list_nodes(primary_only=True)

    assert all_nodes[0]["channel_index"] == 2
    assert primary_nodes == []


def test_repository_backfills_node_metric_history_from_existing_nodes(tmp_path):
    db_path = tmp_path / "mesh.db"

    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE nodes (
            node_num INTEGER PRIMARY KEY,
            node_id TEXT,
            short_name TEXT,
            long_name TEXT,
            hardware_model TEXT,
            role TEXT,
            last_heard_at TEXT,
            last_snr REAL,
            latitude REAL,
            longitude REAL,
            altitude REAL,
            battery_level REAL,
            channel_utilization REAL,
            air_util_tx REAL,
            raw_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO nodes (
            node_num,
            node_id,
            short_name,
            long_name,
            hardware_model,
            role,
            last_heard_at,
            last_snr,
            latitude,
            longitude,
            altitude,
            battery_level,
            channel_utilization,
            air_util_tx,
            raw_json,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            202,
            "!000000ca",
            "BETA",
            "Beta Node",
            "TBEAM",
            "CLIENT",
            "2026-03-30T12:00:00Z",
            2.5,
            10.0,
            -84.0,
            15.0,
            91.0,
            12.4,
            1.9,
            '{"num":202,"channel":0}',
            "2026-03-30T12:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    repo = MeshRepository(db_path)

    assert repo.list_node_metric_history(202) == [
        {
            "recorded_at": "2026-03-30T12:00:00Z",
            "channel_utilization": 12.4,
            "air_util_tx": 1.9,
        }
    ]


def test_repository_backfills_node_activity_from_packets(tmp_path):
    db_path = tmp_path / "mesh.db"
    repo = MeshRepository(db_path)

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
            last_snr=1.0,
            latitude=10.25,
            longitude=-84.1,
            altitude=15.0,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:00:00Z",
            hops_away=1,
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=1010,
            received_at="2026-03-30T12:10:00Z",
            from_node_num=101,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=None,
            hop_limit=3,
            rx_snr=6.5,
            text_preview="refresh existing",
            payload_base64=None,
            raw_json='{"id":1010,"fromId":"!00000065"}',
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=2020,
            received_at="2026-03-30T12:11:00Z",
            from_node_num=202,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=None,
            hop_limit=3,
            rx_snr=4.2,
            text_preview="create missing sender",
            payload_base64=None,
            raw_json='{"id":2020,"fromId":"!000000ca","viaMqtt":true}',
            via_mqtt=True,
        )
    )

    reloaded = MeshRepository(db_path)

    refreshed = reloaded.get_node(101, primary_only=True)
    created = reloaded.get_node(202, primary_only=True)

    assert refreshed is not None
    assert refreshed["last_heard_at"] == "2026-03-30T12:10:00Z"
    assert refreshed["last_snr"] == 6.5
    assert created is not None
    assert created["node_id"] == "!000000ca"
    assert created["last_heard_at"] == "2026-03-30T12:11:00Z"
    assert created["via_mqtt"] is True


def test_repository_backfills_passive_mesh_metadata_from_raw_json(tmp_path):
    db_path = tmp_path / "mesh.db"

    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE packets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mesh_packet_id INTEGER,
            received_at TEXT NOT NULL,
            from_node_num INTEGER,
            to_node_num INTEGER,
            portnum TEXT NOT NULL,
            channel_index INTEGER,
            hop_limit INTEGER,
            rx_snr REAL,
            text_preview TEXT,
            payload_base64 TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE nodes (
            node_num INTEGER PRIMARY KEY,
            node_id TEXT,
            short_name TEXT,
            long_name TEXT,
            hardware_model TEXT,
            role TEXT,
            channel_index INTEGER,
            last_heard_at TEXT,
            last_snr REAL,
            latitude REAL,
            longitude REAL,
            altitude REAL,
            battery_level REAL,
            channel_utilization REAL,
            air_util_tx REAL,
            raw_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO packets (
            mesh_packet_id,
            received_at,
            from_node_num,
            to_node_num,
            portnum,
            channel_index,
            hop_limit,
            rx_snr,
            text_preview,
            payload_base64,
            raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            88,
            "2026-03-30T12:00:00Z",
            303,
            BROADCAST_NODE_NUM,
            "POSITION_APP",
            0,
            2,
            3.5,
            None,
            None,
            '{"hopStart":4,"relayNode":404,"rxRssi":-99,"viaMqtt":false}',
        ),
    )
    connection.execute(
        """
        INSERT INTO nodes (
            node_num,
            node_id,
            short_name,
            long_name,
            hardware_model,
            role,
            channel_index,
            last_heard_at,
            last_snr,
            latitude,
            longitude,
            altitude,
            battery_level,
            channel_utilization,
            air_util_tx,
            raw_json,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            303,
            "!0000012f",
            "GAMMA",
            "Gamma Node",
            "TBEAM",
            "CLIENT",
            0,
            "2026-03-30T12:00:00Z",
            3.5,
            10.0,
            -84.0,
            15.0,
            None,
            None,
            None,
            '{"num":303,"hopsAway":2,"viaMqtt":false}',
            "2026-03-30T12:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    repo = MeshRepository(db_path)
    packet = repo.list_packets(limit=1)[0]
    node = repo.get_node(303)

    assert packet["hop_start"] == 4
    assert packet["relay_node"] == 404
    assert packet["rx_rssi"] == -99
    assert packet["via_mqtt"] is False
    assert node["hops_away"] == 2
    assert node["via_mqtt"] is False


def test_repository_builds_neighbor_links_from_passive_reports(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=90,
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
            raw_json="{}",
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=91,
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
            raw_json="{}",
            via_mqtt=False,
        )
    )

    links = repo.get_mesh_links(primary_only=True)

    assert links["stats"] == {"total": 1, "mutual": 1, "one_way": 0}
    assert links["neighbor_links"][0]["node_a_num"] == 101
    assert links["neighbor_links"][0]["node_b_num"] == 303
    assert links["neighbor_links"][0]["mutual"] is True
    assert links["neighbor_links"][0]["a_to_b"]["last_rx_time"] == timestamp_to_utc_iso(1_743_337_800)


def test_repository_builds_routes_from_passive_traceroute_packets(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=92,
            received_at="2026-03-30T12:12:00Z",
            from_node_num=303,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=3,
            hop_start=3,
            rx_snr=5.0,
            rx_rssi=-94,
            text_preview=None,
            payload_base64=encode_traceroute_payload(
                route=[202],
                snr_towards=[20, 12],
                route_back=[404],
                snr_back=[8, 4],
            ),
            raw_json="{}",
            via_mqtt=False,
        )
    )

    routes = repo.get_mesh_routes(primary_only=True)

    assert routes["stats"] == {"total": 2, "forward": 1, "return": 1}
    assert routes["routes"][0]["direction"] == "forward"
    assert routes["routes"][0]["path_node_nums"] == [101, 202, 303]
    assert routes["routes"][0]["edge_snr_db"] == [5.0, 3.0]
    assert routes["routes"][1]["direction"] == "return"
    assert routes["routes"][1]["path_node_nums"] == [303, 404, 101]
    assert routes["routes"][1]["edge_snr_db"] == [2.0, 1.0]


def test_repository_builds_routes_from_routing_route_reply_packets(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=93,
            received_at="2026-03-30T12:13:00Z",
            from_node_num=303,
            to_node_num=101,
            portnum="ROUTING_APP",
            channel_index=0,
            hop_limit=3,
            hop_start=None,
            rx_snr=4.0,
            rx_rssi=-95,
            text_preview=None,
            payload_base64=encode_routing_reply_payload(route=[202], snr_towards=[16, 8]),
            raw_json="{}",
            via_mqtt=False,
        )
    )

    routes = repo.get_mesh_routes(primary_only=True)

    assert routes["stats"] == {"total": 1, "forward": 1, "return": 0}
    assert routes["routes"][0]["portnum"] == "ROUTING_APP"
    assert routes["routes"][0]["variant"] == "route_reply"
    assert routes["routes"][0]["path_node_nums"] == [101, 202, 303]
    assert routes["routes"][0]["edge_snr_db"] == [4.0, 2.0]


def test_repository_filters_mesh_routes_by_since(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=92,
            received_at="2026-03-30T06:00:00Z",
            from_node_num=303,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=3,
            hop_start=3,
            rx_snr=5.0,
            rx_rssi=-94,
            text_preview=None,
            payload_base64=encode_traceroute_payload(
                route=[202],
                snr_towards=[20, 12],
                route_back=[404],
                snr_back=[8, 4],
            ),
            raw_json="{}",
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=93,
            received_at="2026-03-30T12:00:00Z",
            from_node_num=505,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=2,
            hop_start=2,
            rx_snr=4.5,
            rx_rssi=-96,
            text_preview=None,
            payload_base64=encode_traceroute_payload(
                route=[202],
                snr_towards=[18, 9],
            ),
            raw_json="{}",
            via_mqtt=False,
        )
    )

    routes = repo.get_mesh_routes(since="2026-03-30T10:00:00Z", primary_only=True)

    assert routes["stats"] == {"total": 1, "forward": 1, "return": 0}
    assert routes["routes"][0]["mesh_packet_id"] == 93
    assert routes["routes"][0]["path_node_nums"] == [101, 202, 505]


def test_repository_tracks_traceroute_attempts(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    repo.upsert_node(
        NodeRecord(
            node_num=202,
            node_id="!000000ca",
            short_name="BETA",
            long_name="Beta Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:00:00Z",
            last_snr=4.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202}',
            updated_at="2026-03-30T12:00:00Z",
            hops_away=2,
            via_mqtt=False,
        )
    )

    attempt_id = repo.start_traceroute_attempt(
        target_node_num=202,
        requested_at="2026-03-30T12:00:00Z",
        hop_limit=2,
    )
    repo.complete_traceroute_attempt(
        attempt_id,
        completed_at="2026-03-30T12:00:20Z",
        status="success",
        request_mesh_packet_id=88,
        response_mesh_packet_id=99,
        detail=None,
    )

    recent = repo.list_recent_traceroute_attempts(limit=5)

    assert recent[0]["target_node_num"] == 202
    assert recent[0]["target_short_name"] == "BETA"
    assert recent[0]["status"] == "success"
    assert recent[0]["request_mesh_packet_id"] == 88
    assert recent[0]["response_mesh_packet_id"] == 99


def test_repository_selects_autotrace_candidates_with_cooldowns(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC)

    for node_num, short_name, last_heard_at, hops_away, via_mqtt in (
        (101, "ALFA", "2026-03-30T12:00:00Z", None, False),
        (202, "BETA", "2026-03-30T11:58:00Z", 2, False),
        (303, "GAMMA", "2026-03-30T11:57:00Z", 3, False),
        (404, "MQTT", "2026-03-30T11:56:00Z", 1, True),
        (505, "OLD", "2026-03-28T11:55:00Z", 2, False),
        (606, "ROUTE", "2026-03-30T11:54:00Z", 1, False),
        (707, "AGED", "2026-03-30T11:53:00Z", 4, False),
    ):
        repo.upsert_node(
            NodeRecord(
                node_num=node_num,
                node_id=f"!{node_num:08x}",
                short_name=short_name,
                long_name=f"{short_name} Node",
                hardware_model="TBEAM",
                role="CLIENT",
                channel_index=0,
                last_heard_at=last_heard_at,
                last_snr=4.0,
                latitude=None,
                longitude=None,
                altitude=None,
                battery_level=None,
                channel_utilization=None,
                air_util_tx=None,
                raw_json=f'{{"num":{node_num}}}',
                updated_at=last_heard_at,
                hops_away=hops_away,
                via_mqtt=via_mqtt,
            )
        )

    fresh_attempt = repo.start_traceroute_attempt(
        target_node_num=303,
        requested_at="2026-03-30T10:00:00Z",
        hop_limit=3,
    )
    repo.complete_traceroute_attempt(
        fresh_attempt,
        completed_at="2026-03-30T10:00:10Z",
        status="ack_only",
        request_mesh_packet_id=1,
        response_mesh_packet_id=2,
        detail="ack only",
    )
    stale_attempt = repo.start_traceroute_attempt(
        target_node_num=707,
        requested_at="2026-03-28T10:00:00Z",
        hop_limit=4,
    )
    repo.complete_traceroute_attempt(
        stale_attempt,
        completed_at="2026-03-28T10:00:20Z",
        status="timeout",
        request_mesh_packet_id=3,
        response_mesh_packet_id=None,
        detail="timeout",
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=100,
            received_at="2026-03-30T11:00:00Z",
            from_node_num=606,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=1,
            hop_start=1,
            rx_snr=5.0,
            rx_rssi=-90,
            text_preview=None,
            payload_base64=encode_traceroute_payload(route=[], snr_towards=[20]),
            raw_json="{}",
            via_mqtt=False,
        )
    )

    next_target = repo.get_next_autotrace_target(
        local_node_num=101,
        target_window_hours=24,
        cooldown_hours=24,
        ack_only_cooldown_hours=6,
        primary_only=True,
        now=now,
    )
    count = repo.count_autotrace_candidates(
        local_node_num=101,
        target_window_hours=24,
        cooldown_hours=24,
        ack_only_cooldown_hours=6,
        primary_only=True,
        now=now,
    )

    assert count == 2
    assert next_target is not None
    assert next_target["node_num"] == 202


def test_repository_retries_ack_only_nodes_after_ack_only_cooldown(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC)
    repo.upsert_node(
        NodeRecord(
            node_num=101,
            node_id="!00000065",
            short_name="LOCAL",
            long_name="LOCAL Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:00:00Z",
            last_snr=4.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:00:00Z",
            hops_away=None,
            via_mqtt=False,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=202,
            node_id="!000000ca",
            short_name="ACKY",
            long_name="ACKY Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T11:58:00Z",
            last_snr=4.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202}',
            updated_at="2026-03-30T11:58:00Z",
            hops_away=3,
            via_mqtt=False,
        )
    )
    attempt_id = repo.start_traceroute_attempt(
        target_node_num=202,
        requested_at="2026-03-30T05:30:00Z",
        hop_limit=3,
    )
    repo.complete_traceroute_attempt(
        attempt_id,
        completed_at="2026-03-30T05:30:05Z",
        status="ack_only",
        request_mesh_packet_id=11,
        response_mesh_packet_id=12,
        detail="ack only",
    )

    eligible = repo.get_next_autotrace_target(
        local_node_num=101,
        target_window_hours=24,
        cooldown_hours=24,
        ack_only_cooldown_hours=6,
        primary_only=True,
        now=now,
    )

    assert eligible is not None
    assert eligible["node_num"] == 202


def test_repository_applies_ack_only_backoff_by_consecutive_streak(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    repo.upsert_node(
        NodeRecord(
            node_num=101,
            node_id="!00000065",
            short_name="LOCAL",
            long_name="LOCAL Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T12:00:00Z",
            last_snr=4.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-30T12:00:00Z",
            hops_away=None,
            via_mqtt=False,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=202,
            node_id="!000000ca",
            short_name="ACKY",
            long_name="ACKY Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-30T11:58:00Z",
            last_snr=4.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202}',
            updated_at="2026-03-30T11:58:00Z",
            hops_away=3,
            via_mqtt=False,
        )
    )
    for requested_at, completed_at in (
        ("2026-03-29T20:00:00Z", "2026-03-29T20:00:05Z"),
        ("2026-03-30T05:30:00Z", "2026-03-30T05:30:05Z"),
    ):
        attempt_id = repo.start_traceroute_attempt(
            target_node_num=202,
            requested_at=requested_at,
            hop_limit=3,
        )
        repo.complete_traceroute_attempt(
            attempt_id,
            completed_at=completed_at,
            status="ack_only",
            request_mesh_packet_id=11,
            response_mesh_packet_id=12,
            detail="ack only",
        )

    blocked = repo.get_next_autotrace_target(
        local_node_num=101,
        target_window_hours=24,
        cooldown_hours=24,
        ack_only_cooldown_hours=6,
        primary_only=True,
        now=datetime(2026, 3, 30, 16, 0, 0, tzinfo=UTC),
    )
    eligible = repo.get_next_autotrace_target(
        local_node_num=101,
        target_window_hours=24,
        cooldown_hours=24,
        ack_only_cooldown_hours=6,
        primary_only=True,
        now=datetime(2026, 3, 30, 17, 31, 0, tzinfo=UTC),
    )

    assert blocked is None
    assert eligible is not None
    assert eligible["node_num"] == 202


def test_repository_caps_ack_only_backoff_at_standard_cooldown(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")
    repo.upsert_node(
        NodeRecord(
            node_num=101,
            node_id="!00000065",
            short_name="LOCAL",
            long_name="LOCAL Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-31T12:00:00Z",
            last_snr=4.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":101}',
            updated_at="2026-03-31T12:00:00Z",
            hops_away=None,
            via_mqtt=False,
        )
    )
    repo.upsert_node(
        NodeRecord(
            node_num=202,
            node_id="!000000ca",
            short_name="ACKY",
            long_name="ACKY Node",
            hardware_model="TBEAM",
            role="CLIENT",
            channel_index=0,
            last_heard_at="2026-03-31T11:58:00Z",
            last_snr=4.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=None,
            air_util_tx=None,
            raw_json='{"num":202}',
            updated_at="2026-03-31T11:58:00Z",
            hops_away=3,
            via_mqtt=False,
        )
    )
    for requested_at, completed_at in (
        ("2026-03-30T00:00:00Z", "2026-03-30T00:00:05Z"),
        ("2026-03-30T06:00:00Z", "2026-03-30T06:00:05Z"),
        ("2026-03-30T12:00:00Z", "2026-03-30T12:00:05Z"),
        ("2026-03-30T18:00:00Z", "2026-03-30T18:00:05Z"),
    ):
        attempt_id = repo.start_traceroute_attempt(
            target_node_num=202,
            requested_at=requested_at,
            hop_limit=3,
        )
        repo.complete_traceroute_attempt(
            attempt_id,
            completed_at=completed_at,
            status="ack_only",
            request_mesh_packet_id=11,
            response_mesh_packet_id=12,
            detail="ack only",
        )

    blocked = repo.get_next_autotrace_target(
        local_node_num=101,
        target_window_hours=48,
        cooldown_hours=24,
        ack_only_cooldown_hours=6,
        primary_only=True,
        now=datetime(2026, 3, 31, 17, 0, 0, tzinfo=UTC),
    )
    eligible = repo.get_next_autotrace_target(
        local_node_num=101,
        target_window_hours=48,
        cooldown_hours=24,
        ack_only_cooldown_hours=6,
        primary_only=True,
        now=datetime(2026, 3, 31, 18, 1, 0, tzinfo=UTC),
    )

    assert blocked is None
    assert eligible is not None
    assert eligible["node_num"] == 202


def test_repository_backfills_derived_analytics_from_legacy_history(tmp_path):
    db_path = tmp_path / "mesh.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE packets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mesh_packet_id INTEGER,
            received_at TEXT NOT NULL,
            from_node_num INTEGER,
            to_node_num INTEGER,
            portnum TEXT NOT NULL,
            channel_index INTEGER,
            hop_limit INTEGER,
            hop_start INTEGER,
            rx_snr REAL,
            rx_rssi INTEGER,
            next_hop INTEGER,
            relay_node INTEGER,
            via_mqtt INTEGER,
            transport_mechanism TEXT,
            text_preview TEXT,
            payload_base64 TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE nodes (
            node_num INTEGER PRIMARY KEY,
            node_id TEXT,
            short_name TEXT,
            long_name TEXT,
            hardware_model TEXT,
            role TEXT,
            channel_index INTEGER,
            last_heard_at TEXT,
            last_snr REAL,
            latitude REAL,
            longitude REAL,
            altitude REAL,
            battery_level REAL,
            channel_utilization REAL,
            air_util_tx REAL,
            hops_away INTEGER,
            via_mqtt INTEGER,
            raw_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE node_metric_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_num INTEGER NOT NULL,
            recorded_at TEXT NOT NULL,
            channel_utilization REAL,
            air_util_tx REAL
        );

        CREATE TABLE traceroute_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_node_num INTEGER NOT NULL,
            requested_at TEXT NOT NULL,
            completed_at TEXT,
            hop_limit INTEGER NOT NULL,
            status TEXT NOT NULL,
            request_mesh_packet_id INTEGER,
            response_mesh_packet_id INTEGER,
            detail TEXT
        );
        """
    )
    connection.executemany(
        """
        INSERT INTO nodes (
            node_num,
            node_id,
            short_name,
            long_name,
            hardware_model,
            role,
            channel_index,
            last_heard_at,
            last_snr,
            latitude,
            longitude,
            altitude,
            battery_level,
            channel_utilization,
            air_util_tx,
            hops_away,
            via_mqtt,
            raw_json,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                101,
                "!00000065",
                "LOCAL",
                "Local Node",
                "TBEAM",
                "CLIENT",
                0,
                "2026-03-30T12:00:00Z",
                4.0,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                '{"num":101}',
                "2026-03-30T12:00:00Z",
            ),
            (
                202,
                "!000000ca",
                "BETA",
                "Beta Node",
                "TBEAM",
                "CLIENT",
                0,
                "2026-03-30T11:58:00Z",
                4.0,
                None,
                None,
                None,
                None,
                None,
                None,
                2,
                0,
                '{"num":202}',
                "2026-03-30T11:58:00Z",
            ),
            (
                303,
                "!0000012f",
                "GAMMA",
                "Gamma Node",
                "TBEAM",
                "CLIENT",
                0,
                "2026-03-30T11:57:00Z",
                4.0,
                None,
                None,
                None,
                None,
                None,
                None,
                3,
                0,
                '{"num":303}',
                "2026-03-30T11:57:00Z",
            ),
        ],
    )
    connection.executemany(
        """
        INSERT INTO packets (
            mesh_packet_id,
            received_at,
            from_node_num,
            to_node_num,
            portnum,
            channel_index,
            hop_limit,
            hop_start,
            rx_snr,
            rx_rssi,
            next_hop,
            relay_node,
            via_mqtt,
            transport_mechanism,
            text_preview,
            payload_base64,
            raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                11,
                "2026-03-30T11:45:00Z",
                202,
                BROADCAST_NODE_NUM,
                "TEXT_MESSAGE_APP",
                0,
                1,
                1,
                5.0,
                -90,
                None,
                None,
                0,
                None,
                "hello",
                None,
                "{}",
            ),
            (
                12,
                "2026-03-30T11:40:00Z",
                303,
                101,
                "TRACEROUTE_APP",
                0,
                3,
                3,
                4.5,
                -95,
                None,
                None,
                0,
                None,
                None,
                encode_traceroute_payload(
                    route=[202],
                    snr_towards=[20, 12],
                    route_back=[202],
                    snr_back=[16, 8],
                ),
                "{}",
            ),
            (
                13,
                "2026-03-30T11:35:00Z",
                202,
                BROADCAST_NODE_NUM,
                "TEXT_MESSAGE_APP",
                2,
                1,
                1,
                3.0,
                -98,
                None,
                None,
                0,
                None,
                "off channel",
                None,
                "{}",
            ),
        ],
    )
    connection.executemany(
        """
        INSERT INTO traceroute_attempts (
            target_node_num,
            requested_at,
            completed_at,
            hop_limit,
            status,
            request_mesh_packet_id,
            response_mesh_packet_id,
            detail
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (202, "2026-03-29T20:00:00Z", "2026-03-29T20:00:05Z", 2, "ack_only", 1, 2, "ack"),
            (202, "2026-03-30T05:30:00Z", "2026-03-30T05:30:05Z", 2, "ack_only", 3, 4, "ack"),
        ],
    )
    connection.commit()
    connection.close()

    repo = MeshRepository(db_path)

    with sqlite3.connect(db_path) as derived_connection:
        rollups = {
            row[0]: {
                "total_packets": row[1],
                "text_packets": row[2],
                "position_packets": row[3],
                "telemetry_packets": row[4],
                "mqtt_packets": row[5],
                "direct_packets": row[6],
                "relayed_packets": row[7],
            }
            for row in derived_connection.execute(
                """
                SELECT
                    scope,
                    total_packets,
                    text_packets,
                    position_packets,
                    telemetry_packets,
                    mqtt_packets,
                    direct_packets,
                    relayed_packets
                FROM packet_traffic_rollups
                ORDER BY scope
                """
            )
        }
        route_observation_count = derived_connection.execute(
            "SELECT COUNT(*) FROM route_observations"
        ).fetchone()[0]
        route_activity = {
            row[0]: (row[1], row[2])
            for row in derived_connection.execute(
                """
                SELECT node_num, last_route_seen_at, last_primary_route_seen_at
                FROM route_node_activity
                ORDER BY node_num
                """
            )
        }
        autotrace_state = derived_connection.execute(
            """
            SELECT target_node_num, last_activity_at, last_status, ack_only_streak
            FROM autotrace_target_state
            WHERE target_node_num = 202
            """
        ).fetchone()

    routes = repo.get_mesh_routes(primary_only=True)

    assert rollups == {
        "all": {
            "total_packets": 3,
            "text_packets": 2,
            "position_packets": 0,
            "telemetry_packets": 0,
            "mqtt_packets": 0,
            "direct_packets": 3,
            "relayed_packets": 0,
        },
        "primary": {
            "total_packets": 2,
            "text_packets": 1,
            "position_packets": 0,
            "telemetry_packets": 0,
            "mqtt_packets": 0,
            "direct_packets": 2,
            "relayed_packets": 0,
        },
    }
    assert route_observation_count == 2
    assert route_activity == {
        101: ("2026-03-30T11:40:00Z", "2026-03-30T11:40:00Z"),
        303: ("2026-03-30T11:40:00Z", "2026-03-30T11:40:00Z"),
    }
    assert autotrace_state == (202, "2026-03-30T05:30:05Z", "ack_only", 2)
    assert routes["stats"] == {"total": 2, "forward": 1, "return": 1}
    assert routes["routes"][0]["path_node_nums"] == [101, 202, 303]


def test_repository_tracks_autotrace_target_state_during_pending_and_completion(tmp_path):
    repo = MeshRepository(tmp_path / "mesh.db")

    first_attempt_id = repo.start_traceroute_attempt(
        target_node_num=202,
        requested_at="2026-03-30T05:30:00Z",
        hop_limit=3,
    )
    with sqlite3.connect(tmp_path / "mesh.db") as connection:
        pending_state = connection.execute(
            """
            SELECT last_activity_at, last_status, ack_only_streak
            FROM autotrace_target_state
            WHERE target_node_num = 202
            """
        ).fetchone()

    repo.complete_traceroute_attempt(
        first_attempt_id,
        completed_at="2026-03-30T05:30:05Z",
        status="ack_only",
        request_mesh_packet_id=11,
        response_mesh_packet_id=12,
        detail="ack only",
    )

    second_attempt_id = repo.start_traceroute_attempt(
        target_node_num=202,
        requested_at="2026-03-30T07:30:00Z",
        hop_limit=3,
    )
    repo.complete_traceroute_attempt(
        second_attempt_id,
        completed_at="2026-03-30T07:30:05Z",
        status="ack_only",
        request_mesh_packet_id=13,
        response_mesh_packet_id=14,
        detail="ack only",
    )

    with sqlite3.connect(tmp_path / "mesh.db") as connection:
        final_state = connection.execute(
            """
            SELECT last_activity_at, last_status, ack_only_streak
            FROM autotrace_target_state
            WHERE target_node_num = 202
            """
        ).fetchone()

    assert pending_state == ("2026-03-30T05:30:00Z", "pending", 0)
    assert final_state == ("2026-03-30T07:30:05Z", "ack_only", 2)


def test_repository_includes_top_senders_only_when_requested(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "meshseer.storage.utc_now",
        lambda: datetime(2026, 3, 30, 12, 30, tzinfo=UTC),
    )

    repo = MeshRepository(tmp_path / "mesh.db")
    for node_num, short_name in ((202, "BETA"), (303, "GAMMA")):
        repo.upsert_node(
            NodeRecord(
                node_num=node_num,
                node_id=f"!{node_num:08x}",
                short_name=short_name,
                long_name=f"{short_name} Node",
                hardware_model="TBEAM",
                role="CLIENT",
                channel_index=0,
                last_heard_at="2026-03-30T12:00:00Z",
                last_snr=4.0,
                latitude=None,
                longitude=None,
                altitude=None,
                battery_level=None,
                channel_utilization=None,
                air_util_tx=None,
                raw_json=f'{{"num":{node_num}}}',
                updated_at="2026-03-30T12:00:00Z",
                hops_away=1,
                via_mqtt=False,
            )
        )

    for mesh_packet_id, from_node_num in ((11, 202), (12, 202), (13, 303)):
        repo.insert_packet(
            PacketRecord(
                mesh_packet_id=mesh_packet_id,
                received_at=f"2026-03-30T12:{mesh_packet_id:02d}:00Z",
                from_node_num=from_node_num,
                to_node_num=BROADCAST_NODE_NUM,
                portnum="TEXT_MESSAGE_APP",
                channel_index=0,
                hop_limit=1,
                hop_start=1,
                rx_snr=4.0,
                rx_rssi=-90,
                text_preview="hello",
                payload_base64=None,
                raw_json="{}",
                via_mqtt=False,
            )
        )

    summary = repo.get_mesh_summary(primary_only=True)
    detailed = repo.get_mesh_summary(primary_only=True, include_top_senders=True, top_n=1)

    assert "top_senders" not in summary
    assert detailed["top_senders"] == [
        {
            "node_num": 202,
            "short_name": "BETA",
            "long_name": "BETA Node",
            "node_id": "!000000ca",
            "packet_count": 2,
            "mqtt_packets": 0,
            "direct_packets": 2,
            "relayed_packets": 0,
            "avg_rx_snr": 4.0,
            "last_heard_at": "2026-03-30T12:12:00Z",
        }
    ]


def test_repository_prunes_expired_data_and_rebuilds_derived_state(tmp_path):
    repo = MeshRepository(
        tmp_path / "mesh.db",
        packets_retention_days=30,
        node_metric_history_retention_days=30,
        traceroute_attempts_retention_days=90,
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
            last_heard_at="2026-04-01T12:00:00Z",
            last_snr=4.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=5.0,
            air_util_tx=1.2,
            raw_json='{"num":101}',
            updated_at="2026-04-01T12:00:00Z",
            hops_away=1,
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
            last_heard_at="2026-06-10T12:00:00Z",
            last_snr=4.5,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=7.5,
            air_util_tx=1.8,
            raw_json='{"num":101}',
            updated_at="2026-06-10T12:00:00Z",
            hops_away=1,
            via_mqtt=False,
        )
    )

    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=11,
            received_at="2026-04-01T12:05:00Z",
            from_node_num=202,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=1,
            hop_start=1,
            rx_snr=4.0,
            rx_rssi=-90,
            text_preview=None,
            payload_base64=encode_traceroute_payload(route=[], snr_towards=[20]),
            raw_json="{}",
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=12,
            received_at="2026-06-10T12:06:00Z",
            from_node_num=303,
            to_node_num=BROADCAST_NODE_NUM,
            portnum="TEXT_MESSAGE_APP",
            channel_index=0,
            hop_limit=1,
            hop_start=1,
            rx_snr=5.0,
            rx_rssi=-88,
            text_preview="fresh",
            payload_base64=None,
            raw_json="{}",
            via_mqtt=False,
        )
    )

    old_attempt_id = repo.start_traceroute_attempt(
        target_node_num=202,
        requested_at="2026-02-01T12:00:00Z",
        hop_limit=2,
    )
    repo.complete_traceroute_attempt(
        old_attempt_id,
        completed_at="2026-02-01T12:00:05Z",
        status="ack_only",
        request_mesh_packet_id=21,
        response_mesh_packet_id=22,
        detail="ack only",
    )
    fresh_attempt_id = repo.start_traceroute_attempt(
        target_node_num=303,
        requested_at="2026-06-10T12:00:00Z",
        hop_limit=1,
    )
    repo.complete_traceroute_attempt(
        fresh_attempt_id,
        completed_at="2026-06-10T12:00:05Z",
        status="success",
        request_mesh_packet_id=31,
        response_mesh_packet_id=32,
        detail=None,
    )

    summary = repo.run_maintenance(force=True, now=datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC))

    with sqlite3.connect(tmp_path / "mesh.db") as connection:
        packet_count = connection.execute("SELECT COUNT(*) FROM packets").fetchone()[0]
        node_metric_count = connection.execute("SELECT COUNT(*) FROM node_metric_history").fetchone()[0]
        traceroute_count = connection.execute("SELECT COUNT(*) FROM traceroute_attempts").fetchone()[0]
        route_observation_count = connection.execute("SELECT COUNT(*) FROM route_observations").fetchone()[0]
        rollup = connection.execute(
            """
            SELECT total_packets, text_packets, direct_packets
            FROM packet_traffic_rollups
            WHERE scope = 'primary'
            """
        ).fetchone()
        autotrace_state = connection.execute(
            """
            SELECT target_node_num, last_status
            FROM autotrace_target_state
            ORDER BY target_node_num
            """
        ).fetchall()

    assert summary == {
        "packets": 1,
        "node_metric_history": 1,
        "traceroute_attempts": 1,
        "route_observations": 1,
    }
    assert packet_count == 1
    assert node_metric_count == 1
    assert traceroute_count == 1
    assert route_observation_count == 0
    assert rollup == (1, 1, 1)
    assert autotrace_state == [(303, "success")]


def test_repository_default_retention_is_permanent(tmp_path):
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
            last_heard_at="2026-04-01T12:00:00Z",
            last_snr=4.0,
            latitude=None,
            longitude=None,
            altitude=None,
            battery_level=None,
            channel_utilization=5.0,
            air_util_tx=1.2,
            raw_json='{"num":101}',
            updated_at="2026-04-01T12:00:00Z",
            hops_away=1,
            via_mqtt=False,
        )
    )
    repo.insert_packet(
        PacketRecord(
            mesh_packet_id=11,
            received_at="2026-04-01T12:05:00Z",
            from_node_num=202,
            to_node_num=101,
            portnum="TRACEROUTE_APP",
            channel_index=0,
            hop_limit=1,
            hop_start=1,
            rx_snr=4.0,
            rx_rssi=-90,
            text_preview=None,
            payload_base64=encode_traceroute_payload(route=[], snr_towards=[20]),
            raw_json="{}",
            via_mqtt=False,
        )
    )
    attempt_id = repo.start_traceroute_attempt(
        target_node_num=202,
        requested_at="2026-02-01T12:00:00Z",
        hop_limit=2,
    )
    repo.complete_traceroute_attempt(
        attempt_id,
        completed_at="2026-02-01T12:00:05Z",
        status="ack_only",
        request_mesh_packet_id=21,
        response_mesh_packet_id=22,
        detail="ack only",
    )

    summary = repo.run_maintenance(force=True, now=datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC))

    with sqlite3.connect(tmp_path / "mesh.db") as connection:
        packet_count = connection.execute("SELECT COUNT(*) FROM packets").fetchone()[0]
        node_metric_count = connection.execute("SELECT COUNT(*) FROM node_metric_history").fetchone()[0]
        traceroute_count = connection.execute("SELECT COUNT(*) FROM traceroute_attempts").fetchone()[0]
        route_observation_count = connection.execute("SELECT COUNT(*) FROM route_observations").fetchone()[0]

    assert summary == {
        "packets": 0,
        "node_metric_history": 0,
        "traceroute_attempts": 0,
        "route_observations": 0,
    }
    assert packet_count == 1
    assert node_metric_count == 1
    assert traceroute_count == 1
    assert route_observation_count == 1
