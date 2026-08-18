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
    assert result["result"]["storage"][0]["device_sn"] == "device-1"


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
            return _JsonResponse(
                {"data": {"iBaseToken": "token", "deviceid": "device-1"}}
            )

        async def delete(self, *_args, **_kwargs):
            return _JsonResponse({})

        async def get(self, url, **kwargs):
            params = kwargs.get("params") or {}
            range_key = params.get("range", "")
            get_ranges.append((url.rsplit("/", 1)[-1], range_key))
            if url.endswith("/storagepool"):
                return _JsonResponse(
                    {"error": {"code": 0}, "data": pool_pages.get(range_key, [])}
                )
            if url.endswith("/disk"):
                return _JsonResponse(
                    {"error": {"code": 0}, "data": [{"NAME": "disk-1"}]}
                )
            if url.endswith("/lun"):
                return _JsonResponse(
                    {"error": {"code": 0}, "data": [{"NAME": "lun-1"}, {"NAME": "lun-2"}]}
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
