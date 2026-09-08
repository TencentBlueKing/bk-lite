import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


class _JsonResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.cookies = {}

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_dell_unity_honors_port_header_and_certificate_verification(monkeypatch):
    from plugins.inputs.dell_unity import dell_unity_info

    client_kwargs = []
    get_calls = []

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            client_kwargs.append(kwargs)

        async def get(self, url, **kwargs):
            get_calls.append((url, kwargs))
            if "loginSessionInfo" in url:
                return _JsonResponse({"entries": []}, headers={"EMC-CSRF-TOKEN": "csrf-1"})
            if "types/system/instances" in url:
                return _JsonResponse(
                    {
                        "entries": [
                            {
                                "content": {
                                    "id": "0",
                                    "name": "FNM1",
                                    "model": "Unity 480",
                                    "serialNumber": "FNM00123456789",
                                    "softwareVersion": "5.3.0.0.5.120",
                                    "health": {"value": 5},
                                }
                            }
                        ]
                    }
                )
            return _JsonResponse({"entries": []})

        async def aclose(self):
            return None

    monkeypatch.setattr(dell_unity_info.httpx, "AsyncClient", FakeAsyncClient)
    manager = dell_unity_info.DellUnityManager(
        {
            "host": "10.0.0.20",
            "port": 8443,
            "username": "collector",
            "password": "secret",
            "verify_tls": False,
        }
    )
    result = await manager.list_all_resources()

    assert manager.base_url == "https://10.0.0.20:8443"
    assert client_kwargs[0]["verify"] is False
    first_headers = get_calls[0][1]["headers"]
    assert first_headers["X-EMC-REST-CLIENT"] == "true"
    assert get_calls[0][1]["auth"] == ("collector", "secret")
    assert result["success"] is True
    storage = result["result"]["storage"][0]
    assert storage["device_sn"] == "FNM00123456789"
    assert storage["ip_addr"] == "10.0.0.20"
    assert storage["brand"] == "dell"
    assert storage["storage_type"] == "SAN"
    assert manager._csrf == "csrf-1"
    later_headers = [call[1]["headers"] for call in get_calls if call[1]["headers"].get("EMC-CSRF-TOKEN")]
    assert later_headers
    assert later_headers[0]["EMC-CSRF-TOKEN"] == "csrf-1"


@pytest.mark.asyncio
async def test_dell_unity_paginates_and_falls_back_system_instance(monkeypatch):
    from plugins.inputs.dell_unity import dell_unity_info

    page_size = dell_unity_info.DellUnityManager.PAGE_SIZE

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def get(self, url, **kwargs):
            params = kwargs.get("params") or {}
            if "loginSessionInfo" in url:
                return _JsonResponse({"entries": []})
            if "types/system/instances" in url:
                return _JsonResponse({"entries": []})
            if "instances/system/0" in url:
                return _JsonResponse({"content": {"id": "0", "serialNumber": "SN1", "model": "UnityVSA"}})
            if "ethernetPort" in url:
                query = parse_qs(urlparse(url).query)
                page = int((params or {}).get("page") or (query.get("page") or ["1"])[0])
                if page == 1:
                    records = [{"content": {"name": f"eth{index}", "macAddress": f"00:60:16:aa:bb:{index:02x}"}} for index in range(page_size)]
                    return _JsonResponse({"entries": records, "links": [{"rel": "next", "href": "?page=2"}]})
                return _JsonResponse({"entries": [{"content": {"name": "ethz", "macAddress": "00:60:16:aa:bb:ff"}}]})
            return _JsonResponse({"entries": []})

        async def aclose(self):
            return None

    monkeypatch.setattr(dell_unity_info.httpx, "AsyncClient", FakeAsyncClient)
    manager = dell_unity_info.DellUnityManager({"host": "10.0.0.20", "username": "u", "password": "p"})
    result = await manager.list_all_resources()
    assert result["success"] is True
    assert result["result"]["storage"][0]["device_sn"] == "SN1"
    assert result["result"]["storage"][0]["model"] == "UnityVSA"
    assert len(result["result"]["storage_eth_port"]) == page_size + 1


@pytest.mark.asyncio
async def test_dell_unity_auth_failure(monkeypatch):
    from plugins.inputs.dell_unity import dell_unity_info

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def get(self, *_args, **_kwargs):
            return _JsonResponse({}, status_code=401)

        async def aclose(self):
            return None

    monkeypatch.setattr(dell_unity_info.httpx, "AsyncClient", FakeAsyncClient)
    manager = dell_unity_info.DellUnityManager({"host": "10.0.0.20", "username": "u", "password": "bad"})
    result = await manager.list_all_resources()
    assert result["success"] is False
    assert "cmdb_collect_error" in result["result"]
    assert "bad" not in str(result["result"]["cmdb_collect_error"])
