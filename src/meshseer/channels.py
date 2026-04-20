from __future__ import annotations


LONGFAST_CHANNEL_NAME = "LongFast"
BROADCAST_NODE_NUM = 0xFFFFFFFF


def is_primary_channel(channel_index: int | None) -> bool:
    return channel_index in (None, 0)
