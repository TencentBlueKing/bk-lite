import sys
from pathlib import Path

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


class _JsonResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_netapp_ontap_honors_port_and_certificate_verification(monkeypatch):
    from plugins.inputs.netapp_ontap import netapp_ontap_info

    client_kwargs = []
    get_calls = []

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            client_kwargs.append(kwargs)

        async def get(self, url, **kwargs):
            get_calls.append((url, kwargs))
            if url.endswith("/api/cluster"):
                return _JsonResponse({"name": "cluster1", "uuid": "cluster-uuid", "version": {"full": "9.13.1"}})
            return _JsonResponse({"records": [], "num_records": 0})

        async def aclose(self):
            return None

    monkeypatch.setattr(netapp_ontap_info.httpx, "AsyncClient", FakeAsyncClient)
    manager = netapp_ontap_info.NetAppOntapManager(
        {
            "host": "10.0.0.10",
            "port": 8443,
            "username": "collector",
            "password": "secret",
            "verify_tls": False,
        }
    )
    result = await manager.list_all_resources()

    assert manager.base_url == "https://10.0.0.10:8443"
    assert client_kwargs[0]["verify"] is False
    assert get_calls[0][0].endswith("/api/cluster")
    assert get_calls[0][1]["auth"] == ("collector", "secret")
    assert result["success"] is True
    storage = result["result"]["storage"][0]
    assert storage["device_sn"] == "cluster-uuid"
    assert storage["ip_addr"] == "10.0.0.10"
    assert storage["brand"] == "netapp"
    assert storage["storage_type"] == "unified"
    assert "storage_eth_port" in result["result"]
    assert "storage_fc_port" in result["result"]


@pytest.mark.asyncio
async def test_netapp_ontap_paginates_and_skips_missing_fc(monkeypatch):
    from plugins.inputs.netapp_ontap import netapp_ontap_info

    page_size = netapp_ontap_info.NetAppOntapManager.PAGE_SIZE

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def get(self, url, **kwargs):
            params = kwargs.get("params") or {}
            if url.endswith("/api/cluster"):
                return _JsonResponse({"uuid": "u1", "name": "c1", "version": {"full": "9.13.1"}})
            if "/network/fc/ports" in url:
                return _JsonResponse({"error": {"message": "not found"}}, status_code=404)
            if "/network/ethernet/ports" in url:
                if params.get("max_records") == page_size:
                    records = [{"name": f"e0{index}", "mac_address": f"00:0c:29:aa:bb:{index:02x}"} for index in range(page_size)]
                    return _JsonResponse(
                        {
                            "records": records,
                            "num_records": page_size,
                            "_links": {"next": {"href": "/api/network/ethernet/ports?offset=100"}},
                        }
                    )
                return _JsonResponse({"records": [{"name": "e0z", "mac_address": "00:0c:29:aa:bb:ff"}], "num_records": 1})
            return _JsonResponse({"records": [], "num_records": 0})

        async def aclose(self):
            return None

    monkeypatch.setattr(netapp_ontap_info.httpx, "AsyncClient", FakeAsyncClient)
    manager = netapp_ontap_info.NetAppOntapManager({"host": "10.0.0.10", "username": "u", "password": "p"})
    result = await manager.list_all_resources()
    assert result["success"] is True
    assert len(result["result"]["storage_eth_port"]) == page_size + 1
    assert result["result"]["storage_fc_port"] == []


@pytest.mark.asyncio
async def test_netapp_ontap_auth_failure(monkeypatch):
    from plugins.inputs.netapp_ontap import netapp_ontap_info

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def get(self, *_args, **_kwargs):
            return _JsonResponse({}, status_code=401)

        async def aclose(self):
            return None

    monkeypatch.setattr(netapp_ontap_info.httpx, "AsyncClient", FakeAsyncClient)
    manager = netapp_ontap_info.NetAppOntapManager({"host": "10.0.0.10", "username": "u", "password": "bad"})
    result = await manager.list_all_resources()
    assert result["success"] is False
    assert "cmdb_collect_error" in result["result"]
    assert "bad" not in str(result["result"]["cmdb_collect_error"])
