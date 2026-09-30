import json

from meshtastic.protobuf import mesh_pb2

from meshseer.normalizers import normalize_node, normalize_packet


class ProtoLike:
    def __str__(self):
        return "proto-like"


def test_normalize_packet_sanitizes_bytes_lists_and_tuples():
    packet = normalize_packet(
        {
            "id": 8,
            "from": 1,
            "to": 2,
            "decoded": {
                "portnum": "PRIVATE_APP",
                "payload": b"\x01\x02",
                "history": [b"\x03", (b"\x04",)],
            },
        },
        now_provider=lambda: "2026-03-30T12:00:00Z",
    )

    assert packet["received_at"] == "2026-03-30T12:00:00Z"
    assert packet["payload_base64"] == "AQI="
    assert '"history": ["Aw==", ["BA=="]]' in packet["raw_json"]


def test_normalize_packet_sanitizes_unknown_objects():
    packet = normalize_packet(
        {
            "id": 10,
            "decoded": {
                "portnum": "POSITION_APP",
                "position": ProtoLike(),
            },
        },
        now_provider=lambda: "2026-03-30T12:00:00Z",
    )

    assert '"position": "proto-like"' in packet["raw_json"]


def test_normalize_packet_serializes_protobuf_messages_and_repeated_fields():
    traceroute = mesh_pb2.RouteDiscovery()
    traceroute.route.extend([101, 202])
    traceroute.snr_towards.extend([20, 10])

    packet = normalize_packet(
        {
            "id": 11,
            "from": 101,
            "to": 202,
            "decoded": {
                "portnum": "TRACEROUTE_APP",
                "traceroute": traceroute,
                "payload": traceroute.SerializeToString(),
            },
        },
        now_provider=lambda: "2026-03-30T12:00:00Z",
    )

    raw_json = json.loads(packet["raw_json"])

    assert raw_json["decoded"]["traceroute"]["route"] == [101, 202]
    assert raw_json["decoded"]["traceroute"]["snr_towards"] == [20, 10]


def test_normalize_packet_serializes_protobuf_repeated_composite_fields():
    neighborinfo = mesh_pb2.NeighborInfo(node_id=101)
    neighbor = neighborinfo.neighbors.add()
    neighbor.node_id = 303
    neighbor.snr = 5.0
    neighbor.last_rx_time = 123

    packet = normalize_packet(
        {
            "id": 12,
            "from": 101,
            "to": 202,
            "decoded": {
                "portnum": "NEIGHBORINFO_APP",
                "neighborinfo": neighborinfo,
                "payload": neighborinfo.SerializeToString(),
            },
        },
        now_provider=lambda: "2026-03-30T12:00:00Z",
    )

    raw_json = json.loads(packet["raw_json"])

    assert raw_json["decoded"]["neighborinfo"]["node_id"] == 101
    assert raw_json["decoded"]["neighborinfo"]["neighbors"][0]["node_id"] == 303
    assert raw_json["decoded"]["neighborinfo"]["neighbors"][0]["snr"] == 5.0
    assert int(raw_json["decoded"]["neighborinfo"]["neighbors"][0]["last_rx_time"]) == 123


def test_normalize_node_handles_missing_optional_fields():
    node = normalize_node(
        {"num": 7},
        now_provider=lambda: "2026-03-30T12:00:00Z",
    )

    assert node["channel_index"] is None
    assert node["node_id"] is None
    assert node["last_heard_at"] is None
    assert node["updated_at"] == "2026-03-30T12:00:00Z"
