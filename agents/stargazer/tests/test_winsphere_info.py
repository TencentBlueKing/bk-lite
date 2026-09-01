import pytest
from enterprise.plugins.inputs.winsphere.winsphere_info import MODEL_IDS, WinSphereClient, WinSphereError, WinSphereInfo


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.cookies = {}

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs, dict(self.cookies)))
        response = self.responses.pop(0)
        if url.endswith("/api/login") and response.status_code == 200:
            self.cookies["SESSION"] = response.json()["sessionId"]
        return response


@pytest.mark.parametrize(
    "host",
    [
        "10.0.0.10:8443",
        "https://10.0.0.10",
        "ws.example.com/path",
        "2001:db8::1",
        "bad host",
        "-bad.example.com",
    ],
)
def test_client_rejects_management_address_that_is_not_a_host(host):
    with pytest.raises(WinSphereError, match="management address"):
        WinSphereClient(
            host=host,
            user="collector",
            password="secret",
        )


def test_client_logs_in_once_and_collects_all_pool_pages():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(
                200,
                {
                    "data": [
                        {"id": "pool-1", "name": "生产池"},
                        {"id": "pool-2", "name": "测试池"},
                    ],
                    "total": 3,
                    "start": 1,
                    "size": 2,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [{"id": "pool-3", "name": "灾备池"}],
                    "total": 3,
                    "start": 2,
                    "size": 2,
                },
            ),
        ]
    )
    client = WinSphereClient(
        host="winsphere.example.com",
        user="collector",
        password="secret",
        https_port=8443,
        verify_tls=True,
        session=session,
        page_size=2,
    )

    pools = client.list_pools()

    assert pools == [
        {"id": "pool-1", "name": "生产池"},
        {"id": "pool-2", "name": "测试池"},
        {"id": "pool-3", "name": "灾备池"},
    ]
    assert session.calls[0][:2] == (
        "POST",
        "https://winsphere.example.com:8443/api/login",
    )
    assert session.calls[0][2]["json"] == {"user": "collector", "pwd": "secret"}
    assert session.calls[1][3] == {"SESSION": "session-1"}
    assert session.calls[2][3] == {"SESSION": "session-1"}
    assert session.calls[1][2]["params"]["start"] == 1
    assert session.calls[2][2]["params"]["start"] == 2


def test_client_reauthenticates_once_after_session_expires():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(401, {"message": "expired"}),
            FakeResponse(200, {"sessionId": "session-2"}),
            FakeResponse(200, {"data": [], "total": 0, "start": 1, "size": 200}),
        ]
    )
    client = WinSphereClient(
        host="10.0.0.10",
        user="collector",
        password="secret",
        session=session,
    )

    assert client.list_pools() == []
    assert [call[0] for call in session.calls] == ["POST", "GET", "POST", "GET"]
    assert session.calls[-1][3] == {"SESSION": "session-2"}


def test_client_does_not_retry_forever_after_second_401():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(401, {"message": "expired"}),
            FakeResponse(200, {"sessionId": "session-2"}),
            FakeResponse(401, {"message": "still unauthorized"}),
        ]
    )
    client = WinSphereClient(
        host="10.0.0.10",
        user="collector",
        password="secret",
        session=session,
    )

    with pytest.raises(WinSphereError, match=r"HTTP 401"):
        client.list_pools()

    assert [call[0] for call in session.calls] == ["POST", "GET", "POST", "GET"]


def test_standard_port_groups_are_paginated():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(
                200,
                {"data": [{"id": "pg-1"}], "total": 2, "start": 1, "size": 1},
            ),
            FakeResponse(
                200,
                {"data": [{"id": "pg-2"}], "total": 2, "start": 2, "size": 1},
            ),
        ]
    )
    client = WinSphereClient(
        host="10.0.0.10",
        user="collector",
        password="secret",
        session=session,
        page_size=1,
    )

    assert client.list_standard_port_groups() == [{"id": "pg-1"}, {"id": "pg-2"}]


def test_paginated_endpoint_without_total_aborts_snapshot():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(200, {"data": [{"id": "pool-1"}]}),
        ]
    )
    client = WinSphereClient(
        host="10.0.0.10",
        user="collector",
        password="secret",
        session=session,
    )

    with pytest.raises(WinSphereError, match="pagination total"):
        client.list_pools()


def test_paginated_endpoint_rejects_total_drift_between_pages():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(
                200,
                {
                    "data": [{"id": "pool-1"}, {"id": "pool-2"}],
                    "total": 3,
                    "start": 1,
                    "size": 2,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [{"id": "pool-3"}],
                    "total": 4,
                    "start": 2,
                    "size": 2,
                },
            ),
        ]
    )
    client = WinSphereClient(
        host="10.0.0.10",
        user="collector",
        password="secret",
        session=session,
        page_size=2,
    )

    with pytest.raises(WinSphereError, match="pagination total changed"):
        client.list_pools()


def test_paginated_endpoint_rejects_wrong_response_page():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(
                200,
                {
                    "data": [{"id": "pool-1"}],
                    "total": 1,
                    "start": 2,
                    "size": 1,
                },
            ),
        ]
    )
    client = WinSphereClient(
        host="10.0.0.10",
        user="collector",
        password="secret",
        session=session,
        page_size=1,
    )

    with pytest.raises(WinSphereError, match="pagination page mismatch"):
        client.list_pools()


def test_paginated_endpoint_rejects_duplicate_resource_ids_across_pages():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(
                200,
                {
                    "data": [{"id": "pool-1"}, {"id": "pool-2"}],
                    "total": 4,
                    "start": 1,
                    "size": 2,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [{"id": "pool-2"}, {"id": "pool-3"}],
                    "total": 4,
                    "start": 2,
                    "size": 2,
                },
            ),
        ]
    )
    client = WinSphereClient(
        host="10.0.0.10",
        user="collector",
        password="secret",
        session=session,
        page_size=2,
    )

    with pytest.raises(WinSphereError, match="duplicate resource id"):
        client.list_pools()


def test_standard_switch_pagination_allows_same_native_id_on_different_hosts():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(
                200,
                {
                    "data": [{"id": "switch-1", "hostId": "host-1"}],
                    "total": 2,
                    "start": 1,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [{"id": "switch-1", "hostId": "host-2"}],
                    "total": 2,
                    "start": 2,
                },
            ),
        ]
    )
    client = WinSphereClient(
        host="10.0.0.10",
        user="collector",
        password="secret",
        session=session,
        page_size=1,
    )

    switches = client.list_standard_switches()

    assert [(item["hostId"], item["id"]) for item in switches] == [
        ("host-1", "switch-1"),
        ("host-2", "switch-1"),
    ]


def test_standard_port_group_pagination_uses_parent_scoped_identity():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "pg-1",
                            "hostId": "host-1",
                            "vswitchId": "switch-1",
                        }
                    ],
                    "total": 2,
                    "start": 1,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "pg-1",
                            "hostId": "host-1",
                            "vswitchId": "switch-2",
                        }
                    ],
                    "total": 2,
                    "start": 2,
                },
            ),
        ]
    )
    client = WinSphereClient(
        host="10.0.0.10",
        user="collector",
        password="secret",
        session=session,
        page_size=1,
    )

    port_groups = client.list_standard_port_groups()

    assert [(item["hostId"], item["vswitchId"], item["id"]) for item in port_groups] == [
        ("host-1", "switch-1", "pg-1"),
        ("host-1", "switch-2", "pg-1"),
    ]


def test_missing_optional_network_endpoint_is_an_empty_collection():
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(404, {"message": "feature not installed"}),
        ]
    )
    client = WinSphereClient(
        host="10.0.0.10",
        user="collector",
        password="secret",
        session=session,
    )

    assert client.list_distributed_switches() == []
    assert client.optional_unavailable_paths == {"/api/compute/dvswitchs"}


@pytest.mark.asyncio
async def test_required_endpoint_failure_aborts_snapshot_without_partial_result(monkeypatch):
    collector = object.__new__(WinSphereInfo)

    class FailingClient:
        def list_pools(self):
            return [{"id": "pool-1", "name": "资源池"}]

        def list_clusters(self):
            raise WinSphereError("WinSphere request failed: /api/compute/clusters HTTP 503")

    collector.client = FailingClient()

    with pytest.raises(WinSphereError, match="clusters HTTP 503"):
        await collector.list_all_resources()


@pytest.mark.asyncio
async def test_all_resources_without_stable_ids_fail_the_snapshot():
    collector = object.__new__(WinSphereInfo)

    class InvalidIdentityClient:
        def list_pools(self):
            return [{"name": "没有稳定标识的资源池"}]

    collector.client = InvalidIdentityClient()

    with pytest.raises(WinSphereError, match="all winsphere_host_pool"):
        await collector.list_all_resources()


@pytest.mark.asyncio
async def test_unified_switch_model_accepts_valid_distributed_switches_when_standard_are_invalid():
    collector = object.__new__(WinSphereInfo)
    collector.host = "10.0.0.10"
    collector.https_port = 443
    collector.platform_id = "https://10.0.0.10:443"

    class MixedSwitchClient:
        def list_pools(self):
            return []

        def list_clusters(self):
            return []

        def list_hosts(self):
            return []

        def list_domains(self):
            return []

        def list_storage_pools(self):
            return []

        def list_standard_switches(self):
            return [{"id": "standard-without-host"}]

        def list_standard_port_groups(self):
            return []

        def list_distributed_switches(self):
            return [{"id": "dvs-1", "name": "分布式交换机"}]

        def list_distributed_switch_hosts(self, _switch_id):
            return []

        def list_distributed_port_groups(self, _switch_id):
            return []

    collector.client = MixedSwitchClient()

    result = (await collector.list_all_resources())["result"]

    assert [item["resource_id"] for item in result["winsphere_vswitch"]] == ["distributed:dvs-1"]


def test_invalid_timestamp_is_not_published_as_iso_time():
    assert WinSphereInfo._iso_time("not-a-timestamp") == ""


def test_duplicate_resource_names_remain_distinct_by_platform_and_stable_id():
    collector = object.__new__(WinSphereInfo)
    collector.platform_id = "https://10.0.0.10:443"

    resources = [
        collector._pool({"id": "pool-1", "name": "生产资源"}),
        collector._pool({"id": "pool-2", "name": "生产资源"}),
    ]

    assert resources[0]["inst_name"] != resources[1]["inst_name"]
    assert resources[0]["inst_name"].startswith(collector.platform_id)


@pytest.mark.asyncio
async def test_plugin_collects_eight_inventory_types_from_one_atomic_snapshot():
    gib = 1024**3
    session = FakeSession(
        [
            FakeResponse(200, {"sessionId": "session-1"}),
            FakeResponse(200, {"data": [{"id": "pool-1", "name": "资源池"}], "total": 1}),
            FakeResponse(
                200,
                {
                    "data": [{"id": "cluster-1", "name": "集群A", "poolId": "pool-1"}],
                    "total": 1,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "host-1",
                            "name": "宿主机A",
                            "ip": "10.0.0.11",
                            "clusterId": "cluster-1",
                            "poolId": "pool-1",
                            "memory": 128 * gib,
                            "storage": 2 * gib,
                        }
                    ],
                    "total": 1,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "vm-1",
                            "name": "虚拟机A",
                            "hostId": "host-1",
                            "memory": 8 * gib,
                            "diskSize": 50 * gib,
                            "createTime": "2026-07-27 12:34:56",
                            "upTime": 3600,
                        }
                    ],
                    "total": 1,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "storage-1",
                            "name": "存储池A",
                            "capacity": 100 * gib,
                            "available": 40 * gib,
                            "spHostRelationRspList": [{"hostId": "host-1"}],
                        }
                    ],
                    "total": 1,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [{"id": "switch-1", "name": "br0", "hostId": "host-1"}],
                    "total": 1,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "pg-1",
                            "name": "管理网络",
                            "vswitchId": "switch-1",
                            "hostId": "host-1",
                        }
                    ],
                    "total": 1,
                },
            ),
            FakeResponse(
                200,
                {
                    "data": [{"id": "dvs-1", "name": "业务分布式交换机"}],
                    "total": 1,
                },
            ),
            FakeResponse(200, {"data": [{"id": "host-1"}]}),
            FakeResponse(
                200,
                {
                    "data": [
                        {
                            "id": "dpg-1",
                            "name": "业务网络",
                            "dvswitchId": "wrong-dvs",
                        }
                    ],
                    "total": 1,
                },
            ),
        ]
    )
    collector = WinSphereInfo(
        {
            "host": "10.0.0.10",
            "user": "collector",
            "password": "secret",
            "https_port": 443,
            "verify_tls": False,
            "session": session,
        }
    )

    snapshot = await collector.list_all_resources()

    assert snapshot["success"] is True
    assert snapshot["snapshot_status"] == "complete"
    assert snapshot["snapshot_id"]
    assert snapshot["snapshot_manifest"]["schema_version"] == 1
    assert snapshot["snapshot_manifest"]["snapshot_id"] == snapshot["snapshot_id"]
    assert snapshot["snapshot_manifest"]["expected_models"] == list(MODEL_IDS)
    assert snapshot["snapshot_manifest"]["models"]["winsphere"] == {
        "count": 1,
        "identity_hash": ("0af2cbcd443771b449fe33928fc5c83ce" "6e61db6ba2eef032a5eef7f51be6fe7"),
        "authoritative": True,
    }
    assert snapshot["snapshot_manifest"]["models"]["winsphere_vswitch"] == {
        "count": 2,
        "identity_hash": ("74b082908c8afb3d074d4fb7122f248e" "05f0aefcd7adcb6d95c1701c395f4399"),
        "authoritative": True,
    }
    assert set(snapshot["result"]) == {
        "winsphere",
        "winsphere_host_pool",
        "winsphere_cluster",
        "winsphere_host",
        "winsphere_vm",
        "winsphere_storage_pool",
        "winsphere_vswitch",
        "winsphere_port_group",
    }
    assert snapshot["result"]["winsphere_host"][0]["memory_gib"] == "128.00"
    assert snapshot["result"]["winsphere_vm"][0]["disk_size_gib"] == "50.00"
    assert snapshot["result"]["winsphere_vm"][0]["create_time"] == ("2026-07-27T12:34:56+08:00")
    assert snapshot["result"]["winsphere_vm"][0]["up_time_seconds"] == "3600"
    assert snapshot["result"]["winsphere_vm"][0]["inst_name"] == ("https://10.0.0.10:443/虚拟机A[vm-1]")
    assert snapshot["result"]["winsphere_storage_pool"][0]["available_gib"] == "40.00"

    switches = snapshot["result"]["winsphere_vswitch"]
    assert [item["resource_id"] for item in switches] == [
        "standard:host-1:switch-1",
        "distributed:dvs-1",
    ]
    assert switches[1]["host_ids"] == ["host-1"]

    port_groups = snapshot["result"]["winsphere_port_group"]
    assert [item["resource_id"] for item in port_groups] == [
        "standard:host-1:switch-1:pg-1",
        "distributed:dvs-1:dpg-1",
    ]
    assert all(item["platform_id"] == "https://10.0.0.10:443" for model_items in snapshot["result"].values() for item in model_items)
