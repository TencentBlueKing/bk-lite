"""Stargazer 低流量 control/callback NATS 协议边界。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from core.infra.nats_utils import nats_publish

_COLLECTION_CALLBACKS = frozenset({"receive_config_file_result"})


class UnsupportedControlSubject(ValueError):
    pass


class NatsControlTransport:
    """只暴露已登记的 control 协议，不接受任意 subject 批量发布。"""

    def __init__(self, *, namespace: str | None = None, publish=None) -> None:
        self._namespace = str(namespace or os.getenv("NATS_NAMESPACE", "bklite"))
        self._publish = publish or nats_publish

    async def publish_collection_callback(
        self,
        callback_name: str,
        data: Mapping[str, Any],
    ) -> None:
        normalized = str(callback_name or "").strip()
        if normalized not in _COLLECTION_CALLBACKS:
            raise UnsupportedControlSubject(f"unsupported collection callback: {normalized or '-'}")
        await self._publish(
            f"{self._namespace}.{normalized}",
            {"args": [], "kwargs": {"data": dict(data)}},
        )


_transport: NatsControlTransport | None = None


def get_control_transport() -> NatsControlTransport:
    global _transport
    if _transport is None:
        _transport = NatsControlTransport()
    return _transport
