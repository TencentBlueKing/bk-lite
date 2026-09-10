import sys
from pathlib import Path

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


class _JsonResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_oceanstor_login_honors_port_and_certificate_verification(monkeypatch):
    from plugins.inputs.oceanstor import oceanstor_info

    client_kwargs = []
    post_calls = []

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            client_kwargs.append(kwargs)

        async def post(self, url, **kwargs):
            post_calls.append((url, kwargs))
            return _JsonResponse(
                {
                    "data": {
                        "iBaseToken": "token",
                        "deviceid": "device-1",
                    }
                }
            )

        async def delete(self, *_args, **_kwargs):
            return _JsonResponse({})

        async def get(self, *_args, **_kwargs):
            return _JsonResponse({"error": {"code": 0}, "data": []})

        async def aclose(self):
            return None

    monkeypatch.setattr(oceanstor_info.httpx, "AsyncClient", FakeAsyncClient)
    manager = oceanstor_info.OceanStorManager(
        {
            "host": "10.0.0.88",
            "port": 8443,
            "username": "collector",
            "password": "secret",
            "verify_tls": False,
        }
    )

    result = await manager.list_all_resources()

    assert manager.base_url == "https://10.0.0.88:8443"
    assert client_kwargs[0]["verify"] is False
    assert post_calls[0][0].endswith("/deviceManager/rest/xxxxx/sessions")
    assert result["success"] is True
    storage = result["result"]["storage"][0]
    assert storage["device_sn"] == "device-1"
    assert storage["ip_addr"] == "10.0.0.88"
    assert "storage_eth_port" in result["result"]
    assert "storage_fc_port" in result["result"]


@pytest.mark.asyncio
async def test_list_all_resources_paginates_storage_objects(monkeypatch):
    from plugins.inputs.oceanstor import oceanstor_info

    page_size = oceanstor_info.OceanStorManager.PAGE_SIZE
    pool_pages = {
        f"[0-{page_size - 1}]": [
            {
                "NAME": f"pool-{i}",
                "USERTOTALCAPACITY": str(2 * 1024**3 // 512),
                "USERCONSUMEDCAPACITY": str(1024**3 // 512),
                "USERFREECAPACITY": str(1024**3 // 512),
                "SECTORSIZE": "512",
            }
            for i in range(page_size)
        ],
        f"[{page_size}-{2 * page_size - 1}]": [
            {
                "NAME": "pool-extra",
                "USERTOTALCAPACITY": str(1024**3 // 512),
                "USERCONSUMEDCAPACITY": "0",
                "USERFREECAPACITY": str(1024**3 // 512),
                "SECTORSIZE": "512",
            }
        ],
    }
    get_ranges = []

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def post(self, *_args, **_kwargs):
            return _JsonResponse({"data": {"iBaseToken": "token", "deviceid": "device-1"}})

        async def delete(self, *_args, **_kwargs):
            return _JsonResponse({})

        async def get(self, url, **kwargs):
            params = kwargs.get("params") or {}
            range_key = params.get("range", "")
            get_ranges.append((url.rsplit("/", 1)[-1], range_key))
            if url.endswith("/storagepool"):
                return _JsonResponse({"error": {"code": 0}, "data": pool_pages.get(range_key, [])})
            if url.endswith("/disk"):
                return _JsonResponse({"error": {"code": 0}, "data": [{"NAME": "disk-1"}]})
            if url.endswith("/lun"):
                return _JsonResponse({"error": {"code": 0}, "data": [{"NAME": "lun-1"}, {"NAME": "lun-2"}]})
            return _JsonResponse({"error": {"code": 0}, "data": []})

        async def aclose(self):
            return None

    monkeypatch.setattr(oceanstor_info.httpx, "AsyncClient", FakeAsyncClient)
    manager = oceanstor_info.OceanStorManager(
        {
            "host": "10.0.0.88",
            "username": "collector",
            "password": "secret",
            "verify_tls": True,
        }
    )

    result = await manager.list_all_resources()

    assert result["success"] is True
    storage = result["result"]["storage"][0]
    assert storage["pool_count"] == str(page_size + 1)
    assert storage["disk_count"] == "1"
    assert storage["volume_count"] == "2"
    assert storage["total_capacity"] == str(page_size * 2 + 1)
    assert len(result["result"]["storage_pool"]) == page_size + 1
    assert ("storagepool", f"[0-{page_size - 1}]") in get_ranges
    assert ("storagepool", f"[{page_size}-{2 * page_size - 1}]") in get_ranges
    fetched_paths = {path for path, _range in get_ranges}
    assert {"storagepool", "disk", "lun", "eth_port", "fc_port"} <= fetched_paths


@pytest.mark.asyncio
async def test_list_all_resources_collects_ports_and_system_in_same_session(monkeypatch):
    from plugins.inputs.oceanstor import oceanstor_info

    get_urls = []
    post_count = {"n": 0}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def post(self, *_args, **_kwargs):
            post_count["n"] += 1
            return _JsonResponse({"data": {"iBaseToken": "token", "deviceid": "device-1"}})

        async def delete(self, *_args, **_kwargs):
            return _JsonResponse({})

        async def get(self, url, **_kwargs):
            get_urls.append(url.rsplit("/", 1)[-1])
            if url.endswith("/system"):
                return _JsonResponse(
                    {
                        "error": {"code": 0},
                        "data": {
                            "PRODUCTMODESTRING": "Dorado 5000 V6",
                            "PRODUCTVERSION": "V600R003C00",
                            "pointRelease": "6.1.8",
                        },
                    }
                )
            if url.endswith("/eth_port"):
                return _JsonResponse(
                    {
                        "error": {"code": 0},
                        "data": [
                            {
                                "NAME": "ETH0",
                                "LOCATION": "CTE0.A.IOM0.P0",
                                "MACADDR": "AA-BB-CC-DD-EE-01",
                                "IPV4ADDR": "10.0.1.8",
                            },
                            {"NAME": "ETH1", "MACADDR": ""},
                        ],
                    }
                )
            if url.endswith("/fc_port"):
                return _JsonResponse(
                    {
                        "error": {"code": 0},
                        "data": [
                            {"NAME": "FC0", "WWPN": "21000024FF5A1234", "RUNSPEED": "16"},
                            {"NAME": "FC1", "WWPN": "--"},
                        ],
                    }
                )
            return _JsonResponse({"error": {"code": 0}, "data": []})

        async def aclose(self):
            return None

    monkeypatch.setattr(oceanstor_info.httpx, "AsyncClient", FakeAsyncClient)
    manager = oceanstor_info.OceanStorManager(
        {
            "host": "10.0.0.88",
            "username": "collector",
            "password": "secret",
        }
    )

    result = await manager.list_all_resources()

    assert result["success"] is True
    assert post_count["n"] == 1
    assert get_urls.count("system") == 1
    assert get_urls.count("eth_port") == 1
    assert get_urls.count("fc_port") == 1
    storage = result["result"]["storage"][0]
    assert storage["ip_addr"] == "10.0.0.88"
    assert storage["model"] == "Dorado 5000 V6"
    assert storage["firmware_version"] == "V600R003C00"
    assert len(result["result"]["storage_eth_port"]) == 2
    assert result["result"]["storage_eth_port"][0]["MACADDR"] == "AA-BB-CC-DD-EE-01"
    assert result["result"]["storage_eth_port"][0]["IPV4ADDR"] == "10.0.1.8"
    assert len(result["result"]["storage_fc_port"]) == 2
    assert result["result"]["storage_fc_port"][0]["WWPN"] == "21000024FF5A1234"


@pytest.mark.asyncio
async def test_list_all_resources_continues_when_port_or_system_endpoints_fail(monkeypatch):
    from plugins.inputs.oceanstor import oceanstor_info

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def post(self, *_args, **_kwargs):
            return _JsonResponse({"data": {"iBaseToken": "token", "deviceid": "device-1"}})

        async def delete(self, *_args, **_kwargs):
            return _JsonResponse({})

        async def get(self, url, **_kwargs):
            if url.endswith("/system") or url.endswith("/eth_port") or url.endswith("/fc_port"):
                return _JsonResponse({"error": {"code": 10700001, "description": "not support"}})
            if url.endswith("/storagepool"):
                return _JsonResponse({"error": {"code": 0}, "data": [{"NAME": "pool-1"}]})
            return _JsonResponse({"error": {"code": 0}, "data": []})

        async def aclose(self):
            return None

    monkeypatch.setattr(oceanstor_info.httpx, "AsyncClient", FakeAsyncClient)
    manager = oceanstor_info.OceanStorManager({"host": "10.0.0.88", "username": "collector", "password": "secret"})

    result = await manager.list_all_resources()

    assert result["success"] is True
    assert result["result"]["storage_pool"] == [{"NAME": "pool-1"}]
    assert result["result"]["storage_eth_port"] == []
    assert result["result"]["storage_fc_port"] == []
    assert result["result"]["storage"][0]["model"] == ""
    assert result["result"]["storage"][0]["firmware_version"] == ""
