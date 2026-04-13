from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class PacketRecord:
    mesh_packet_id: int | None
    received_at: str
    from_node_num: int | None
    to_node_num: int | None
    portnum: str
    channel_index: int | None
    hop_limit: int | None
    rx_snr: float | None
    text_preview: str | None
    payload_base64: str | None
    raw_json: str
    hop_start: int | None = None
    rx_rssi: int | None = None
    next_hop: int | None = None
    relay_node: int | None = None
    via_mqtt: bool | None = None
    transport_mechanism: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PacketRecord":
        return cls(
            mesh_packet_id=data.get("mesh_packet_id"),
            received_at=data["received_at"],
            from_node_num=data.get("from_node_num"),
            to_node_num=data.get("to_node_num"),
            portnum=data["portnum"],
            channel_index=data.get("channel_index"),
            hop_limit=data.get("hop_limit"),
            rx_snr=data.get("rx_snr"),
            text_preview=data.get("text_preview"),
            payload_base64=data.get("payload_base64"),
            raw_json=data["raw_json"],
            hop_start=data.get("hop_start"),
            rx_rssi=data.get("rx_rssi"),
            next_hop=data.get("next_hop"),
            relay_node=data.get("relay_node"),
            via_mqtt=data.get("via_mqtt"),
            transport_mechanism=data.get("transport_mechanism"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NodeRecord:
    node_num: int
    node_id: str | None
    short_name: str | None
    long_name: str | None
    hardware_model: str | None
    role: str | None
    channel_index: int | None
    last_heard_at: str | None
    last_snr: float | None
    latitude: float | None
    longitude: float | None
    altitude: float | None
    battery_level: float | None
    channel_utilization: float | None
    air_util_tx: float | None
    raw_json: str
    updated_at: str
    hops_away: int | None = None
    via_mqtt: bool | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "NodeRecord":
        return cls(
            node_num=data["node_num"],
            node_id=data.get("node_id"),
            short_name=data.get("short_name"),
            long_name=data.get("long_name"),
            hardware_model=data.get("hardware_model"),
            role=data.get("role"),
            channel_index=data.get("channel_index"),
            last_heard_at=data.get("last_heard_at"),
            last_snr=data.get("last_snr"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            altitude=data.get("altitude"),
            battery_level=data.get("battery_level"),
            channel_utilization=data.get("channel_utilization"),
            air_util_tx=data.get("air_util_tx"),
            raw_json=data["raw_json"],
            updated_at=data["updated_at"],
            hops_away=data.get("hops_away"),
            via_mqtt=data.get("via_mqtt"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
