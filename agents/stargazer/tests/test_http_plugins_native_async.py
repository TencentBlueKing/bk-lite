# -*- coding: utf-8 -*-
"""HTTP 配置采集插件原生异步心跳：mock 的 HTTP await 使用 asyncio.sleep，
证明 probe / list_all_resources 不会阻塞事件循环。
"""
import asyncio
import sys
from pathlib import Path

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


async def _heartbeat_during(awaitable, minimum_ticks: int = 5):
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        result = await awaitable
    finally:
        heartbeat_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await heartbeat_task

    assert ticks >= minimum_ticks, "event_loop_stalled"
    return result


class _JsonResponse:
    def __init__(self, payload=None, status_code=200, headers=None, content=b"{}"):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload if payload is not None else {}
        if payload is not None:
            import json

            self.content = json.dumps(payload).encode()
        else:
            self.content = content

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_influxdb_probe_does_not_stall_event_loop(monkeypatch):
    from plugins.inputs.influxdb import influxdb_info

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **_kwargs):
            await asyncio.sleep(0.05)
            if url.endswith("/health"):
                return _JsonResponse({"status": "pass", "version": "2.7.5"})
            return _JsonResponse({}, status_code=200)

    monkeypatch.setattr(influxdb_info.httpx, "AsyncClient", FakeAsyncClient)

    from core.collection.contracts import AccessProbeStatus

    result = await _heartbeat_during(influxdb_info.InfluxdbInfo({"host": "influx.local", "timeout": 5}).probe())
    assert result.status == AccessProbeStatus.READY


@pytest.mark.asyncio
async def test_influxdb_collect_does_not_stall_event_loop(monkeypatch):
    from plugins.inputs.influxdb import influxdb_info

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **_kwargs):
            await asyncio.sleep(0.05)
            return _JsonResponse({"status": "pass", "version": "2.7.5"})

    monkeypatch.setattr(influxdb_info.httpx, "AsyncClient", FakeAsyncClient)

    result = await _heartbeat_during(influxdb_info.InfluxdbInfo({"host": "influx.local"}).list_all_resources())
    assert result["success"] is True


@pytest.mark.asyncio
async def test_oceanstor_collect_does_not_stall_event_loop(monkeypatch):
    from plugins.inputs.oceanstor import oceanstor_info

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def post(self, *_args, **_kwargs):
            await asyncio.sleep(0.05)
            return _JsonResponse({"data": {"iBaseToken": "t", "deviceid": "d1"}})

        async def get(self, *_args, **_kwargs):
            await asyncio.sleep(0.05)
            return _JsonResponse({"error": {"code": 0}, "data": []})

        async def delete(self, *_args, **_kwargs):
            await asyncio.sleep(0.05)
            return _JsonResponse({})

        async def aclose(self):
            return None

    monkeypatch.setattr(oceanstor_info.httpx, "AsyncClient", FakeAsyncClient)

    result = await _heartbeat_during(oceanstor_info.OceanStorManager({"host": "10.0.0.1", "username": "u", "password": "p"}).list_all_resources())
    assert result["success"] is True


@pytest.mark.asyncio
async def test_dell_unity_collect_does_not_stall_event_loop(monkeypatch):
    from plugins.inputs.dell_unity import dell_unity_info

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def get(self, url, **_kwargs):
            await asyncio.sleep(0.05)
            if "system" in url:
                return _JsonResponse({"entries": [{"content": {"id": "0", "serialNumber": "FNM1", "model": "Unity 480"}}]})
            return _JsonResponse({"entries": []})

        async def aclose(self):
            return None

    monkeypatch.setattr(dell_unity_info.httpx, "AsyncClient", FakeAsyncClient)

    result = await _heartbeat_during(dell_unity_info.DellUnityManager({"host": "10.0.0.20", "username": "u", "password": "p"}).list_all_resources())
    assert result["success"] is True


@pytest.mark.asyncio
async def test_netapp_ontap_collect_does_not_stall_event_loop(monkeypatch):
    from plugins.inputs.netapp_ontap import netapp_ontap_info

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def get(self, *_args, **_kwargs):
            await asyncio.sleep(0.05)
            return _JsonResponse({"name": "c1", "uuid": "u1", "records": [], "num_records": 0})

        async def aclose(self):
            return None

    monkeypatch.setattr(netapp_ontap_info.httpx, "AsyncClient", FakeAsyncClient)

    result = await _heartbeat_during(
        netapp_ontap_info.NetAppOntapManager({"host": "10.0.0.10", "username": "u", "password": "p"}).list_all_resources()
    )
    assert result["success"] is True


@pytest.mark.asyncio
async def test_fusioninsight_collect_does_not_stall_event_loop(monkeypatch):
    from plugins.inputs.fusioninsight import fusioninsight_info

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def request(self, method, url, **_kwargs):
            await asyncio.sleep(0.05)
            if "session" in url:
                return _JsonResponse({})
            if "clusters" in url:
                return _JsonResponse([{"id": 1, "name": "c1"}])
            if "hosts" in url:
                return _JsonResponse({"hosts": []})
            return _JsonResponse({})

        async def aclose(self):
            return None

    monkeypatch.setattr(fusioninsight_info.httpx, "AsyncClient", FakeAsyncClient)

    result = await _heartbeat_during(
        fusioninsight_info.FusionInsightManager(
            {
                "username": "u",
                "password": "p",
                "host": "fi.example.com",
            }
        ).list_all_resources()
    )
    assert result["success"] is True
