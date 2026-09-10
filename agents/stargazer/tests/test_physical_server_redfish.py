import traceback

import httpx
import pytest
from plugins.inputs.physcial_server import redfish_info
from plugins.inputs.physcial_server.physcial_server_info import PhyscialServerProtocolInfo
from plugins.inputs.physcial_server.redfish_info import PhyscialServerRedfishInfo

pytestmark = pytest.mark.asyncio


def _response(request, payload, status=200):
    return httpx.Response(status, json=payload, request=request)


async def test_redfish_protocol_collects_one_physical_server_by_target_ip():
    def handler(request):
        assert request.headers["Authorization"].startswith("Basic ")
        if request.url.path == "/redfish/v1/":
            return _response(
                request,
                {
                    "RedfishVersion": "1.6.0",
                    "Systems": {"@odata.id": "/redfish/v1/Systems"},
                },
            )
        if request.url.path == "/redfish/v1/Systems":
            return _response(
                request,
                {
                    "Members": [
                        {"@odata.id": "/redfish/v1/Systems/1"},
                    ]
                },
            )
        if request.url.path == "/redfish/v1/Systems/1":
            return _response(
                request,
                {
                    "Manufacturer": "Huawei",
                    "Model": "2288H V5",
                    "SerialNumber": "SERVER-SN-8",
                    "AssetTag": "ASSET-8",
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    collector = PhyscialServerProtocolInfo(
        {
            "collection_protocol": "redfish",
            "host": "10.0.0.8",
            "port": 443,
            "username": "Administrator",
            "password": "secret",
            "model_id": "physcial_server",
        },
        transport=httpx.MockTransport(handler),
    )

    result = await collector.list_all_resources()

    assert result == {
        "success": True,
        "result": {
            "physcial_server": [
                {
                    "ip_addr": "10.0.0.8",
                    "port": 443,
                    "serial_number": "SERVER-SN-8",
                    "model": "2288H V5",
                    "brand": "Huawei",
                    "asset_code": "ASSET-8",
                }
            ]
        },
    }


async def test_redfish_protocol_rejects_multiple_systems_for_one_ip():
    def handler(request):
        if request.url.path == "/redfish/v1/":
            return _response(
                request,
                {"Systems": {"@odata.id": "/redfish/v1/Systems"}},
            )
        return _response(
            request,
            {
                "Members": [
                    {"@odata.id": "/redfish/v1/Systems/1"},
                    {"@odata.id": "/redfish/v1/Systems/2"},
                ]
            },
        )

    collector = PhyscialServerProtocolInfo(
        {
            "collection_protocol": "redfish",
            "host": "10.0.0.8",
            "port": 443,
            "username": "Administrator",
            "password": "secret",
            "model_id": "physcial_server",
        },
        transport=httpx.MockTransport(handler),
    )

    result = await collector.list_all_resources()

    assert result["success"] is False
    assert result["result"]["cmdb_collect_error"] == "Redfish target must expose exactly one ComputerSystem"


async def test_redfish_protocol_does_not_follow_cross_origin_resource_links():
    def handler(request):
        return _response(
            request,
            {
                "Systems": {
                    "@odata.id": "https://attacker.invalid/redfish/v1/Systems",
                }
            },
        )

    collector = PhyscialServerProtocolInfo(
        {
            "collection_protocol": "redfish",
            "host": "10.0.0.8",
            "port": 443,
            "username": "Administrator",
            "password": "secret",
            "model_id": "physcial_server",
        },
        transport=httpx.MockTransport(handler),
    )

    result = await collector.list_all_resources()

    assert result["success"] is False
    assert result["result"]["cmdb_collect_error"] == "Redfish resource link must stay on the target service"


async def test_redfish_protocol_accepts_same_origin_absolute_resource_links():
    def handler(request):
        if request.url.path == "/redfish/v1/":
            return _response(
                request,
                {"Systems": {"@odata.id": "https://10.0.0.8/redfish/v1/Systems"}},
            )
        if request.url.path == "/redfish/v1/Systems":
            return _response(
                request,
                {"Members": [{"@odata.id": "https://10.0.0.8/redfish/v1/Systems/1"}]},
            )
        return _response(request, {"Manufacturer": "Huawei"})

    collector = PhyscialServerProtocolInfo(
        {
            "collection_protocol": "redfish",
            "host": "10.0.0.8",
            "port": 443,
            "username": "Administrator",
            "password": "secret",
        },
        transport=httpx.MockTransport(handler),
    )

    result = await collector.list_all_resources()

    assert result["success"] is True


async def test_redfish_protocol_counts_members_across_paginated_system_collection():
    requested_urls = []

    def handler(request):
        requested_urls.append(str(request.url))
        if request.url.path == "/redfish/v1/":
            return _response(request, {"Systems": {"@odata.id": "/redfish/v1/Systems"}})
        if request.url.query == b"page=2":
            return _response(request, {"Members": [{"@odata.id": "/redfish/v1/Systems/2"}]})
        return _response(
            request,
            {
                "Members": [{"@odata.id": "/redfish/v1/Systems/1"}],
                "Members@odata.nextLink": "/redfish/v1/Systems?page=2",
            },
        )

    collector = PhyscialServerProtocolInfo(
        {
            "collection_protocol": "redfish",
            "host": "10.0.0.8",
            "username": "Administrator",
            "password": "secret",
        },
        transport=httpx.MockTransport(handler),
    )

    result = await collector.list_all_resources()

    assert result["success"] is False
    assert result["result"]["cmdb_collect_error"] == "Redfish target must expose exactly one ComputerSystem"
    assert any(url.endswith("/redfish/v1/Systems?page=2") for url in requested_urls)


async def test_redfish_protocol_honors_explicitly_disabled_tls_verification(monkeypatch):
    captured = {}
    real_async_client = httpx.AsyncClient

    def handler(request):
        if request.url.path == "/redfish/v1/":
            return _response(
                request,
                {"Systems": {"@odata.id": "/redfish/v1/Systems"}},
            )
        if request.url.path == "/redfish/v1/Systems":
            return _response(
                request,
                {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]},
            )
        return _response(request, {"Manufacturer": "Huawei"})

    def client_factory(**kwargs):
        captured["verify"] = kwargs["verify"]
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(**kwargs)

    monkeypatch.setattr(redfish_info.httpx, "AsyncClient", client_factory)
    collector = PhyscialServerProtocolInfo(
        {
            "collection_protocol": "redfish",
            "host": "10.0.0.8",
            "port": 443,
            "username": "Administrator",
            "password": "secret",
            # 服务端自定义请求头在传输后为字符串，采集器必须正确还原布尔语义。
            "verify_tls": "False",
        }
    )

    result = await collector.list_all_resources()

    assert result["success"] is True
    assert captured["verify"] is False


async def test_redfish_protocol_uses_canonical_service_root_without_redirects():
    requested_paths = []

    def handler(request):
        requested_paths.append(request.url.path)
        if request.url.path == "/redfish/v1":
            return httpx.Response(
                308,
                headers={"Location": "/redfish/v1/"},
                request=request,
            )
        if request.url.path == "/redfish/v1/":
            return _response(
                request,
                {"Systems": {"@odata.id": "/redfish/v1/Systems"}},
            )
        if request.url.path == "/redfish/v1/Systems":
            return _response(
                request,
                {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]},
            )
        return _response(request, {"Manufacturer": "Huawei"})

    collector = PhyscialServerProtocolInfo(
        {
            "collection_protocol": "redfish",
            "host": "10.0.0.8",
            "username": "Administrator",
            "password": "secret",
        },
        transport=httpx.MockTransport(handler),
    )

    result = await collector.list_all_resources()

    assert result["success"] is True
    assert requested_paths[0] == "/redfish/v1/"
    assert "/redfish/v1" not in requested_paths


async def test_redfish_protocol_reports_tls_validation_failure_during_collection(monkeypatch):
    secret_sentinel = "BMC_SECRET_MUST_NOT_LEAK"
    log_calls = []

    def handler(request):
        raise httpx.ConnectError(
            f"certificate verify failed {secret_sentinel}",
            request=request,
        )

    def capture_error(template, *args, **kwargs):
        log_calls.append((template, args, kwargs))

    monkeypatch.setattr(redfish_info.logger, "error", capture_error)

    collector = PhyscialServerProtocolInfo(
        {
            "collection_protocol": "redfish",
            "host": "10.0.0.8",
            "username": "Administrator",
            "password": secret_sentinel,
        },
        transport=httpx.MockTransport(handler),
    )

    result = await collector.list_all_resources()

    assert result == {
        "result": {"cmdb_collect_error": "Redfish TLS validation failed"},
        "success": False,
    }
    assert len(log_calls) == 1
    template, args, kwargs = log_calls[0]
    assert template.startswith("event=physical_server_redfish_collect_failed")
    assert secret_sentinel not in template % args
    assert kwargs["exc_info"][2] is not None
    formatted_traceback = "".join(traceback.format_exception(*kwargs["exc_info"]))
    assert "test_physical_server_redfish.py" in formatted_traceback
    assert "in handler" in formatted_traceback
    assert secret_sentinel not in formatted_traceback


async def test_redfish_protocol_rejects_oversized_response():
    oversized_value = "x" * (PhyscialServerRedfishInfo.MAX_RESPONSE_BYTES + 1)

    def handler(request):
        return _response(request, {"oversized": oversized_value})

    collector = PhyscialServerProtocolInfo(
        {
            "collection_protocol": "redfish",
            "host": "10.0.0.8",
            "username": "Administrator",
            "password": "secret",
        },
        transport=httpx.MockTransport(handler),
    )

    result = await collector.list_all_resources()

    assert result == {
        "result": {"cmdb_collect_error": "Redfish response exceeds size limit"},
        "success": False,
    }
