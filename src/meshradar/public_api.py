from __future__ import annotations

from typing import Any, Mapping


PUBLIC_PACKET_FIELDS = (
    "id",
    "mesh_packet_id",
    "received_at",
    "from_node_num",
    "to_node_num",
    "portnum",
    "channel_index",
    "hop_limit",
    "hop_start",
    "rx_snr",
    "relay_node",
    "next_hop",
    "text_preview",
    "via_mqtt",
    "from_short_name",
    "from_long_name",
    "from_node_id",
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

PUBLIC_NODE_INSIGHTS_FIELDS = (
    "heard_packets",
    "broadcast_packets",
    "mqtt_packets",
    "direct_packets",
    "relayed_packets",
    "avg_rx_snr",
    "best_rx_snr",
    "worst_rx_snr",
    "last_path",
    "last_hops_taken",
    "last_portnum",
    "last_seen_at",
)


def _pick(mapping: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: mapping.get(field) for field in fields}


def collector_status_payload(status: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "state": status.get("state"),
        "connected": bool(status.get("connected")),
    }


def public_packet_payload(packet: Mapping[str, Any]) -> dict[str, Any]:
    return _pick(packet, PUBLIC_PACKET_FIELDS)


def public_packets_payload(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [public_packet_payload(item) for item in items]


def public_node_payload(node: Mapping[str, Any]) -> dict[str, Any]:
    return _pick(node, PUBLIC_NODE_FIELDS)


def public_nodes_payload(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [public_node_payload(item) for item in items]


def public_node_detail_payload(
    node: Mapping[str, Any],
    *,
    recent_packets: list[Mapping[str, Any]],
    insights: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "node": public_node_payload(node),
        "recent_packets": public_packets_payload(recent_packets),
        "insights": _pick(insights, PUBLIC_NODE_INSIGHTS_FIELDS),
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
