"""Stargazer 低流量 control/callback NATS 协议边界。"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from core.infra.nats_utils import nats_publish, nats_request

_COLLECTION_CALLBACKS = frozenset(
    {
        "receive_config_file_result",
        "receive_scan_credential_result",
        "receive_access_check_result",
    }
)


class UnsupportedControlSubject(ValueError):
    pass


async def _request_collection_callback(subject: str, envelope: Mapping[str, Any], timeout: float) -> dict:
    return await nats_request(subject, json.dumps(envelope).encode(), timeout=timeout)


class NatsControlTransport:
    """只暴露已登记的 control 协议，不接受任意 subject 批量发布。"""

    def __init__(self, *, namespace: str | None = None, publish=None, request=None) -> None:
        self._namespace = str(namespace or os.getenv("NATS_NAMESPACE", "bklite"))
        self._publish = publish or nats_publish
        self._request = request or _request_collection_callback

    async def publish_collection_callback(
        self,
        callback_name: str,
        data: Mapping[str, Any],
    ) -> None:
        normalized = self._callback_name(callback_name)
        await self._publish(
            f"{self._namespace}.{normalized}",
            {"args": [], "kwargs": {"data": dict(data)}},
        )

    async def request_collection_callback(
        self,
        callback_name: str,
        data: Mapping[str, Any],
        timeout: float = 10,
    ) -> dict:
        normalized = self._callback_name(callback_name)
        envelope = {"args": [], "kwargs": {"data": dict(data)}}
        return await self._request(f"{self._namespace}.{normalized}", envelope, timeout)

    @staticmethod
    def _callback_name(callback_name: str) -> str:
        normalized = str(callback_name or "").strip()
        if normalized not in _COLLECTION_CALLBACKS:
            raise UnsupportedControlSubject(f"unsupported collection callback: {normalized or '-'}")
        return normalized


_transport: NatsControlTransport | None = None


def get_control_transport() -> NatsControlTransport:
    global _transport
    if _transport is None:
        _transport = NatsControlTransport()
    return _transport
