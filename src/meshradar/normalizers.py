from __future__ import annotations

import base64
import json
from typing import Any, Mapping

from meshradar.clock import timestamp_to_utc_iso, utc_now_iso


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "items"):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if hasattr(value, "__dict__") and value.__dict__:
        return {str(key): _sanitize(item) for key, item in vars(value).items()}
    return str(value)


def _payload_base64(decoded: Mapping[str, Any]) -> str | None:
    payload = decoded.get("payload")
    if isinstance(payload, bytes):
        return base64.b64encode(payload).decode("ascii")
    if isinstance(payload, str):
        return payload
    return None


def _text_preview(decoded: Mapping[str, Any]) -> str | None:
    text = decoded.get("text")
    if isinstance(text, str):
        return text
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    return str(value)


def normalize_packet(packet: Mapping[str, Any], *, now_provider=utc_now_iso) -> dict[str, Any]:
    decoded = packet.get("decoded", {})
    fallback_now = now_provider()
    return {
        "mesh_packet_id": packet.get("id"),
        "received_at": timestamp_to_utc_iso(packet.get("rxTime"), fallback=fallback_now),
        "from_node_num": packet.get("from"),
        "to_node_num": packet.get("to"),
        "portnum": str(decoded.get("portnum", "UNKNOWN")),
        "channel_index": packet.get("channel"),
        "hop_limit": packet.get("hopLimit"),
        "rx_snr": packet.get("rxSnr"),
        "text_preview": _text_preview(decoded),
        "payload_base64": _payload_base64(decoded),
        "raw_json": json.dumps(_sanitize(dict(packet)), sort_keys=True),
        "hop_start": _optional_int(packet.get("hopStart")),
        "rx_rssi": _optional_int(packet.get("rxRssi")),
        "next_hop": _optional_int(packet.get("nextHop")),
        "relay_node": _optional_int(packet.get("relayNode")),
        "via_mqtt": _optional_bool(packet.get("viaMqtt")),
        "transport_mechanism": _string_or_none(packet.get("transportMechanism")),
    }


def normalize_node(node: Mapping[str, Any], *, now_provider=utc_now_iso) -> dict[str, Any]:
    user = node.get("user", {})
    position = node.get("position", {})
    device_metrics = node.get("deviceMetrics", {})
    return {
        "node_num": node["num"],
        "node_id": user.get("id"),
        "short_name": user.get("shortName"),
        "long_name": user.get("longName"),
        "hardware_model": user.get("hwModel"),
        "role": user.get("role"),
        "channel_index": node.get("channel"),
        "last_heard_at": timestamp_to_utc_iso(node.get("lastHeard")) if node.get("lastHeard") else None,
        "last_snr": node.get("snr"),
        "latitude": position.get("latitude"),
        "longitude": position.get("longitude"),
        "altitude": position.get("altitude"),
        "battery_level": device_metrics.get("batteryLevel"),
        "channel_utilization": device_metrics.get("channelUtilization"),
        "air_util_tx": device_metrics.get("airUtilTx"),
        "raw_json": json.dumps(_sanitize(dict(node)), sort_keys=True),
        "updated_at": now_provider(),
        "hops_away": _optional_int(node.get("hopsAway")),
        "via_mqtt": _optional_bool(node.get("viaMqtt")),
    }
