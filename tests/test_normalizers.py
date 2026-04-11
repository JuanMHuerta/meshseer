from meshradar.normalizers import normalize_node, normalize_packet


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


def test_normalize_node_handles_missing_optional_fields():
    node = normalize_node(
        {"num": 7},
        now_provider=lambda: "2026-03-30T12:00:00Z",
    )

    assert node["channel_index"] is None
    assert node["node_id"] is None
    assert node["last_heard_at"] is None
    assert node["updated_at"] == "2026-03-30T12:00:00Z"
