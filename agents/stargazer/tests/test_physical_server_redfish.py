import asyncio
import json
import ssl
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
    ctx = captured["verify"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False
    assert "AES256-GCM-SHA384" in {item["name"] for item in ctx.get_ciphers()}


async def test_redfish_tls_context_keeps_verify_flag_and_offers_rsa_gcm():
    from plugins.inputs.physcial_server.redfish_info import _tls_verify

    ctx = _tls_verify(True)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert "AES256-GCM-SHA384" in {item["name"] for item in ctx.get_ciphers()}

    ctx = _tls_verify(False)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False
    assert "AES256-GCM-SHA384" in {item["name"] for item in ctx.get_ciphers()}


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


async def test_redfish_protocol_collects_standard_child_inventory():
    requested = []

    def handler(request):
        requested.append(request.url.path)
        payloads = {
            "/redfish/v1/": {"Systems": {"@odata.id": "/redfish/v1/Systems"}},
            "/redfish/v1/Systems": {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]},
            "/redfish/v1/Systems/1": {
                "Manufacturer": "Huawei",
                "Model": "2288H V5",
                "SerialNumber": "SERVER-SN-8",
                "Processors": {"@odata.id": "/redfish/v1/Systems/1/Processors"},
                "Memory": {"@odata.id": "/redfish/v1/Systems/1/Memory"},
                "Storage": {"@odata.id": "/redfish/v1/Systems/1/Storage"},
                "Links": {"Chassis": [{"@odata.id": "/redfish/v1/Chassis/1"}]},
            },
            "/redfish/v1/Systems/1/Processors": {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Processors/1"}]},
            "/redfish/v1/Systems/1/Processors/1": {
                "Manufacturer": "Intel",
                "Model": "Xeon",
                "TotalCores": 8,
                "TotalThreads": 16,
                "InstructionSet": "x86-64",
            },
            "/redfish/v1/Systems/1/Memory": {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Memory/1"}]},
            "/redfish/v1/Systems/1/Memory/1": {
                "DeviceLocator": "DIMM_A1",
                "CapacityMiB": 32768,
                "SerialNumber": "MEM-1",
            },
            "/redfish/v1/Systems/1/Storage": {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Storage/1"}]},
            "/redfish/v1/Systems/1/Storage/1": {"Drives": {"@odata.id": "/redfish/v1/Systems/1/Storage/1/Drives"}},
            "/redfish/v1/Systems/1/Storage/1/Drives": {
                "Members": [
                    {"@odata.id": "/redfish/v1/Chassis/1/Drives/1"},
                    {"@odata.id": "/redfish/v1/Chassis/1/Drives/1"},
                ]
            },
            "/redfish/v1/Chassis/1/Drives/1": {
                "Id": "Disk.Bay.0",
                "Manufacturer": "Samsung",
                "MediaType": "SSD",
                "CapacityBytes": 480 * 1024**3,
            },
            "/redfish/v1/Chassis/1": {
                "Assembly": {"@odata.id": "/redfish/v1/Chassis/1/Assembly"},
                "NetworkAdapters": {"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters"},
            },
            "/redfish/v1/Chassis/1/Assembly": {
                "Assemblies": [
                    {
                        "PhysicalContext": "SystemBoard",
                        "Vendor": "Huawei",
                        "Model": "BC11",
                        "SerialNumber": "BOARD-SN",
                    }
                ]
            },
            "/redfish/v1/Chassis/1/NetworkAdapters": {"Members": [{"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1"}]},
            "/redfish/v1/Chassis/1/NetworkAdapters/1": {
                "Manufacturer": "Broadcom",
                "Model": "BCM5720",
                "NetworkDeviceFunctions": {"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1/NetworkDeviceFunctions"},
            },
            "/redfish/v1/Chassis/1/NetworkAdapters/1/NetworkDeviceFunctions": {
                "Members": [{"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1/NetworkDeviceFunctions/1"}]
            },
            "/redfish/v1/Chassis/1/NetworkAdapters/1/NetworkDeviceFunctions/1": {
                "NetDevFuncType": "Ethernet",
                "Ethernet": {"MACAddress": "AA:BB:CC:DD:EE:FF"},
            },
        }
        if request.url.path not in payloads:
            raise AssertionError(request.url.path)
        return _response(request, payloads[request.url.path])

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

    assert result["success"] is True
    server = result["result"]["physcial_server"][0]
    assert server["cpu_cores"] == 8
    assert server["cpu_arch"] == "x86_64"
    assert server["board_serial"] == "BOARD-SN"
    assert result["result"]["memory"][0]["mem_locator"] == "DIMM_A1"
    assert result["result"]["disk"][0]["disk_name"] == "Disk.Bay.0"
    assert result["result"]["nic"][0]["nic_mac"] == "aa:bb:cc:dd:ee:ff"
    assert "EthernetInterfaces" not in "".join(requested)
    assert requested.count("/redfish/v1/Chassis/1/Drives/1") == 1


async def test_redfish_protocol_collects_storage_drives_array():
    requested = []

    def handler(request):
        requested.append(request.url.path)
        payloads = {
            "/redfish/v1/": {"Systems": {"@odata.id": "/redfish/v1/Systems"}},
            "/redfish/v1/Systems": {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]},
            "/redfish/v1/Systems/1": {
                "Manufacturer": "Huawei",
                "Storage": {"@odata.id": "/redfish/v1/Systems/1/Storage"},
            },
            "/redfish/v1/Systems/1/Storage": {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Storage/1"}]},
            "/redfish/v1/Systems/1/Storage/1": {
                "Drives": [
                    {"@odata.id": "/redfish/v1/Chassis/1/Drives/1"},
                    {"@odata.id": "/redfish/v1/Chassis/1/Drives/1"},
                ]
            },
            "/redfish/v1/Chassis/1/Drives/1": {
                "Id": "Disk.Bay.0",
                "Manufacturer": "Samsung",
                "MediaType": "SSD",
            },
        }
        if request.url.path not in payloads:
            raise AssertionError(request.url.path)
        return _response(request, payloads[request.url.path])

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

    assert result["success"] is True
    assert result["result"]["disk"][0]["disk_name"] == "Disk.Bay.0"
    assert "/redfish/v1/Systems/1/Storage/1/Drives" not in requested
    assert requested.count("/redfish/v1/Chassis/1/Drives/1") == 1


async def test_redfish_child_collection_failure_keeps_server_identity():
    def handler(request):
        if request.url.path == "/redfish/v1/":
            return _response(request, {"Systems": {"@odata.id": "/redfish/v1/Systems"}})
        if request.url.path == "/redfish/v1/Systems":
            return _response(request, {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]})
        if request.url.path == "/redfish/v1/Systems/1":
            return _response(
                request,
                {
                    "SerialNumber": "SERVER-SN-8",
                    "Memory": {"@odata.id": "/redfish/v1/Systems/1/Memory"},
                    "Storage": {"@odata.id": "https://attacker.invalid/redfish/v1/Systems/1/Storage"},
                },
            )
        if request.url.path == "/redfish/v1/Systems/1/Memory":
            return _response(request, {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Memory/1"}]})
        if request.url.path == "/redfish/v1/Systems/1/Memory/1":
            return httpx.Response(500, json={"error": "boom"}, request=request)
        raise AssertionError(request.url.path)

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
    assert result["result"]["physcial_server"][0]["serial_number"] == "SERVER-SN-8"
    assert "memory" not in result["result"]
    assert "disk" not in result["result"]


async def test_redfish_invalid_child_member_is_skipped():
    def handler(request):
        if request.url.path == "/redfish/v1/":
            return _response(request, {"Systems": {"@odata.id": "/redfish/v1/Systems"}})
        if request.url.path == "/redfish/v1/Systems":
            return _response(request, {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]})
        if request.url.path == "/redfish/v1/Systems/1":
            return _response(
                request,
                {"Memory": {"@odata.id": "/redfish/v1/Systems/1/Memory"}},
            )
        if request.url.path == "/redfish/v1/Systems/1/Memory":
            return _response(
                request,
                {
                    "Members": [
                        {"@odata.id": "https://attacker.invalid/redfish/v1/Systems/1/Memory/bad"},
                        {"@odata.id": "/redfish/v1/Systems/1/Memory/1"},
                    ]
                },
            )
        if request.url.path == "/redfish/v1/Systems/1/Memory/1":
            return _response(request, {"DeviceLocator": "DIMM_A1", "CapacityMiB": 32768})
        raise AssertionError(request.url.path)

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
    assert [item["mem_locator"] for item in result["result"]["memory"]] == ["DIMM_A1"]


async def test_redfish_child_transport_error_keeps_server_identity(monkeypatch):
    secret_sentinel = "BMC_SECRET_MUST_NOT_LEAK"
    log_calls = []

    def handler(request):
        if request.url.path == "/redfish/v1/":
            return _response(request, {"Systems": {"@odata.id": "/redfish/v1/Systems"}})
        if request.url.path == "/redfish/v1/Systems":
            return _response(request, {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]})
        if request.url.path == "/redfish/v1/Systems/1":
            return _response(
                request,
                {
                    "SerialNumber": "SERVER-SN-8",
                    "Memory": {"@odata.id": "/redfish/v1/Systems/1/Memory"},
                },
            )
        if request.url.path == "/redfish/v1/Systems/1/Memory":
            raise httpx.ConnectError(
                f"certificate verify failed {secret_sentinel}",
                request=request,
            )
        raise AssertionError(request.url.path)

    def capture_warning(template, *args, **kwargs):
        log_calls.append((template, args, kwargs))

    monkeypatch.setattr(redfish_info.logger, "warning", capture_warning)

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

    assert result["success"] is True
    assert result["result"]["physcial_server"][0]["serial_number"] == "SERVER-SN-8"
    assert "memory" not in result["result"]
    assert len(log_calls) == 1
    template, args, kwargs = log_calls[0]
    assert template.startswith("event=physical_server_redfish_child_skipped")
    assert secret_sentinel not in template % args


async def test_redfish_child_member_fetches_use_bounded_concurrency():
    collector = PhyscialServerRedfishInfo(
        {
            "host": "10.0.0.8",
            "username": "Administrator",
            "password": "secret",
        },
        transport=httpx.MockTransport(lambda request: _response(request, {})),
    )
    in_flight = 0
    peak = 0

    async def delayed_get_json(client, link):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        path = link["@odata.id"] if isinstance(link, dict) else str(link)
        return {"Id": path.rsplit("/", 1)[-1]}

    collector._get_json = delayed_get_json
    links = [{"@odata.id": f"/redfish/v1/Systems/1/Memory/{index}"} for index in range(12)]

    resources = await collector._read_linked_resources(None, links)

    assert [item["Id"] for item in resources] == [str(index) for index in range(12)]
    assert peak > 1
    assert peak <= PhyscialServerRedfishInfo.CHILD_CONCURRENCY


async def test_redfish_missing_power_and_controllers_stay_successful():
    def handler(request):
        payloads = {
            "/redfish/v1/": {"Systems": {"@odata.id": "/redfish/v1/Systems"}},
            "/redfish/v1/Systems": {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]},
            "/redfish/v1/Systems/1": {
                "SerialNumber": "SERVER-SN-8",
                "PowerState": "On",
                "Status": {"Health": "OK"},
                "Storage": {"@odata.id": "/redfish/v1/Systems/1/Storage"},
                "Links": {"Chassis": [{"@odata.id": "/redfish/v1/Chassis/1"}]},
            },
            "/redfish/v1/Systems/1/Storage": {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Storage/1"}]},
            "/redfish/v1/Systems/1/Storage/1": {
                "Drives": [{"@odata.id": "/redfish/v1/Chassis/1/Drives/1"}],
                "StorageControllers": {"@odata.id": "/redfish/v1/Systems/1/Storage/1/Controllers"},
            },
            "/redfish/v1/Chassis/1/Drives/1": {"Id": "Disk.Bay.0", "Status": {"Health": "OK"}},
            "/redfish/v1/Chassis/1": {"Power": {"@odata.id": "/redfish/v1/Chassis/1/Power"}},
        }
        if request.url.path == "/redfish/v1/Systems/1/Storage/1/Controllers":
            return httpx.Response(404, json={"error": "missing"}, request=request)
        if request.url.path == "/redfish/v1/Chassis/1/Power":
            return httpx.Response(404, json={"error": "missing"}, request=request)
        if request.url.path not in payloads:
            raise AssertionError(request.url.path)
        return _response(request, payloads[request.url.path])

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
    assert result["result"]["physcial_server"][0]["serial_number"] == "SERVER-SN-8"
    assert result["result"]["physcial_server"][0]["power_state"] == "On"
    assert result["result"]["physcial_server"][0]["health"] == "OK"
    assert result["result"]["disk"][0]["disk_name"] == "Disk.Bay.0"
    assert result["result"]["disk"][0]["health"] == "OK"
    assert "storage_controller" not in result["result"]
    assert "psu" not in result["result"]


async def test_redfish_maps_controllers_psu_and_nic_speed_when_present():
    def handler(request):
        payloads = {
            "/redfish/v1/": {"Systems": {"@odata.id": "/redfish/v1/Systems"}},
            "/redfish/v1/Systems": {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]},
            "/redfish/v1/Systems/1": {
                "SerialNumber": "SERVER-SN-8",
                "PowerState": "Off",
                "Status": {"Health": "Warning"},
                "Storage": {"@odata.id": "/redfish/v1/Systems/1/Storage"},
                "Links": {"Chassis": [{"@odata.id": "/redfish/v1/Chassis/1"}]},
            },
            "/redfish/v1/Systems/1/Storage": {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Storage/1"}]},
            "/redfish/v1/Systems/1/Storage/1": {
                "Drives": [{"@odata.id": "/redfish/v1/Chassis/1/Drives/1"}],
                "StorageControllers": [
                    {
                        "Id": "RAID.Integrated.1",
                        "MemberId": "0",
                        "Name": "RAID",
                        "Manufacturer": "Broadcom",
                        "Model": "SAS3408",
                        "SerialNumber": "SC-1",
                        "FirmwareVersion": "5.1",
                        "Status": {"Health": "OK"},
                    }
                ],
            },
            "/redfish/v1/Chassis/1/Drives/1": {
                "Id": "Disk.Bay.0",
                "Status": {"Health": "OK"},
                "PredictedMediaLifeLeftPercent": 90,
            },
            "/redfish/v1/Chassis/1": {
                "Power": {"@odata.id": "/redfish/v1/Chassis/1/Power"},
                "NetworkAdapters": {"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters"},
            },
            "/redfish/v1/Chassis/1/Power": {
                "PowerControl": [{"PowerConsumedWatts": 240}],
                "Voltages": [{"ReadingVolts": 12}],
                "PowerSupplies": [
                    {
                        "Name": "PSU1",
                        "Manufacturer": "Delta",
                        "Model": "DPS-1600",
                        "SerialNumber": "PSU-SN",
                        "PowerCapacityWatts": 1600,
                        "PowerInputWatts": 120,
                        "Status": {"Health": "OK"},
                    }
                ],
            },
            "/redfish/v1/Chassis/1/NetworkAdapters": {"Members": [{"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1"}]},
            "/redfish/v1/Chassis/1/NetworkAdapters/1": {
                "Name": "NIC.Slot.1",
                "Manufacturer": "Broadcom",
                "Model": "BCM5720",
                "NetworkDeviceFunctions": {"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1/NetworkDeviceFunctions"},
            },
            "/redfish/v1/Chassis/1/NetworkAdapters/1/NetworkDeviceFunctions": {
                "Members": [{"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1/NetworkDeviceFunctions/1"}]
            },
            "/redfish/v1/Chassis/1/NetworkAdapters/1/NetworkDeviceFunctions/1": {
                "Name": "NIC.Slot.1-1",
                "NetDevFuncType": "Ethernet",
                "Ethernet": {"MACAddress": "AA-BB-CC-DD-EE-FF"},
                "Links": {"PhysicalNetworkPortAssignment": {"@odata.id": "/redfish/v1/Chassis/1/NetworkAdapters/1/Ports/1"}},
            },
            "/redfish/v1/Chassis/1/NetworkAdapters/1/Ports/1": {"CurrentLinkSpeedMbps": 25000},
        }
        if request.url.path not in payloads:
            raise AssertionError(request.url.path)
        return _response(request, payloads[request.url.path])

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
    server = result["result"]["physcial_server"][0]
    assert server["power_state"] == "Off"
    assert server["health"] == "Warning"
    assert result["result"]["disk"][0]["disk_life_percent"] == 90
    controller = result["result"]["storage_controller"][0]
    assert controller["sc_id"] == "RAID.Integrated.1"
    assert controller["sc_firmware"] == "5.1"
    assert controller["self_device"] == "10.0.0.8"
    psu = result["result"]["psu"][0]
    assert psu["psu_name"] == "PSU1"
    assert psu["psu_capacity_watts"] == 1600
    assert "PowerInputWatts" not in psu
    assert "psu_input_watts" not in psu
    nic = result["result"]["nic"][0]
    assert nic["nic_iface"] == "NIC.Slot.1-1"
    assert nic["nic_speed_mbps"] == 25000
    assert "fan" not in result["result"]
    flat = json.dumps(result["result"])
    for forbidden in ("PowerInputWatts", "PowerConsumedWatts", "ReadingVolts", "ReadingCelsius", "PowerOutputWatts"):
        assert forbidden not in flat
