from __future__ import annotations

import math
from typing import Any, Mapping

from meshseer.channels import BROADCAST_NODE_NUM


PUBLIC_PACKET_FIELDS = (
    "id",
    "received_at",
    "from_node_num",
    "to_node_num",
    "portnum",
    "rx_snr",
    "relay_node",
    "next_hop",
)

PUBLIC_CHAT_FIELDS = (
    "id",
    "received_at",
    "text_preview",
)

PUBLIC_NODE_RECENT_PACKET_FIELDS = (
    "id",
    "received_at",
    "to_node_num",
    "portnum",
    "text_preview",
    "rx_snr",
    "relay_node",
    "next_hop",
)

PUBLIC_NODE_FIELDS = (
    "node_num",
    "node_id",
    "short_name",
    "long_name",
    "hardware_model",
    "role",
    "last_heard_at",
    "last_snr",
    "latitude",
    "longitude",
    "battery_level",
    "channel_utilization",
    "air_util_tx",
    "hops_away",
    "via_mqtt",
    "status",
    "is_active",
    "is_direct_rf",
    "is_mapped",
    "is_mqtt",
    "is_stale",
    "activity_count_60m",
)

PUBLIC_NODE_DETAIL_FIELDS = tuple(
    [field for field in PUBLIC_NODE_FIELDS if field not in {"latitude", "longitude"}] + ["first_heard_at"]
)

PUBLIC_NODE_INSIGHTS_FIELDS = (
    "heard_packets",
    "sent_packets",
    "broadcast_packets",
    "mqtt_packets",
    "direct_packets",
    "relayed_packets",
    "text_packets",
    "position_packets",
    "telemetry_packets",
    "avg_rx_snr",
    "best_rx_snr",
    "worst_rx_snr",
    "last_path",
    "last_hops_taken",
    "last_portnum",
    "last_seen_at",
)

PUBLIC_TRACEROUTE_ATTEMPT_FIELDS = (
    "id",
    "target_node_num",
    "requested_at",
    "completed_at",
    "hop_limit",
    "status",
    "request_mesh_packet_id",
    "response_mesh_packet_id",
    "detail",
)

PUBLIC_TRACEROUTE_ROUTE_FIELDS = (
    "mesh_packet_id",
    "received_at",
    "direction",
    "source_node_num",
    "destination_node_num",
    "path_node_nums",
    "hop_count",
)

PUBLIC_NODE_METRIC_HISTORY_FIELDS = (
    "recorded_at",
    "channel_utilization",
    "air_util_tx",
)

PUBLIC_COMPLETE_TRACEROUTE_FIELDS = (
    "mesh_packet_id",
    "received_at",
    "request_mesh_packet_id",
    "discovery_request_id",
    "forward_path_node_nums",
    "return_path_node_nums",
    "full_path_node_nums",
    "hop_count",
)


def _pick(mapping: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: mapping.get(field) for field in fields}


def _obfuscated_coordinate(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return math.trunc(numeric * 10_000) / 10_000


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _packet_path_tone(packet: Mapping[str, Any], *, local_node_num: int | None = None) -> str:
    if packet.get("via_mqtt"):
        return "mqtt"
    from_node_num = _coerce_int(packet.get("from_node_num"))
    if local_node_num is not None and from_node_num == local_node_num:
        return "local"
    relay_node = _coerce_int(packet.get("relay_node"))
    next_hop = _coerce_int(packet.get("next_hop"))
    delivered_by = relay_node if relay_node is not None else next_hop
    if delivered_by == 0:
        return "local"
    hop_start = _coerce_int(packet.get("hop_start"))
    hop_limit = _coerce_int(packet.get("hop_limit"))
    if hop_start is None or hop_limit is None or hop_start < hop_limit:
        return "unknown"
    return "direct" if hop_start == hop_limit else "relayed"


def _packet_path_label(packet: Mapping[str, Any], *, local_node_num: int | None = None) -> str:
    tone = _packet_path_tone(packet, local_node_num=local_node_num)
    if tone == "mqtt":
        return "MQTT"
    if tone == "local":
        return "Local"
    if tone == "unknown":
        return "Unknown"
    hop_start = _coerce_int(packet.get("hop_start"))
    hop_limit = _coerce_int(packet.get("hop_limit"))
    if hop_start is None or hop_limit is None:
        return "Unknown"
    hops_taken = hop_start - hop_limit
    if hops_taken == 0:
        return "Direct"
    if hops_taken == 1:
        return "1 Hop"
    return f"{hops_taken} Hops"


def _sender_label(packet: Mapping[str, Any]) -> str:
    short_name = packet.get("from_short_name")
    if isinstance(short_name, str) and short_name.strip():
        return short_name
    long_name = packet.get("from_long_name")
    if isinstance(long_name, str) and long_name.strip():
        return long_name
    from_node_num = _coerce_int(packet.get("from_node_num"))
    if from_node_num is not None:
        return f"Node {from_node_num}"
    return "Unknown"


def _destination_label(packet: Mapping[str, Any]) -> str:
    to_node_num = _coerce_int(packet.get("to_node_num"))
    if to_node_num == BROADCAST_NODE_NUM:
        return "Broadcast"
    short_name = packet.get("to_short_name")
    if isinstance(short_name, str) and short_name.strip():
        return short_name
    long_name = packet.get("to_long_name")
    if isinstance(long_name, str) and long_name.strip():
        return long_name
    if to_node_num is not None:
        return f"Node {to_node_num}"
    return "Unknown"


def _delivery_node_label(packet: Mapping[str, Any]) -> str | None:
    relay_node = _coerce_int(packet.get("relay_node"))
    next_hop = _coerce_int(packet.get("next_hop"))
    delivered_by = relay_node if relay_node is not None else next_hop
    if delivered_by is None:
        return None
    if delivered_by == 0:
        return "Local"
    label = packet.get("delivery_short_name") or packet.get("delivery_long_name")
    if isinstance(label, str) and label.strip():
        return label
    return f"Node {delivered_by}"


def collector_status_payload(status: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "state": status.get("state"),
        "connected": bool(status.get("connected")),
    }


def public_packet_payload(packet: Mapping[str, Any], *, local_node_num: int | None = None) -> dict[str, Any]:
    payload = _pick(packet, PUBLIC_PACKET_FIELDS)
    payload["path_tone"] = _packet_path_tone(packet, local_node_num=local_node_num)
    payload["path_label"] = _packet_path_label(packet, local_node_num=local_node_num)
    payload["delivery_node_label"] = _delivery_node_label(packet)
    return payload


def public_packets_payload(items: list[Mapping[str, Any]], *, local_node_num: int | None = None) -> list[dict[str, Any]]:
    return [public_packet_payload(item, local_node_num=local_node_num) for item in items]


def public_chat_message_payload(packet: Mapping[str, Any], *, local_node_num: int | None = None) -> dict[str, Any]:
    payload = _pick(packet, PUBLIC_CHAT_FIELDS)
    payload["sender_label"] = _sender_label(packet)
    payload["path_tone"] = _packet_path_tone(packet, local_node_num=local_node_num)
    payload["path_label"] = _packet_path_label(packet, local_node_num=local_node_num)
    return payload


def public_chat_messages_payload(items: list[Mapping[str, Any]], *, local_node_num: int | None = None) -> list[dict[str, Any]]:
    return [public_chat_message_payload(item, local_node_num=local_node_num) for item in items]


def public_node_recent_packet_payload(packet: Mapping[str, Any], *, local_node_num: int | None = None) -> dict[str, Any]:
    payload = _pick(packet, PUBLIC_NODE_RECENT_PACKET_FIELDS)
    payload["destination_label"] = _destination_label(packet)
    payload["path_tone"] = _packet_path_tone(packet, local_node_num=local_node_num)
    payload["path_label"] = _packet_path_label(packet, local_node_num=local_node_num)
    payload["delivery_node_label"] = _delivery_node_label(packet)
    return payload


def public_node_recent_packets_payload(
    items: list[Mapping[str, Any]],
    *,
    local_node_num: int | None = None,
) -> list[dict[str, Any]]:
    return [public_node_recent_packet_payload(item, local_node_num=local_node_num) for item in items]


def public_node_payload(node: Mapping[str, Any]) -> dict[str, Any]:
    payload = _pick(node, PUBLIC_NODE_FIELDS)
    payload["latitude"] = _obfuscated_coordinate(payload.get("latitude"))
    payload["longitude"] = _obfuscated_coordinate(payload.get("longitude"))
    return payload


def public_node_detail_node_payload(node: Mapping[str, Any]) -> dict[str, Any]:
    return _pick(node, PUBLIC_NODE_DETAIL_FIELDS)


def public_nodes_payload(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [public_node_payload(item) for item in items]


def public_node_detail_payload(
    node: Mapping[str, Any],
    *,
    insights: Mapping[str, Any],
    recent_packets: list[Mapping[str, Any]],
    metric_history: list[Mapping[str, Any]],
    local_node_num: int | None = None,
    last_traceroute_attempt: Mapping[str, Any] | None = None,
    last_successful_traceroute_attempt: Mapping[str, Any] | None = None,
    latest_complete_traceroute: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    last_attempt_payload = (
        None if last_traceroute_attempt is None else _pick(last_traceroute_attempt, PUBLIC_TRACEROUTE_ATTEMPT_FIELDS)
    )
    last_successful_payload = (
        None
        if last_successful_traceroute_attempt is None
        else _pick(last_successful_traceroute_attempt, PUBLIC_TRACEROUTE_ATTEMPT_FIELDS)
    )
    if last_attempt_payload is not None:
        route = last_traceroute_attempt.get("route")
        last_attempt_payload["route"] = None if route is None else _pick(route, PUBLIC_TRACEROUTE_ROUTE_FIELDS)
    if last_successful_payload is not None:
        route = last_successful_traceroute_attempt.get("route")
        last_successful_payload["route"] = None if route is None else _pick(route, PUBLIC_TRACEROUTE_ROUTE_FIELDS)
    return {
        "node": public_node_detail_node_payload(node),
        "insights": _pick(insights, PUBLIC_NODE_INSIGHTS_FIELDS),
        "recent_packets": public_node_recent_packets_payload(recent_packets, local_node_num=local_node_num),
        "metric_history": [_pick(item, PUBLIC_NODE_METRIC_HISTORY_FIELDS) for item in metric_history],
        "last_traceroute_attempt": last_attempt_payload,
        "last_successful_traceroute_attempt": last_successful_payload,
        "latest_complete_traceroute": (
            None if latest_complete_traceroute is None else _pick(latest_complete_traceroute, PUBLIC_COMPLETE_TRACEROUTE_FIELDS)
        ),
    }


def public_receiver_payload(
    *,
    local_node_num: int | None,
    label: str,
    receiver_node: Mapping[str, Any] | None,
    history: list[Mapping[str, Any]],
    windowed_utilization: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "node_num": local_node_num,
        "label": label,
        "updated_at": None if receiver_node is None else receiver_node.get("updated_at"),
        "channel_utilization": None if receiver_node is None else receiver_node.get("channel_utilization"),
        "air_util_tx": None if receiver_node is None else receiver_node.get("air_util_tx"),
        "history": [
            {
                "recorded_at": item.get("recorded_at"),
                "channel_utilization": item.get("channel_utilization"),
                "air_util_tx": item.get("air_util_tx"),
            }
            for item in history
        ],
        "windowed_utilization": {
            "window_minutes": windowed_utilization.get("window_minutes"),
            "channel_utilization_avg": windowed_utilization.get("channel_utilization_avg"),
            "air_util_tx_avg": windowed_utilization.get("air_util_tx_avg"),
            "sample_count": windowed_utilization.get("sample_count"),
        },
    }


def public_mesh_summary_payload(
    summary: Mapping[str, Any],
    *,
    receiver: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "nodes": dict(summary.get("nodes") or {}),
        "traffic": dict(summary.get("traffic") or {}),
        "windowed_activity": dict(summary.get("windowed_activity") or {}),
        "receiver": dict(receiver),
    }
