from __future__ import annotations

import base64
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from meshtastic.protobuf import mesh_pb2

from meshradar.channels import BROADCAST_NODE_NUM
from meshradar.clock import timestamp_to_utc_iso, to_utc_iso, utc_now
from meshradar.models import NodeRecord, PacketRecord


KPI_ACTIVE_NODES_WINDOW_MINUTES = 180


class MeshRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row["name"] for row in rows}
        if column in existing:
            return
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _coerce_optional_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return int(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _coerce_optional_bool(value: Any) -> int | None:
        if isinstance(value, bool):
            return int(value)
        return None

    @staticmethod
    def _coerce_optional_string(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        name = getattr(value, "name", None)
        if isinstance(name, str):
            return name
        return str(value)

    @staticmethod
    def _backfill_node_channels(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT node_num, raw_json
            FROM nodes
            WHERE channel_index IS NULL
            """
        ).fetchall()
        updates: list[tuple[int, int]] = []
        for row in rows:
            try:
                raw = json.loads(row["raw_json"])
            except (TypeError, ValueError):
                continue
            channel_index = raw.get("channel")
            if isinstance(channel_index, int):
                updates.append((channel_index, row["node_num"]))
        if updates:
            connection.executemany(
                "UPDATE nodes SET channel_index = ? WHERE node_num = ?",
                updates,
            )

    @classmethod
    def _backfill_packet_metadata(cls, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT id, raw_json
            FROM packets
            WHERE hop_start IS NULL
               OR rx_rssi IS NULL
               OR next_hop IS NULL
               OR relay_node IS NULL
               OR via_mqtt IS NULL
               OR transport_mechanism IS NULL
            """
        ).fetchall()
        updates: list[tuple[int | None, int | None, int | None, int | None, int | None, str | None, int]] = []
        for row in rows:
            try:
                raw = json.loads(row["raw_json"])
            except (TypeError, ValueError):
                continue
            updates.append(
                (
                    cls._coerce_optional_int(raw.get("hopStart")),
                    cls._coerce_optional_int(raw.get("rxRssi")),
                    cls._coerce_optional_int(raw.get("nextHop")),
                    cls._coerce_optional_int(raw.get("relayNode")),
                    cls._coerce_optional_bool(raw.get("viaMqtt")),
                    cls._coerce_optional_string(raw.get("transportMechanism")),
                    row["id"],
                )
            )
        if updates:
            connection.executemany(
                """
                UPDATE packets
                SET hop_start = ?,
                    rx_rssi = ?,
                    next_hop = ?,
                    relay_node = ?,
                    via_mqtt = ?,
                    transport_mechanism = ?
                WHERE id = ?
                """,
                updates,
            )

    @classmethod
    def _backfill_node_metadata(cls, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT node_num, raw_json
            FROM nodes
            WHERE hops_away IS NULL
               OR via_mqtt IS NULL
            """
        ).fetchall()
        updates: list[tuple[int | None, int | None, int]] = []
        for row in rows:
            try:
                raw = json.loads(row["raw_json"])
            except (TypeError, ValueError):
                continue
            updates.append(
                (
                    cls._coerce_optional_int(raw.get("hopsAway")),
                    cls._coerce_optional_bool(raw.get("viaMqtt")),
                    row["node_num"],
                )
            )
        if updates:
            connection.executemany(
                """
                UPDATE nodes
                SET hops_away = ?,
                    via_mqtt = ?
                WHERE node_num = ?
                """,
                updates,
            )

    @staticmethod
    def _backfill_node_metric_history(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT
                node_num,
                updated_at,
                channel_utilization,
                air_util_tx
            FROM nodes
            WHERE updated_at IS NOT NULL
              AND (channel_utilization IS NOT NULL OR air_util_tx IS NOT NULL)
              AND NOT EXISTS (
                    SELECT 1
                    FROM node_metric_history
                    WHERE node_metric_history.node_num = nodes.node_num
              )
            """
        ).fetchall()
        if rows:
            connection.executemany(
                """
                INSERT INTO node_metric_history (
                    node_num,
                    recorded_at,
                    channel_utilization,
                    air_util_tx
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        row["node_num"],
                        row["updated_at"],
                        row["channel_utilization"],
                        row["air_util_tx"],
                    )
                    for row in rows
                ],
            )

    @classmethod
    def _packet_node_id(cls, packet: dict[str, Any]) -> str | None:
        try:
            raw = json.loads(packet.get("raw_json") or "{}")
        except (TypeError, ValueError):
            return None
        from_id = raw.get("fromId")
        return from_id if isinstance(from_id, str) and from_id else None

    @classmethod
    def _observe_packet_node_activity(
        cls,
        connection: sqlite3.Connection,
        packet: dict[str, Any],
    ) -> dict[str, Any] | None:
        node_num = cls._coerce_optional_int(packet.get("from_node_num"))
        received_at = packet.get("received_at")
        if node_num is None or not isinstance(received_at, str) or not received_at:
            return None

        packet_channel_index = cls._coerce_optional_int(packet.get("channel_index"))
        packet_via_mqtt = packet.get("via_mqtt")
        packet_node_id = cls._packet_node_id(packet)
        packet_rx_snr = cls._coerce_optional_float(packet.get("rx_snr"))

        row = connection.execute(
            "SELECT * FROM nodes WHERE node_num = ?",
            (node_num,),
        ).fetchone()
        existing = cls._row_to_dict(row)

        if existing is None:
            raw_json = json.dumps(
                {
                    "num": node_num,
                    "channel": packet_channel_index,
                    "viaMqtt": packet_via_mqtt,
                    "fromId": packet_node_id,
                    "inferredFromPackets": True,
                },
                separators=(",", ":"),
                sort_keys=True,
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
                    hops_away,
                    via_mqtt,
                    raw_json,
                    updated_at
                ) VALUES (?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?, ?)
                """,
                (
                    node_num,
                    packet_node_id,
                    packet_channel_index,
                    received_at,
                    packet_rx_snr,
                    None if packet_via_mqtt is None else int(bool(packet_via_mqtt)),
                    raw_json,
                    received_at,
                ),
            )
        else:
            new_last_heard_at = existing.get("last_heard_at")
            new_last_snr = existing.get("last_snr")
            if new_last_heard_at is None or str(new_last_heard_at) <= received_at:
                new_last_heard_at = received_at
                if packet_rx_snr is not None:
                    new_last_snr = packet_rx_snr

            new_channel_index = (
                existing.get("channel_index")
                if existing.get("channel_index") is not None
                else packet_channel_index
            )
            new_via_mqtt = existing.get("via_mqtt")
            if new_via_mqtt is None and packet_via_mqtt is not None:
                new_via_mqtt = bool(packet_via_mqtt)
            new_node_id = existing.get("node_id") or packet_node_id

            connection.execute(
                """
                UPDATE nodes
                SET node_id = ?,
                    channel_index = ?,
                    last_heard_at = ?,
                    last_snr = ?,
                    via_mqtt = ?
                WHERE node_num = ?
                """,
                (
                    new_node_id,
                    new_channel_index,
                    new_last_heard_at,
                    new_last_snr,
                    None if new_via_mqtt is None else int(bool(new_via_mqtt)),
                    node_num,
                ),
            )

        updated_row = connection.execute(
            "SELECT * FROM nodes WHERE node_num = ?",
            (node_num,),
        ).fetchone()
        return cls._row_to_dict(updated_row)

    @classmethod
    def _backfill_node_activity_from_packets(cls, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            f"""
            SELECT *
            FROM packets
            WHERE from_node_num IS NOT NULL
              AND {cls._primary_channel_clause()}
            ORDER BY received_at DESC, id DESC
            """
        ).fetchall()

        observed_node_nums: set[int] = set()
        for row in rows:
            packet = cls._row_to_dict(row)
            if packet is None:
                continue
            node_num = cls._coerce_optional_int(packet.get("from_node_num"))
            if node_num is None or node_num in observed_node_nums:
                continue
            cls._observe_packet_node_activity(connection, packet)
            observed_node_nums.add(node_num)

    @staticmethod
    def _append_node_metric_history(connection: sqlite3.Connection, node: NodeRecord) -> None:
        recorded_at = node.updated_at or node.last_heard_at
        if not recorded_at:
            return
        if node.channel_utilization is None and node.air_util_tx is None:
            return
        connection.execute(
            """
            INSERT OR IGNORE INTO node_metric_history (
                node_num,
                recorded_at,
                channel_utilization,
                air_util_tx
            ) VALUES (?, ?, ?, ?)
            """,
            (
                node.node_num,
                recorded_at,
                node.channel_utilization,
                node.air_util_tx,
            ),
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS packets (
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

                CREATE TABLE IF NOT EXISTS nodes (
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

                CREATE TABLE IF NOT EXISTS node_metric_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_num INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL,
                    channel_utilization REAL,
                    air_util_tx REAL
                );

                CREATE TABLE IF NOT EXISTS traceroute_attempts (
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
            self._ensure_column(connection, "packets", "hop_start", "INTEGER")
            self._ensure_column(connection, "packets", "rx_rssi", "INTEGER")
            self._ensure_column(connection, "packets", "next_hop", "INTEGER")
            self._ensure_column(connection, "packets", "relay_node", "INTEGER")
            self._ensure_column(connection, "packets", "via_mqtt", "INTEGER")
            self._ensure_column(connection, "packets", "transport_mechanism", "TEXT")
            self._ensure_column(connection, "nodes", "channel_index", "INTEGER")
            self._ensure_column(connection, "nodes", "hops_away", "INTEGER")
            self._ensure_column(connection, "nodes", "via_mqtt", "INTEGER")
            self._backfill_node_channels(connection)
            self._backfill_packet_metadata(connection)
            self._backfill_node_metadata(connection)
            self._backfill_node_activity_from_packets(connection)
            self._backfill_node_metric_history(connection)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_packets_received_at ON packets(received_at DESC);
                CREATE INDEX IF NOT EXISTS idx_packets_from_node_num ON packets(from_node_num);
                CREATE INDEX IF NOT EXISTS idx_packets_portnum ON packets(portnum);
                CREATE INDEX IF NOT EXISTS idx_packets_channel_index ON packets(channel_index);
                CREATE INDEX IF NOT EXISTS idx_packets_via_mqtt ON packets(via_mqtt);
                CREATE INDEX IF NOT EXISTS idx_nodes_last_heard_at ON nodes(last_heard_at DESC);
                CREATE INDEX IF NOT EXISTS idx_nodes_channel_index ON nodes(channel_index);
                CREATE INDEX IF NOT EXISTS idx_nodes_hops_away ON nodes(hops_away);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_node_metric_history_node_recorded_at
                    ON node_metric_history(node_num, recorded_at);
                CREATE INDEX IF NOT EXISTS idx_node_metric_history_recorded_at
                    ON node_metric_history(recorded_at DESC);
                CREATE INDEX IF NOT EXISTS idx_traceroute_attempts_target_requested_at
                    ON traceroute_attempts(target_node_num, requested_at DESC);
                CREATE INDEX IF NOT EXISTS idx_traceroute_attempts_requested_at
                    ON traceroute_attempts(requested_at DESC);
                """
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        payload = {key: row[key] for key in row.keys()}
        if "via_mqtt" in payload and payload["via_mqtt"] is not None:
            payload["via_mqtt"] = bool(payload["via_mqtt"])
        return payload

    @classmethod
    def _coerce_optional_float(cls, value: Any) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            try:
                return float(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _primary_channel_clause(column_name: str = "channel_index") -> str:
        return f"COALESCE({column_name}, 0) = 0"

    @staticmethod
    def _hops_taken(hop_start: int | None, hop_limit: int | None) -> int | None:
        if hop_start is None or hop_limit is None or hop_start < hop_limit:
            return None
        return hop_start - hop_limit

    @classmethod
    def _path_label(cls, packet: dict[str, Any] | None) -> str:
        if not packet:
            return "unknown"
        if packet.get("via_mqtt"):
            return "mqtt"
        hops_taken = cls._hops_taken(packet.get("hop_start"), packet.get("hop_limit"))
        if hops_taken is None:
            return "unknown"
        if hops_taken == 0:
            return "direct"
        if hops_taken == 1:
            return "1 hop"
        return f"{hops_taken} hops"

    @staticmethod
    def _where_clause(clauses: list[str]) -> str:
        return f"WHERE {' AND '.join(clauses)}" if clauses else ""

    @staticmethod
    def _parse_utc_iso(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None

    @classmethod
    def _activity_sort_key(cls, value: Any) -> float:
        parsed = cls._parse_utc_iso(value)
        if parsed is None:
            return float("-inf")
        return parsed.timestamp()

    @staticmethod
    def _max_timestamp(*values: str | None) -> str | None:
        items = [value for value in values if isinstance(value, str) and value]
        if not items:
            return None
        return max(items)

    @classmethod
    def _optional_timestamp_to_utc_iso(cls, value: Any) -> str | None:
        timestamp = cls._coerce_optional_int(value)
        if timestamp is None or timestamp <= 0:
            return None
        return timestamp_to_utc_iso(timestamp)

    @classmethod
    def _neighbor_reports_from_packet(cls, packet: dict[str, Any]) -> list[dict[str, Any]]:
        source_node_num = cls._coerce_optional_int(packet.get("from_node_num"))
        if source_node_num is None:
            return []

        info: dict[str, Any] | None = None
        payload_base64 = packet.get("payload_base64")
        if isinstance(payload_base64, str) and payload_base64:
            try:
                payload = base64.b64decode(payload_base64)
                proto = mesh_pb2.NeighborInfo()
                proto.ParseFromString(payload)
                info = {
                    "node_id": proto.node_id,
                    "neighbors": [
                        {
                            "node_id": neighbor.node_id,
                            "snr": neighbor.snr,
                            "last_rx_time": neighbor.last_rx_time,
                        }
                        for neighbor in proto.neighbors
                    ],
                }
            except Exception:
                info = None

        if info is None:
            try:
                raw_json = json.loads(packet.get("raw_json") or "{}")
            except (TypeError, ValueError):
                raw_json = {}
            decoded = raw_json.get("decoded", {})
            info = decoded.get("neighborinfo") if isinstance(decoded, dict) else None

        if not isinstance(info, dict):
            return []

        neighbors = info.get("neighbors")
        if not isinstance(neighbors, list):
            return []

        reported_at = packet.get("received_at")
        reports: list[dict[str, Any]] = []
        for neighbor in neighbors:
            if not isinstance(neighbor, dict):
                continue
            target_node_num = cls._coerce_optional_int(
                neighbor.get("node_id", neighbor.get("nodeId"))
            )
            if target_node_num is None or target_node_num == source_node_num:
                continue
            reports.append(
                {
                    "source_node_num": source_node_num,
                    "target_node_num": target_node_num,
                    "reported_at": reported_at,
                    "snr": cls._coerce_optional_float(neighbor.get("snr")),
                    "last_rx_time": cls._optional_timestamp_to_utc_iso(
                        neighbor.get("last_rx_time", neighbor.get("lastRxTime"))
                    ),
                }
            )
        return reports

    @classmethod
    def _coerce_optional_int_list(cls, value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        items: list[int] = []
        for entry in value:
            item = cls._coerce_optional_int(entry)
            if item is not None:
                items.append(item)
        return items

    @classmethod
    def _route_snr_values(cls, value: Any) -> list[float | None]:
        if not isinstance(value, list):
            return []
        values: list[float | None] = []
        for entry in value:
            snr = cls._coerce_optional_float(entry)
            if snr is None:
                values.append(None)
                continue
            values.append(None if snr == -128 else snr / 4.0)
        return values

    @staticmethod
    def _compress_path_nodes(node_nums: list[int]) -> list[int]:
        path: list[int] = []
        for node_num in node_nums:
            if path and path[-1] == node_num:
                continue
            path.append(node_num)
        return path

    @classmethod
    def _route_discovery_mapping(cls, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        return {
            "route": cls._coerce_optional_int_list(value.get("route")),
            "snr_towards": cls._route_snr_values(
                value.get("snr_towards", value.get("snrTowards"))
            ),
            "route_back": cls._coerce_optional_int_list(
                value.get("route_back", value.get("routeBack"))
            ),
            "snr_back": cls._route_snr_values(value.get("snr_back", value.get("snrBack"))),
        }

    @classmethod
    def _route_payload_from_packet(cls, packet: dict[str, Any]) -> dict[str, Any] | None:
        portnum = packet.get("portnum")
        payload_base64 = packet.get("payload_base64")

        if portnum == "TRACEROUTE_APP" and isinstance(payload_base64, str) and payload_base64:
            try:
                payload = base64.b64decode(payload_base64)
                proto = mesh_pb2.RouteDiscovery()
                proto.ParseFromString(payload)
                return {
                    "variant": "traceroute",
                    "route": list(proto.route),
                    "snr_towards": cls._route_snr_values(list(proto.snr_towards)),
                    "route_back": list(proto.route_back),
                    "snr_back": cls._route_snr_values(list(proto.snr_back)),
                }
            except Exception:
                pass

        if portnum == "ROUTING_APP" and isinstance(payload_base64, str) and payload_base64:
            try:
                payload = base64.b64decode(payload_base64)
                proto = mesh_pb2.Routing()
                proto.ParseFromString(payload)
                if proto.HasField("route_reply"):
                    route_reply = proto.route_reply
                    return {
                        "variant": "route_reply",
                        "route": list(route_reply.route),
                        "snr_towards": cls._route_snr_values(list(route_reply.snr_towards)),
                        "route_back": list(route_reply.route_back),
                        "snr_back": cls._route_snr_values(list(route_reply.snr_back)),
                    }
            except Exception:
                pass

        try:
            raw_json = json.loads(packet.get("raw_json") or "{}")
        except (TypeError, ValueError):
            raw_json = {}
        decoded = raw_json.get("decoded", {})
        if not isinstance(decoded, dict):
            return None

        if portnum == "TRACEROUTE_APP":
            route = cls._route_discovery_mapping(decoded.get("traceroute"))
            return {"variant": "traceroute", **route} if route is not None else None

        if portnum == "ROUTING_APP":
            routing = decoded.get("routing")
            if not isinstance(routing, dict):
                return None
            route_reply = cls._route_discovery_mapping(
                routing.get("route_reply", routing.get("routeReply"))
            )
            return {"variant": "route_reply", **route_reply} if route_reply is not None else None

        return None

    @classmethod
    def _route_record(
        cls,
        packet: dict[str, Any],
        *,
        variant: str,
        direction: str,
        source_node_num: int,
        destination_node_num: int,
        path_node_nums: list[int],
        edge_snr_db: list[float | None],
    ) -> dict[str, Any] | None:
        path = cls._compress_path_nodes(path_node_nums)
        if len(path) < 2:
            return None
        edge_count = len(path) - 1
        return {
            "packet_id": packet.get("id"),
            "mesh_packet_id": packet.get("mesh_packet_id"),
            "received_at": packet.get("received_at"),
            "portnum": packet.get("portnum"),
            "variant": variant,
            "direction": direction,
            "source_node_num": source_node_num,
            "destination_node_num": destination_node_num,
            "path_node_nums": path,
            "edge_snr_db": edge_snr_db if len(edge_snr_db) == edge_count else [],
            "hop_count": edge_count,
        }

    @classmethod
    def _routes_from_packet(cls, packet: dict[str, Any]) -> list[dict[str, Any]]:
        payload = cls._route_payload_from_packet(packet)
        if payload is None:
            return []

        from_node_num = cls._coerce_optional_int(packet.get("from_node_num"))
        to_node_num = cls._coerce_optional_int(packet.get("to_node_num"))
        if from_node_num is None or to_node_num is None:
            return []

        routes: list[dict[str, Any]] = []
        forward = cls._route_record(
            packet,
            variant=payload["variant"],
            direction="forward",
            source_node_num=to_node_num,
            destination_node_num=from_node_num,
            path_node_nums=[to_node_num, *payload["route"], from_node_num],
            edge_snr_db=payload["snr_towards"],
        )
        if forward is not None:
            routes.append(forward)

        route_back = payload["route_back"]
        snr_back = payload["snr_back"]
        if packet.get("hop_start") is not None and len(snr_back) == len(route_back) + 1:
            reverse = cls._route_record(
                packet,
                variant=payload["variant"],
                direction="return",
                source_node_num=from_node_num,
                destination_node_num=to_node_num,
                path_node_nums=[from_node_num, *route_back, to_node_num],
                edge_snr_db=snr_back,
            )
            if reverse is not None:
                routes.append(reverse)

        return routes

    def get_mesh_routes(
        self,
        *,
        since: str | None = None,
        primary_only: bool = False,
    ) -> dict[str, Any]:
        clauses = ["portnum IN (?, ?)"]
        params: list[Any] = ["TRACEROUTE_APP", "ROUTING_APP"]
        if since is not None:
            clauses.append("received_at >= ?")
            params.append(since)
        if primary_only:
            clauses.append(self._primary_channel_clause())
        where = self._where_clause(clauses)

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM packets
                {where}
                ORDER BY received_at DESC, id DESC
                """,
                params,
            ).fetchall()

        routes: list[dict[str, Any]] = []
        for row in rows:
            packet = self._row_to_dict(row)
            if packet is None:
                continue
            routes.extend(self._routes_from_packet(packet))

        routes.sort(
            key=lambda item: (
                item["received_at"] or "",
                item["packet_id"] or 0,
                int(item["direction"] == "forward"),
            ),
            reverse=True,
        )

        return {
            "routes": routes,
            "stats": {
                "total": len(routes),
                "forward": sum(1 for route in routes if route["direction"] == "forward"),
                "return": sum(1 for route in routes if route["direction"] == "return"),
            },
        }

    def get_mesh_links(self, *, primary_only: bool = False) -> dict[str, Any]:
        clauses = ["portnum = ?"]
        params: list[Any] = ["NEIGHBORINFO_APP"]
        if primary_only:
            clauses.append(self._primary_channel_clause())
        where = self._where_clause(clauses)

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM packets
                {where}
                ORDER BY received_at DESC, id DESC
                """,
                params,
            ).fetchall()

        directional: dict[tuple[int, int], dict[str, Any]] = {}
        for row in rows:
            packet = self._row_to_dict(row)
            if packet is None:
                continue
            for report in self._neighbor_reports_from_packet(packet):
                key = (report["source_node_num"], report["target_node_num"])
                aggregate = directional.get(key)
                if aggregate is None:
                    aggregate = {
                        "source_node_num": report["source_node_num"],
                        "target_node_num": report["target_node_num"],
                        "report_count": 0,
                        "snr_total": 0.0,
                        "snr_samples": 0,
                        "avg_snr": None,
                        "latest_snr": None,
                        "latest_reported_at": None,
                        "last_rx_time": None,
                    }
                    directional[key] = aggregate

                aggregate["report_count"] += 1
                if report["snr"] is not None:
                    aggregate["snr_total"] += report["snr"]
                    aggregate["snr_samples"] += 1
                    aggregate["avg_snr"] = aggregate["snr_total"] / aggregate["snr_samples"]

                if (
                    aggregate["latest_reported_at"] is None
                    or str(report["reported_at"]) > str(aggregate["latest_reported_at"])
                ):
                    aggregate["latest_reported_at"] = report["reported_at"]
                    aggregate["latest_snr"] = report["snr"]
                    aggregate["last_rx_time"] = report["last_rx_time"]

        paired: dict[tuple[int, int], dict[str, Any]] = {}
        for (source_node_num, target_node_num), report in directional.items():
            node_a_num, node_b_num = sorted((source_node_num, target_node_num))
            pair_key = (node_a_num, node_b_num)
            pair = paired.get(pair_key)
            if pair is None:
                pair = {
                    "node_a_num": node_a_num,
                    "node_b_num": node_b_num,
                    "a_to_b": None,
                    "b_to_a": None,
                    "report_count": 0,
                }
                paired[pair_key] = pair

            pair["report_count"] += report["report_count"]
            if source_node_num == node_a_num:
                pair["a_to_b"] = {
                    "source_node_num": source_node_num,
                    "target_node_num": target_node_num,
                    "report_count": report["report_count"],
                    "avg_snr": report["avg_snr"],
                    "latest_snr": report["latest_snr"],
                    "latest_reported_at": report["latest_reported_at"],
                    "last_rx_time": report["last_rx_time"],
                }
            else:
                pair["b_to_a"] = {
                    "source_node_num": source_node_num,
                    "target_node_num": target_node_num,
                    "report_count": report["report_count"],
                    "avg_snr": report["avg_snr"],
                    "latest_snr": report["latest_snr"],
                    "latest_reported_at": report["latest_reported_at"],
                    "last_rx_time": report["last_rx_time"],
                }

        links: list[dict[str, Any]] = []
        for pair in paired.values():
            directions = [direction for direction in (pair["a_to_b"], pair["b_to_a"]) if direction is not None]
            latest_reported_at = max(
                (direction["latest_reported_at"] for direction in directions if direction.get("latest_reported_at")),
                default=None,
            )
            avg_snr_values = [
                direction["avg_snr"]
                for direction in directions
                if direction.get("avg_snr") is not None
            ]
            links.append(
                {
                    "node_a_num": pair["node_a_num"],
                    "node_b_num": pair["node_b_num"],
                    "mutual": pair["a_to_b"] is not None and pair["b_to_a"] is not None,
                    "report_count": pair["report_count"],
                    "avg_snr": (
                        sum(avg_snr_values) / len(avg_snr_values)
                        if avg_snr_values else None
                    ),
                    "latest_reported_at": latest_reported_at,
                    "a_to_b": pair["a_to_b"],
                    "b_to_a": pair["b_to_a"],
                }
            )

        links.sort(
            key=lambda item: (
                int(bool(item["mutual"])),
                item["latest_reported_at"] or "",
                item["report_count"],
            ),
            reverse=True,
        )

        return {
            "neighbor_links": links,
            "stats": {
                "total": len(links),
                "mutual": sum(1 for link in links if link["mutual"]),
                "one_way": sum(1 for link in links if not link["mutual"]),
            },
        }

    @staticmethod
    def _ack_only_backoff_hours(
        attempt: dict[str, Any],
        *,
        ack_only_cooldown_hours: int,
        cooldown_hours: int,
    ) -> int:
        streak = attempt.get("ack_only_streak")
        if not isinstance(streak, int) or streak < 1:
            streak = 1
        base_hours = max(1, ack_only_cooldown_hours)
        cap_hours = max(1, cooldown_hours)
        return min(base_hours * streak, cap_hours)

    def _latest_attempts_by_node(self) -> dict[int, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    target_node_num,
                    status,
                    COALESCE(completed_at, requested_at) AS last_activity_at
                FROM traceroute_attempts
                ORDER BY target_node_num ASC, last_activity_at DESC, id DESC
                """
            ).fetchall()
        attempts_by_node: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            node_num = self._coerce_optional_int(row["target_node_num"])
            if node_num is None:
                continue
            last_activity_at = row["last_activity_at"]
            if isinstance(last_activity_at, str) and last_activity_at:
                attempts_by_node.setdefault(node_num, []).append(
                    {
                        "last_activity_at": last_activity_at,
                        "status": row["status"],
                    }
                )
        activity: dict[int, dict[str, Any]] = {}
        for node_num, attempts in attempts_by_node.items():
            latest = attempts[0]
            ack_only_streak = 0
            if latest.get("status") == "ack_only":
                for attempt in attempts:
                    if attempt.get("status") != "ack_only":
                        break
                    ack_only_streak += 1
            activity[node_num] = {
                "last_activity_at": latest["last_activity_at"],
                "status": latest["status"],
                "ack_only_streak": ack_only_streak,
            }
        return activity

    def _route_activity_by_node(self, *, primary_only: bool = False) -> dict[int, str]:
        activity: dict[int, str] = {}
        for route in self.get_mesh_routes(primary_only=primary_only)["routes"]:
            observed_at = route.get("received_at")
            if not isinstance(observed_at, str) or not observed_at:
                continue
            for key in ("source_node_num", "destination_node_num"):
                node_num = self._coerce_optional_int(route.get(key))
                if node_num is None:
                    continue
                activity[node_num] = self._max_timestamp(activity.get(node_num), observed_at) or observed_at
        return activity

    def _eligible_autotrace_nodes(
        self,
        *,
        local_node_num: int | None,
        target_window_hours: int,
        cooldown_hours: int,
        ack_only_cooldown_hours: int,
        primary_only: bool = False,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if local_node_num is None:
            return []

        now = utc_now() if now is None else now.astimezone(UTC)
        heard_cutoff = timestamp_to_utc_iso((now - timedelta(hours=target_window_hours)).timestamp())
        cooldown_cutoff = timestamp_to_utc_iso((now - timedelta(hours=cooldown_hours)).timestamp())
        clauses = [
            "node_num != ?",
            "COALESCE(via_mqtt, 0) = 0",
            "hops_away IS NOT NULL",
            "last_heard_at IS NOT NULL",
            "last_heard_at >= ?",
        ]
        params: list[Any] = [local_node_num, heard_cutoff]
        if primary_only:
            clauses.append(self._primary_channel_clause())
        where = self._where_clause(clauses)

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM nodes
                {where}
                """,
                params,
            ).fetchall()

        attempt_activity = self._latest_attempts_by_node()
        route_activity = self._route_activity_by_node(primary_only=primary_only)
        recent_attempt_nodes = set()
        for node_num, attempt in attempt_activity.items():
            last_activity_at = attempt.get("last_activity_at")
            if not isinstance(last_activity_at, str):
                continue
            status = attempt.get("status")
            if status == "ack_only":
                cutoff = timestamp_to_utc_iso(
                    (
                        now
                        - timedelta(
                            hours=self._ack_only_backoff_hours(
                                attempt,
                                ack_only_cooldown_hours=ack_only_cooldown_hours,
                                cooldown_hours=cooldown_hours,
                            )
                        )
                    ).timestamp()
                )
            else:
                cutoff = cooldown_cutoff
            if last_activity_at >= cutoff:
                recent_attempt_nodes.add(node_num)
        recent_route_nodes = {
            node_num
            for node_num, observed_at in route_activity.items()
            if isinstance(observed_at, str) and observed_at >= cooldown_cutoff
        }

        eligible: list[dict[str, Any]] = []
        for row in rows:
            node = self._row_to_dict(row)
            if node is None:
                continue
            node_num = self._coerce_optional_int(node.get("node_num"))
            if node_num is None:
                continue
            if node_num in recent_attempt_nodes or node_num in recent_route_nodes:
                continue
            node["last_trace_activity_at"] = self._max_timestamp(
                attempt_activity.get(node_num, {}).get("last_activity_at"),
                route_activity.get(node_num),
            )
            eligible.append(node)

        eligible.sort(
            key=lambda node: (
                0 if node.get("last_trace_activity_at") is None else 1,
                self._activity_sort_key(node.get("last_trace_activity_at")),
                -self._activity_sort_key(node.get("last_heard_at")),
                node.get("hops_away") if isinstance(node.get("hops_away"), int) else 999,
                node.get("node_num") or 0,
            )
        )
        return eligible

    def count_autotrace_candidates(
        self,
        *,
        local_node_num: int | None,
        target_window_hours: int,
        cooldown_hours: int,
        ack_only_cooldown_hours: int,
        primary_only: bool = False,
        now: datetime | None = None,
    ) -> int:
        return len(
            self._eligible_autotrace_nodes(
                local_node_num=local_node_num,
                target_window_hours=target_window_hours,
                cooldown_hours=cooldown_hours,
                ack_only_cooldown_hours=ack_only_cooldown_hours,
                primary_only=primary_only,
                now=now,
            )
        )

    def get_next_autotrace_target(
        self,
        *,
        local_node_num: int | None,
        target_window_hours: int,
        cooldown_hours: int,
        ack_only_cooldown_hours: int,
        primary_only: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        candidates = self._eligible_autotrace_nodes(
            local_node_num=local_node_num,
            target_window_hours=target_window_hours,
            cooldown_hours=cooldown_hours,
            ack_only_cooldown_hours=ack_only_cooldown_hours,
            primary_only=primary_only,
            now=now,
        )
        return candidates[0] if candidates else None

    def start_traceroute_attempt(
        self,
        *,
        target_node_num: int,
        requested_at: str,
        hop_limit: int,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
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
                ) VALUES (?, ?, NULL, ?, 'pending', NULL, NULL, NULL)
                """,
                (target_node_num, requested_at, hop_limit),
            )
            return int(cursor.lastrowid)

    def complete_traceroute_attempt(
        self,
        attempt_id: int,
        *,
        completed_at: str,
        status: str,
        request_mesh_packet_id: int | None,
        response_mesh_packet_id: int | None,
        detail: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE traceroute_attempts
                SET completed_at = ?,
                    status = ?,
                    request_mesh_packet_id = ?,
                    response_mesh_packet_id = ?,
                    detail = ?
                WHERE id = ?
                """,
                (
                    completed_at,
                    status,
                    request_mesh_packet_id,
                    response_mesh_packet_id,
                    detail,
                    attempt_id,
                ),
            )

    def list_recent_traceroute_attempts(self, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    a.*,
                    n.short_name AS target_short_name,
                    n.long_name AS target_long_name,
                    n.node_id AS target_node_id
                FROM traceroute_attempts AS a
                LEFT JOIN nodes AS n ON n.node_num = a.target_node_num
                ORDER BY COALESCE(a.completed_at, a.requested_at) DESC, a.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def get_last_traceroute_attempt(self) -> dict[str, Any] | None:
        attempts = self.list_recent_traceroute_attempts(limit=1)
        return attempts[0] if attempts else None

    def insert_packet(self, packet: PacketRecord) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
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
                (
                    packet.mesh_packet_id,
                    packet.received_at,
                    packet.from_node_num,
                    packet.to_node_num,
                    packet.portnum,
                    packet.channel_index,
                    packet.hop_limit,
                    packet.hop_start,
                    packet.rx_snr,
                    packet.rx_rssi,
                    packet.next_hop,
                    packet.relay_node,
                    None if packet.via_mqtt is None else int(packet.via_mqtt),
                    packet.transport_mechanism,
                    packet.text_preview,
                    packet.payload_base64,
                    packet.raw_json,
                ),
            )
            return int(cursor.lastrowid)

    def upsert_node(self, node: NodeRecord) -> None:
        with self._connect() as connection:
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
                    hops_away,
                    via_mqtt,
                    raw_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_num) DO UPDATE SET
                    node_id = excluded.node_id,
                    short_name = excluded.short_name,
                    long_name = excluded.long_name,
                    hardware_model = excluded.hardware_model,
                    role = excluded.role,
                    channel_index = excluded.channel_index,
                    last_heard_at = excluded.last_heard_at,
                    last_snr = excluded.last_snr,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    altitude = excluded.altitude,
                    battery_level = excluded.battery_level,
                    channel_utilization = excluded.channel_utilization,
                    air_util_tx = excluded.air_util_tx,
                    hops_away = excluded.hops_away,
                    via_mqtt = excluded.via_mqtt,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    node.node_num,
                    node.node_id,
                    node.short_name,
                    node.long_name,
                    node.hardware_model,
                    node.role,
                    node.channel_index,
                    node.last_heard_at,
                    node.last_snr,
                    node.latitude,
                    node.longitude,
                    node.altitude,
                    node.battery_level,
                    node.channel_utilization,
                    node.air_util_tx,
                    node.hops_away,
                    None if node.via_mqtt is None else int(node.via_mqtt),
                    node.raw_json,
                    node.updated_at,
                ),
            )
            self._append_node_metric_history(connection, node)

    def observe_packet_node_activity(self, packet: PacketRecord | Mapping[str, Any]) -> dict[str, Any] | None:
        payload = packet.to_dict() if isinstance(packet, PacketRecord) else dict(packet)
        with self._connect() as connection:
            return self._observe_packet_node_activity(connection, payload)

    def list_packets(
        self,
        *,
        limit: int = 50,
        since: str | None = None,
        from_node: int | None = None,
        portnum: str | None = None,
        primary_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if since is not None:
            clauses.append("received_at >= ?")
            params.append(since)
        if from_node is not None:
            clauses.append("from_node_num = ?")
            params.append(from_node)
        if portnum is not None:
            clauses.append("portnum = ?")
            params.append(portnum)
        if primary_only:
            clauses.append(self._primary_channel_clause())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        query = f"""
            SELECT *
            FROM packets
            {where}
            ORDER BY id DESC
            LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def list_packets_for_node(
        self,
        node_num: int,
        *,
        limit: int = 20,
        primary_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["(from_node_num = ? OR to_node_num = ?)"]
        params: list[Any] = [node_num, node_num]
        if primary_only:
            clauses.append(self._primary_channel_clause())
        where = " AND ".join(clauses)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM packets
                WHERE {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def list_chat_messages(self, *, limit: int = 50, primary_only: bool = False) -> list[dict[str, Any]]:
        clauses = [
            "p.portnum = ?",
            "p.text_preview IS NOT NULL",
            "TRIM(p.text_preview) != ''",
            "p.to_node_num = ?",
        ]
        params: list[Any] = ["TEXT_MESSAGE_APP", BROADCAST_NODE_NUM]
        if primary_only:
            clauses.append(self._primary_channel_clause("p.channel_index"))
        where = " AND ".join(clauses)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    p.*,
                    n.short_name AS from_short_name,
                    n.long_name AS from_long_name,
                    n.node_id AS from_node_id
                FROM packets AS p
                LEFT JOIN nodes AS n ON n.node_num = p.from_node_num
                WHERE {where}
                ORDER BY p.id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def get_packet(self, packet_id: int, *, primary_only: bool = False) -> dict[str, Any] | None:
        clauses = ["id = ?"]
        params: list[Any] = [packet_id]
        if primary_only:
            clauses.append(self._primary_channel_clause())
        where = " AND ".join(clauses)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM packets WHERE {where}",
                params,
            ).fetchone()
        return self._row_to_dict(row)

    def list_nodes(self, *, primary_only: bool = False) -> list[dict[str, Any]]:
        where = f"WHERE {self._primary_channel_clause()}" if primary_only else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM nodes
                {where}
                ORDER BY COALESCE(last_heard_at, '') DESC, node_num ASC
                """
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    @staticmethod
    def _node_has_coordinates(node: Mapping[str, Any]) -> bool:
        return node.get("latitude") is not None and node.get("longitude") is not None

    @classmethod
    def _node_is_mobile(cls, node: Mapping[str, Any]) -> bool:
        hardware = str(node.get("hardware_model") or "").upper()
        return "TRACKER" in hardware or "T1000" in hardware

    @classmethod
    def _node_is_active(
        cls,
        node: Mapping[str, Any],
        *,
        now: datetime,
        window_minutes: int,
    ) -> bool:
        last_heard_at = cls._parse_utc_iso(node.get("last_heard_at"))
        if last_heard_at is None:
            return False
        return last_heard_at >= now - timedelta(minutes=window_minutes)

    @classmethod
    def _node_is_stale(
        cls,
        node: Mapping[str, Any],
        *,
        now: datetime,
        stale_after_minutes: int = 24 * 60,
    ) -> bool:
        last_heard_at = cls._parse_utc_iso(node.get("last_heard_at"))
        if last_heard_at is None:
            return False
        return last_heard_at < now - timedelta(minutes=stale_after_minutes)

    @classmethod
    def _node_status(cls, node: Mapping[str, Any], *, local_node_num: int | None) -> str:
        node_num = cls._coerce_optional_int(node.get("node_num"))
        if node_num is not None and local_node_num is not None and node_num == local_node_num:
            return "local"
        if bool(node.get("via_mqtt")):
            return "mqtt"
        hops_away = cls._coerce_optional_int(node.get("hops_away"))
        if hops_away is not None and hops_away <= 1:
            return "direct"
        return "relayed"

    def list_nodes_roster(
        self,
        *,
        primary_only: bool = False,
        local_node_num: int | None = None,
        activity_window_minutes: int = 60,
        text_window_hours: int = 24,
    ) -> list[dict[str, Any]]:
        node_where = f"WHERE {self._primary_channel_clause()}" if primary_only else ""
        packet_clauses = ["from_node_num IS NOT NULL"]
        if primary_only:
            packet_clauses.append(self._primary_channel_clause())
        packet_where = self._where_clause(packet_clauses)

        now = utc_now().astimezone(UTC).replace(microsecond=0)
        activity_since_iso = to_utc_iso(now - timedelta(minutes=activity_window_minutes))
        text_since_iso = to_utc_iso(now - timedelta(hours=text_window_hours))

        with self._connect() as connection:
            node_rows = connection.execute(
                f"""
                SELECT *
                FROM nodes
                {node_where}
                ORDER BY COALESCE(last_heard_at, '') DESC, node_num ASC
                """
            ).fetchall()
            packet_rows = connection.execute(
                f"""
                SELECT
                    from_node_num AS node_num,
                    SUM(CASE WHEN received_at >= ? THEN 1 ELSE 0 END) AS activity_count_60m,
                    SUM(CASE
                        WHEN received_at >= ?
                             AND portnum = 'TEXT_MESSAGE_APP'
                        THEN 1 ELSE 0
                    END) AS text_count_24h
                FROM packets
                {packet_where}
                GROUP BY from_node_num
                """,
                [activity_since_iso, text_since_iso],
            ).fetchall()

        packet_stats_by_node_num = {
            int(row["node_num"]): {
                "activity_count_60m": int(row["activity_count_60m"] or 0),
                "has_text_traffic": int(row["text_count_24h"] or 0) > 0,
            }
            for row in packet_rows
            if row is not None and row["node_num"] is not None
        }

        items: list[dict[str, Any]] = []
        for row in node_rows:
            node = self._row_to_dict(row)
            if node is None:
                continue
            packet_stats = packet_stats_by_node_num.get(int(node["node_num"]), {})
            status = self._node_status(node, local_node_num=local_node_num)
            is_mobile = self._node_is_mobile(node)
            items.append(
                {
                    **node,
                    "status": status,
                    "is_active": self._node_is_active(
                        node,
                        now=now,
                        window_minutes=activity_window_minutes,
                    ),
                    "is_direct_rf": status == "direct",
                    "is_mapped": self._node_has_coordinates(node),
                    "is_mqtt": bool(node.get("via_mqtt")),
                    "is_stale": self._node_is_stale(node, now=now),
                    "mobility": "mobile" if is_mobile else "stationary",
                    "has_text_traffic": bool(packet_stats.get("has_text_traffic", False)),
                    "activity_count_60m": int(packet_stats.get("activity_count_60m", 0)),
                }
            )
        return items

    def get_node(self, node_num: int, *, primary_only: bool = False) -> dict[str, Any] | None:
        clauses = ["node_num = ?"]
        params: list[Any] = [node_num]
        if primary_only:
            clauses.append(self._primary_channel_clause())
        where = " AND ".join(clauses)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM nodes WHERE {where}",
                params,
            ).fetchone()
        return self._row_to_dict(row)

    def list_node_metric_history(
        self,
        node_num: int,
        *,
        limit: int = 24,
        primary_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["h.node_num = ?"]
        params: list[Any] = [node_num]
        if primary_only:
            clauses.append(self._primary_channel_clause("n.channel_index"))
        where = self._where_clause(clauses)

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    h.recorded_at,
                    h.channel_utilization,
                    h.air_util_tx
                FROM node_metric_history AS h
                LEFT JOIN nodes AS n ON n.node_num = h.node_num
                {where}
                ORDER BY h.recorded_at DESC, h.id DESC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()

        if rows:
            return [
                {
                    "recorded_at": row["recorded_at"],
                    "channel_utilization": row["channel_utilization"],
                    "air_util_tx": row["air_util_tx"],
                }
                for row in reversed(rows)
            ]

        node = self.get_node(node_num, primary_only=primary_only)
        if node is None or not isinstance(node.get("updated_at"), str):
            return []
        if node.get("channel_utilization") is None and node.get("air_util_tx") is None:
            return []
        return [
            {
                "recorded_at": node["updated_at"],
                "channel_utilization": node.get("channel_utilization"),
                "air_util_tx": node.get("air_util_tx"),
            }
        ]

    def summarize_node_metric_window(
        self,
        node_num: int,
        *,
        window_minutes: int,
        primary_only: bool = False,
    ) -> dict[str, Any]:
        now = utc_now().astimezone(UTC).replace(microsecond=0)
        window_start = now - timedelta(minutes=window_minutes)
        window_start_iso = to_utc_iso(window_start)
        window_end_iso = to_utc_iso(now)

        clauses = [
            "h.node_num = ?",
            "h.recorded_at >= ?",
            "h.recorded_at <= ?",
        ]
        params: list[Any] = [node_num, window_start_iso, window_end_iso]
        if primary_only:
            clauses.append(self._primary_channel_clause("n.channel_index"))
        where = self._where_clause(clauses)

        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS sample_count,
                    AVG(h.channel_utilization) AS channel_utilization_avg,
                    AVG(h.air_util_tx) AS air_util_tx_avg
                FROM node_metric_history AS h
                LEFT JOIN nodes AS n ON n.node_num = h.node_num
                {where}
                """,
                params,
            ).fetchone()

        sample_count = int(row["sample_count"] or 0) if row is not None else 0
        if sample_count:
            return {
                "window_minutes": int(window_minutes),
                "channel_utilization_avg": None if row is None else row["channel_utilization_avg"],
                "air_util_tx_avg": None if row is None else row["air_util_tx_avg"],
                "sample_count": sample_count,
            }

        node = self.get_node(node_num, primary_only=primary_only)
        recorded_at = self._parse_utc_iso(node.get("updated_at")) if node is not None else None
        if recorded_at is not None and window_start <= recorded_at <= now:
            if node.get("channel_utilization") is not None or node.get("air_util_tx") is not None:
                return {
                    "window_minutes": int(window_minutes),
                    "channel_utilization_avg": node.get("channel_utilization"),
                    "air_util_tx_avg": node.get("air_util_tx"),
                    "sample_count": 1,
                }

        return {
            "window_minutes": int(window_minutes),
            "channel_utilization_avg": None,
            "air_util_tx_avg": None,
            "sample_count": 0,
        }

    def healthcheck(self) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT 1 AS ok").fetchone()
        return bool(row and row["ok"] == 1)

    def get_node_insights(self, node_num: int, *, primary_only: bool = False) -> dict[str, Any]:
        clauses = ["(from_node_num = ? OR to_node_num = ?)"]
        params: list[Any] = [node_num, node_num]
        if primary_only:
            clauses.append(self._primary_channel_clause())
        where = self._where_clause(clauses)
        hops_taken_expr = "CASE WHEN hop_start IS NOT NULL AND hop_limit IS NOT NULL AND hop_start >= hop_limit THEN hop_start - hop_limit END"
        with self._connect() as connection:
            aggregate = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS heard_packets,
                    SUM(CASE WHEN to_node_num = ? THEN 1 ELSE 0 END) AS broadcast_packets,
                    SUM(CASE WHEN COALESCE(via_mqtt, 0) = 1 THEN 1 ELSE 0 END) AS mqtt_packets,
                    SUM(CASE WHEN COALESCE(via_mqtt, 0) = 0 AND {hops_taken_expr} = 0 THEN 1 ELSE 0 END) AS direct_packets,
                    SUM(CASE WHEN COALESCE(via_mqtt, 0) = 0 AND {hops_taken_expr} > 0 THEN 1 ELSE 0 END) AS relayed_packets,
                    AVG(rx_snr) AS avg_rx_snr,
                    MAX(rx_snr) AS best_rx_snr,
                    MIN(rx_snr) AS worst_rx_snr
                FROM packets
                {where}
                """,
                [BROADCAST_NODE_NUM, *params],
            ).fetchone()
            latest_packet = connection.execute(
                f"""
                SELECT *
                FROM packets
                {where}
                ORDER BY id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        latest_payload = self._row_to_dict(latest_packet)
        return {
            "heard_packets": int(aggregate["heard_packets"] or 0) if aggregate is not None else 0,
            "broadcast_packets": int(aggregate["broadcast_packets"] or 0) if aggregate is not None else 0,
            "mqtt_packets": int(aggregate["mqtt_packets"] or 0) if aggregate is not None else 0,
            "direct_packets": int(aggregate["direct_packets"] or 0) if aggregate is not None else 0,
            "relayed_packets": int(aggregate["relayed_packets"] or 0) if aggregate is not None else 0,
            "avg_rx_snr": aggregate["avg_rx_snr"] if aggregate is not None else None,
            "best_rx_snr": aggregate["best_rx_snr"] if aggregate is not None else None,
            "worst_rx_snr": aggregate["worst_rx_snr"] if aggregate is not None else None,
            "last_path": self._path_label(latest_payload),
            "last_hops_taken": None if latest_payload is None else self._hops_taken(latest_payload.get("hop_start"), latest_payload.get("hop_limit")),
            "last_next_hop": None if latest_payload is None else latest_payload.get("next_hop"),
            "last_relay_node": None if latest_payload is None else latest_payload.get("relay_node"),
            "last_portnum": None if latest_payload is None else latest_payload.get("portnum"),
            "last_seen_at": None if latest_payload is None else latest_payload.get("received_at"),
        }

    def get_mesh_summary(
        self,
        *,
        primary_only: bool = False,
        exclude_node_num: int | None = None,
        top_n: int = 5,
        window_minutes: int = 60,
    ) -> dict[str, Any]:
        node_clauses: list[str] = []
        node_params: list[Any] = []
        if primary_only:
            node_clauses.append(self._primary_channel_clause())
        if exclude_node_num is not None:
            node_clauses.append("node_num != ?")
            node_params.append(exclude_node_num)
        node_where = self._where_clause(node_clauses)

        packet_clauses: list[str] = []
        packet_params: list[Any] = []
        if primary_only:
            packet_clauses.append(self._primary_channel_clause("p.channel_index"))
        packet_where = self._where_clause(packet_clauses)
        hops_taken_expr = "CASE WHEN p.hop_start IS NOT NULL AND p.hop_limit IS NOT NULL AND p.hop_start >= p.hop_limit THEN p.hop_start - p.hop_limit END"
        now = utc_now().astimezone(UTC).replace(microsecond=0)
        current_window_start = now - timedelta(minutes=window_minutes)
        previous_window_start = current_window_start - timedelta(minutes=window_minutes)
        active_nodes_window_start = now - timedelta(minutes=KPI_ACTIVE_NODES_WINDOW_MINUTES)
        current_window_end_iso = to_utc_iso(now)
        current_window_start_iso = to_utc_iso(current_window_start)
        previous_window_start_iso = to_utc_iso(previous_window_start)
        active_nodes_window_start_iso = to_utc_iso(active_nodes_window_start)

        with self._connect() as connection:
            node_row = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS total_nodes,
                    SUM(CASE
                        WHEN last_heard_at IS NOT NULL
                             AND last_heard_at >= ?
                             AND last_heard_at <= ?
                        THEN 1 ELSE 0
                    END) AS active_nodes_3h,
                    SUM(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 ELSE 0 END) AS mapped_nodes,
                    SUM(CASE WHEN COALESCE(via_mqtt, 0) = 1 THEN 1 ELSE 0 END) AS mqtt_nodes,
                    SUM(CASE WHEN hops_away IS NOT NULL AND hops_away <= 1 THEN 1 ELSE 0 END) AS direct_nodes,
                    SUM(CASE WHEN hops_away > 1 THEN 1 ELSE 0 END) AS multi_hop_nodes,
                    SUM(CASE WHEN hops_away IS NULL AND COALESCE(via_mqtt, 0) = 0 THEN 1 ELSE 0 END) AS unknown_path_nodes
                FROM nodes
                {node_where}
                """,
                [active_nodes_window_start_iso, current_window_end_iso, *node_params],
            ).fetchone()
            traffic_row = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS total_packets,
                    SUM(CASE WHEN portnum = 'TEXT_MESSAGE_APP' THEN 1 ELSE 0 END) AS text_packets,
                    SUM(CASE WHEN portnum LIKE '%POSITION%' THEN 1 ELSE 0 END) AS position_packets,
                    SUM(CASE WHEN
                        portnum LIKE '%TELEMETRY%'
                        OR portnum LIKE '%NODEINFO%'
                        OR portnum LIKE '%NEIGHBORINFO%'
                        OR portnum LIKE '%STORE_FORWARD%'
                        OR portnum LIKE '%PAXCOUNTER%'
                        OR portnum LIKE '%AIRQUALITY%'
                    THEN 1 ELSE 0 END) AS telemetry_packets,
                    SUM(CASE WHEN COALESCE(via_mqtt, 0) = 1 THEN 1 ELSE 0 END) AS mqtt_packets,
                    SUM(CASE WHEN COALESCE(via_mqtt, 0) = 0 AND {hops_taken_expr} = 0 THEN 1 ELSE 0 END) AS direct_packets,
                    SUM(CASE WHEN COALESCE(via_mqtt, 0) = 0 AND {hops_taken_expr} > 0 THEN 1 ELSE 0 END) AS relayed_packets
                FROM packets AS p
                {packet_where}
                """,
                packet_params,
            ).fetchone()
            window_row = connection.execute(
                f"""
                SELECT
                    COUNT(CASE WHEN p.received_at >= ? AND p.received_at < ? THEN 1 END) AS current_packet_count,
                    COUNT(CASE WHEN p.received_at >= ? AND p.received_at < ? THEN 1 END) AS previous_packet_count,
                    COUNT(DISTINCT CASE
                        WHEN p.received_at >= ?
                             AND p.received_at < ?
                             AND p.from_node_num IS NOT NULL
                             AND (? IS NULL OR p.from_node_num != ?)
                        THEN p.from_node_num
                    END) AS current_active_nodes,
                    COUNT(DISTINCT CASE
                        WHEN p.received_at >= ?
                             AND p.received_at < ?
                             AND p.from_node_num IS NOT NULL
                             AND (? IS NULL OR p.from_node_num != ?)
                        THEN p.from_node_num
                    END) AS previous_active_nodes,
                    SUM(CASE
                        WHEN p.received_at >= ?
                             AND p.received_at < ?
                             AND COALESCE(p.via_mqtt, 0) = 1
                        THEN 1 ELSE 0
                    END) AS current_mqtt_packets,
                    SUM(CASE
                        WHEN p.received_at >= ?
                             AND p.received_at < ?
                             AND COALESCE(p.via_mqtt, 0) = 1
                        THEN 1 ELSE 0
                    END) AS previous_mqtt_packets,
                    SUM(CASE
                        WHEN p.received_at >= ?
                             AND p.received_at < ?
                             AND COALESCE(p.via_mqtt, 0) = 0
                             AND {hops_taken_expr} = 0
                        THEN 1 ELSE 0
                    END) AS current_direct_packets,
                    SUM(CASE
                        WHEN p.received_at >= ?
                             AND p.received_at < ?
                             AND COALESCE(p.via_mqtt, 0) = 0
                             AND {hops_taken_expr} = 0
                        THEN 1 ELSE 0
                    END) AS previous_direct_packets,
                    SUM(CASE
                        WHEN p.received_at >= ?
                             AND p.received_at < ?
                             AND COALESCE(p.via_mqtt, 0) = 0
                             AND {hops_taken_expr} > 0
                        THEN 1 ELSE 0
                    END) AS current_relayed_packets,
                    SUM(CASE
                        WHEN p.received_at >= ?
                             AND p.received_at < ?
                             AND COALESCE(p.via_mqtt, 0) = 0
                             AND {hops_taken_expr} > 0
                        THEN 1 ELSE 0
                    END) AS previous_relayed_packets,
                    AVG(CASE
                        WHEN p.received_at >= ?
                             AND p.received_at < ?
                             AND COALESCE(p.via_mqtt, 0) = 0
                             AND {hops_taken_expr} IS NOT NULL
                        THEN {hops_taken_expr}
                    END) AS current_avg_hops,
                    AVG(CASE
                        WHEN p.received_at >= ?
                             AND p.received_at < ?
                             AND COALESCE(p.via_mqtt, 0) = 0
                             AND {hops_taken_expr} IS NOT NULL
                        THEN {hops_taken_expr}
                    END) AS previous_avg_hops
                FROM packets AS p
                {packet_where}
                """,
                [
                    current_window_start_iso,
                    current_window_end_iso,
                    previous_window_start_iso,
                    current_window_start_iso,
                    current_window_start_iso,
                    current_window_end_iso,
                    exclude_node_num,
                    exclude_node_num,
                    previous_window_start_iso,
                    current_window_start_iso,
                    exclude_node_num,
                    exclude_node_num,
                    current_window_start_iso,
                    current_window_end_iso,
                    previous_window_start_iso,
                    current_window_start_iso,
                    current_window_start_iso,
                    current_window_end_iso,
                    previous_window_start_iso,
                    current_window_start_iso,
                    current_window_start_iso,
                    current_window_end_iso,
                    previous_window_start_iso,
                    current_window_start_iso,
                    current_window_start_iso,
                    current_window_end_iso,
                    previous_window_start_iso,
                    current_window_start_iso,
                ],
            ).fetchone()
            top_rows = connection.execute(
                f"""
                SELECT
                    p.from_node_num AS node_num,
                    n.short_name,
                    n.long_name,
                    n.node_id,
                    COUNT(*) AS packet_count,
                    SUM(CASE WHEN COALESCE(p.via_mqtt, 0) = 1 THEN 1 ELSE 0 END) AS mqtt_packets,
                    SUM(CASE WHEN COALESCE(p.via_mqtt, 0) = 0 AND {hops_taken_expr} = 0 THEN 1 ELSE 0 END) AS direct_packets,
                    SUM(CASE WHEN COALESCE(p.via_mqtt, 0) = 0 AND {hops_taken_expr} > 0 THEN 1 ELSE 0 END) AS relayed_packets,
                    AVG(p.rx_snr) AS avg_rx_snr,
                    MAX(p.received_at) AS last_heard_at
                FROM packets AS p
                LEFT JOIN nodes AS n ON n.node_num = p.from_node_num
                {packet_where} {"AND" if packet_where else "WHERE"} p.from_node_num IS NOT NULL
                GROUP BY p.from_node_num
                ORDER BY packet_count DESC, last_heard_at DESC
                LIMIT ?
                """,
                [*packet_params, top_n],
            ).fetchall()

        def window_payload(prefix: str) -> dict[str, Any]:
            if window_row is None:
                return {
                    "active_nodes": 0,
                    "packet_count": 0,
                    "direct_packets": 0,
                    "relayed_packets": 0,
                    "mqtt_packets": 0,
                    "avg_hops": None,
                }
            return {
                "active_nodes": int(window_row[f"{prefix}_active_nodes"] or 0),
                "packet_count": int(window_row[f"{prefix}_packet_count"] or 0),
                "direct_packets": int(window_row[f"{prefix}_direct_packets"] or 0),
                "relayed_packets": int(window_row[f"{prefix}_relayed_packets"] or 0),
                "mqtt_packets": int(window_row[f"{prefix}_mqtt_packets"] or 0),
                "avg_hops": window_row[f"{prefix}_avg_hops"],
            }

        return {
            "nodes": {
                "total": int(node_row["total_nodes"] or 0) if node_row is not None else 0,
                "active_3h": int(node_row["active_nodes_3h"] or 0) if node_row is not None else 0,
                "mapped": int(node_row["mapped_nodes"] or 0) if node_row is not None else 0,
                "direct": int(node_row["direct_nodes"] or 0) if node_row is not None else 0,
                "multi_hop": int(node_row["multi_hop_nodes"] or 0) if node_row is not None else 0,
                "mqtt": int(node_row["mqtt_nodes"] or 0) if node_row is not None else 0,
                "unknown_path": int(node_row["unknown_path_nodes"] or 0) if node_row is not None else 0,
            },
            "traffic": {
                "packets": int(traffic_row["total_packets"] or 0) if traffic_row is not None else 0,
                "text": int(traffic_row["text_packets"] or 0) if traffic_row is not None else 0,
                "position": int(traffic_row["position_packets"] or 0) if traffic_row is not None else 0,
                "telemetry": int(traffic_row["telemetry_packets"] or 0) if traffic_row is not None else 0,
                "mqtt": int(traffic_row["mqtt_packets"] or 0) if traffic_row is not None else 0,
                "direct": int(traffic_row["direct_packets"] or 0) if traffic_row is not None else 0,
                "relayed": int(traffic_row["relayed_packets"] or 0) if traffic_row is not None else 0,
            },
            "windowed_activity": {
                "window_minutes": int(window_minutes),
                "current": window_payload("current"),
                "previous": window_payload("previous"),
            },
            "top_senders": [
                {
                    "node_num": row["node_num"],
                    "short_name": row["short_name"],
                    "long_name": row["long_name"],
                    "node_id": row["node_id"],
                    "packet_count": int(row["packet_count"] or 0),
                    "mqtt_packets": int(row["mqtt_packets"] or 0),
                    "direct_packets": int(row["direct_packets"] or 0),
                    "relayed_packets": int(row["relayed_packets"] or 0),
                    "avg_rx_snr": row["avg_rx_snr"],
                    "last_heard_at": row["last_heard_at"],
                }
                for row in top_rows
            ],
        }
