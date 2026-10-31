from plugins.inputs.qcloud.qcloud_info import TencentCloudManager
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException


class _FakeService:
    def __init__(self, region, handler):
        self._region = region
        self._handler = handler

    def call_json(self, action, params):
        return self._handler(self._region, action, params or {})


class _FakeClient:
    def __init__(self, region, handler):
        self._region = region
        self._handler = handler

    def __getattr__(self, service):
        return _FakeService(self._region, self._handler)


def _page(items, params):
    # 腾讯云 Describe* 未传 Limit 时默认 20。
    limit = params.get("Limit") or 20
    offset = params.get("Offset") or 0
    return items[offset : offset + limit]


def _manager_with_client(handler, regions):
    manager = TencentCloudManager(
        {
            "secret_id": "test-secret-id",
            "secret_key": "test-secret-key",
            "ssl": True,
            "region_id": regions[0],
        }
    )
    manager.available_region_list = list(regions)
    manager.zone_id_zone_map = {}
    manager.get_tencent_client = lambda region="ap-guangzhou": _FakeClient(region, handler)
    return manager


def test_qcloud_cvm_collects_all_pages_instead_of_default_20():
    instances = [
        {
            "InstanceId": f"ins-{index}",
            "InstanceName": f"cvm-{index}",
            "Placement": {"Zone": "ap-guangzhou-1"},
        }
        for index in range(109)
    ]

    def handler(region, action, params):
        assert action == "DescribeInstances"
        return {"Response": {"TotalCount": 109, "InstanceSet": _page(instances, params)}}

    result = _manager_with_client(handler, ["ap-guangzhou"]).get_qcloud_cvm()

    assert len(result) == 109
    assert all(isinstance(item, dict) for item in result)
    assert {item["resource_id"] for item in result} == {f"ins-{index}" for index in range(109)}


def test_qcloud_mysql_returns_flat_instance_dicts():
    def handler(region, action, params):
        assert action == "DescribeDBInstances"
        items = [
            {"InstanceId": "cdb-a", "InstanceName": "mysql-a", "Status": 1, "PayType": 1},
            {"InstanceId": "cdb-b", "InstanceName": "mysql-b", "Status": 1, "PayType": 0},
        ]
        return {"Response": {"TotalCount": 2, "Items": _page(items, params)}}

    result = _manager_with_client(handler, ["ap-guangzhou"]).get_qcloud_mysql()

    assert [item["resource_id"] for item in result] == ["cdb-a", "cdb-b"]
    assert all(isinstance(item, dict) for item in result)
    assert result[0]["resource_name"] == "mysql-a"


def test_qcloud_redis_keeps_supported_region_when_another_region_is_unsupported():
    def handler(region, action, params):
        if region == "ap-osaka":
            raise TencentCloudSDKException("UnsupportedRegion", "该接口不支持此地域访问。", "req-1")
        items = [{"InstanceId": "crs-1", "InstanceName": "redis-gz", "Status": 2}]
        return {"Response": {"TotalCount": 1, "InstanceSet": _page(items, params)}}

    result = _manager_with_client(handler, ["ap-guangzhou", "ap-osaka"]).get_qcloud_redis()

    assert [item["resource_id"] for item in result] == ["crs-1"]


def test_qcloud_clb_collects_instances_with_null_zone_fields():
    instances = []
    for index in range(20):
        instances.append(
            {
                "LoadBalancerId": f"lb-{index}",
                "LoadBalancerName": f"clb-{index}",
                "MasterZone": None,
                "BackupZoneSet": None,
                "LoadBalancerVips": ["10.0.0.1"] if index == 0 else None,
                "Status": 1,
            }
        )
    for index in range(20, 36):
        instances.append(
            {
                "LoadBalancerId": f"lb-{index}",
                "LoadBalancerName": f"clb-{index}",
                "MasterZone": {"Zone": "ap-guangzhou-2"},
                "BackupZoneSet": [{"Zone": "ap-guangzhou-3"}],
                "LoadBalancerVips": ["10.0.0.2"],
                "Status": 1,
            }
        )

    def handler(region, action, params):
        assert action == "DescribeLoadBalancers"
        return {"Response": {"TotalCount": 36, "LoadBalancerSet": _page(instances, params)}}

    result = _manager_with_client(handler, ["ap-guangzhou"]).get_qcloud_clb()

    assert len(result) == 36
    assert result[0]["resource_id"] == "lb-0"
    assert result[0]["master_zone"] is None
    assert result[0]["backup_zone"] == ""
    assert result[0]["ip_addr"] == "10.0.0.1"
    assert result[20]["master_zone"] == "ap-guangzhou-2"
    assert result[20]["backup_zone"] == "ap-guangzhou-3"


def test_qcloud_manager_reads_persisted_access_key_aliases():
    manager = TencentCloudManager(
        {
            "accessKey": "AKIDreal",
            "accessSecret": "sk-real",
        }
    )
    assert manager.secret_id == "AKIDreal"
    assert manager.secret_key == "sk-real"
    assert manager.get_credentials().secret_id == "AKIDreal"


def test_qcloud_tke_client_version_is_registered():
    from plugins.constants import client_version_map

    assert client_version_map["tke"] == "2018-05-25"
    assert client_version_map["vpc"] == "2017-03-12"


def _clusters(count):
    return [
        {
            "ClusterId": f"cls-{index}",
            "ClusterName": f"tke-{index}",
            "ClusterStatus": "Running",
            "ClusterType": "MANAGED_CLUSTER",
            "ClusterVersion": "1.28.3",
            "ClusterNetworkSettings": {"VpcId": "vpc-1", "ClusterCIDR": "10.0.0.0/16", "ServiceCIDR": "172.16.0.0/20"},
            "Property": '{"NetworkType":"VPC-CNI"}',
            "ClusterNodeNum": 3,
            "ClusterMaterNodeNum": 2,
            "ContainerRuntime": "containerd",
            "RuntimeVersion": "1.6.9",
            "ClusterOs": "tlinux3.2",
            "ProjectId": 1001,
            "ClusterLevel": "L5",
            "IsHighAvailability": True,
            "CreatedTime": "2024-01-02T03:04:05Z",
            "DeletionProtection": False,
            "TagSpecification": [{"ResourceType": "cluster", "Tags": [{"Key": "env", "Value": "prod"}]}],
        }
        for index in range(count)
    ]


def test_qcloud_tke_cluster_pages_and_maps_fields():
    clusters = _clusters(101)
    seen = []

    def handler(region, action, params):
        assert action == "DescribeClusters"
        assert params["Limit"] == 100
        seen.append(params["Offset"])
        return {"Response": {"TotalCount": 101, "Clusters": _page(clusters, params)}}

    result = _manager_with_client(handler, ["ap-guangzhou"]).get_qcloud_tke_cluster()

    assert seen == [0, 100]
    assert len(result) == 101
    first = result[0]
    assert first["resource_name"] == "tke-0"
    assert first["resource_id"] == "cls-0"
    assert first["vpc"] == "vpc-1"
    assert first["cluster_cidr"] == "10.0.0.0/16"
    assert first["service_cidr"] == "172.16.0.0/20"
    assert first["network_type"] == "VPC-CNI"
    assert first["node_num"] == 3
    assert first["master_node_num"] == 2
    assert first["ha"] == "true"
    assert first["deletion_protection"] == "false"
    assert first["tag"] == "env:prod"
    assert first["project_id"] == 1001


def test_qcloud_tke_node_lists_clusters_then_instances_and_skips_one_failure():
    import logging

    records = []

    class _Handler(logging.Handler):
        def emit(self, record):
            records.append(record)

    log = logging.getLogger("qcloud.p0.tke.node")
    log.setLevel(logging.WARNING)
    log.addHandler(_Handler())
    sentinel = "SECRET-PSK-DO-NOT-COLLECT"

    def handler(region, action, params):
        if action == "DescribeClusters":
            assert params["Limit"] == 100
            return {
                "Response": {
                    "Clusters": _page(
                        [{"ClusterId": "cls-ok", "ClusterName": "ok"}, {"ClusterId": "cls-bad", "ClusterName": "bad"}],
                        params,
                    )
                }
            }
        assert action == "DescribeClusterInstances"
        assert params["Limit"] == 100
        assert params["ClusterId"] in {"cls-ok", "cls-bad"}
        if params["ClusterId"] == "cls-bad":
            raise RuntimeError(sentinel)
        return {
            "Response": {
                "InstanceSet": [
                    {
                        "InstanceId": "",
                        "LanIP": "10.0.0.8",
                        "InstanceRole": "WORKER",
                        "InstanceState": "running",
                        "CreatedTime": "2024-02-02T00:00:00Z",
                    },
                    {
                        "InstanceId": "ins-1",
                        "LanIP": "10.0.0.9",
                        "InstanceRole": "MASTER",
                        "InstanceState": "running",
                        "NodePoolId": "np-1",
                        "CreatedTime": "2024-02-03T00:00:00Z",
                    },
                ]
            }
        }

    import plugins.inputs.qcloud.qcloud_info as qcloud_info

    original = qcloud_info.logger
    qcloud_info.logger = log
    try:
        result = _manager_with_client(handler, ["ap-guangzhou"]).get_qcloud_tke_node()
    finally:
        qcloud_info.logger = original
        log.removeHandler(log.handlers[-1])

    assert [item["resource_id"] for item in result] == ["", "ins-1"]
    assert result[0]["resource_name"] == "10.0.0.8"
    assert result[1]["resource_name"] == "ins-1"
    assert result[1]["cluster_id"] == "cls-ok"
    assert result[1]["ip_addr"] == "10.0.0.9"
    assert result[1]["tag"] == ""
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=qcloud_collect_skipped failed_stage=%s region=%s cluster_id=%s error_type=%s"
    assert record.args == ("DescribeClusterInstances", "ap-guangzhou", "cls-bad", "RuntimeError")
    assert record.exc_info is None
    rendered = record.getMessage()
    assert "cls-bad" in rendered
    assert sentinel not in rendered
    assert sentinel not in str(record.args)


def test_qcloud_tke_cluster_and_node_share_one_describe_clusters_call():
    calls = []

    def handler(region, action, params):
        calls.append(action)
        if action == "DescribeClusters":
            return {"Response": {"Clusters": [{"ClusterId": "cls-1", "ClusterName": "c1"}]}}
        return {"Response": {"InstanceSet": [{"InstanceId": "ins-1", "LanIP": "10.0.0.1"}]}}

    manager = _manager_with_client(handler, ["ap-guangzhou"])
    clusters = manager.get_qcloud_tke_cluster()
    nodes = manager.get_qcloud_tke_node()

    assert [item["resource_id"] for item in clusters] == ["cls-1"]
    assert [item["cluster_id"] for item in nodes] == ["cls-1"]
    assert calls == ["DescribeClusters", "DescribeClusterInstances"]


def test_qcloud_tke_node_retries_describe_clusters_after_cluster_listing_failed():
    attempts = []

    def handler(region, action, params):
        if action == "DescribeClusters":
            attempts.append(action)
            if len(attempts) == 1:
                raise RuntimeError("temporary")
            return {"Response": {"Clusters": [{"ClusterId": "cls-1"}]}}
        return {"Response": {"InstanceSet": [{"InstanceId": "ins-1"}]}}

    manager = _manager_with_client(handler, ["ap-guangzhou"])
    try:
        manager.get_qcloud_tke_cluster()
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected cluster listing failure")

    assert [item["resource_id"] for item in manager.get_qcloud_tke_node()] == ["ins-1"]
    assert len(attempts) == 2


def test_qcloud_tke_node_empty_clusters_is_empty_success():
    def handler(region, action, params):
        assert action == "DescribeClusters"
        return {"Response": {"Clusters": []}}

    assert _manager_with_client(handler, ["ap-guangzhou"]).get_qcloud_tke_node() == []


def test_qcloud_tke_node_all_cluster_failures_are_not_an_empty_snapshot():
    def handler(region, action, params):
        if action == "DescribeClusters":
            return {"Response": {"Clusters": [{"ClusterId": "cls-1"}, {"ClusterId": "cls-2"}]}}
        raise RuntimeError("temporary")

    manager = _manager_with_client(handler, ["ap-guangzhou"])
    try:
        manager.get_qcloud_tke_node()
    except RuntimeError as err:
        assert str(err) == "qcloud tke node collection failed for all clusters"
        return
    raise AssertionError("expected all-cluster failure")


def test_qcloud_vpn_and_nat_empty_inventory_returns_empty_lists():
    def handler(region, action, params):
        assert params["Limit"] == 100
        assert params["Offset"] == 0
        return {"Response": {}}

    manager = _manager_with_client(handler, ["ap-guangzhou"])
    assert manager.get_qcloud_vpn_gateway() == []
    assert manager.get_qcloud_customer_gateway() == []
    assert manager.get_qcloud_vpn_connection() == []
    assert manager.get_qcloud_nat_gateway() == []


def test_qcloud_vpn_connection_never_keeps_presharekey_and_nat_joins_eips():
    sentinel = "SECRET-PSK-DO-NOT-COLLECT"

    def handler(region, action, params):
        if action == "DescribeVpnConnections":
            return {
                "Response": {
                    "VpnConnectionSet": [
                        {
                            "VpnConnectionId": "vpnx-1",
                            "VpnConnectionName": "link-1",
                            "VpcId": "vpc-1",
                            "VpnGatewayId": "vpngw-1",
                            "CustomerGatewayId": "cgw-1",
                            "State": "AVAILABLE",
                            "NetStatus": "AVAILABLE",
                            "VpnProto": "IPSEC",
                            "RouteType": "StaticRoute",
                            "CreatedTime": "2024-03-01T00:00:00Z",
                            "PreShareKey": sentinel,
                            "TagSet": [{"Key": "team", "Value": "net"}],
                        }
                    ]
                }
            }
        if action == "DescribeNatGateways":
            return {
                "Response": {
                    "NatGatewaySet": [
                        {
                            "NatGatewayId": "nat-1",
                            "NatGatewayName": "nat-a",
                            "Zone": "ap-guangzhou-3",
                            "VpcId": "vpc-1",
                            "SubnetId": "subnet-1",
                            "State": "AVAILABLE",
                            "NetworkState": "AVAILABLE",
                            "InternetMaxBandwidthOut": 100,
                            "MaxConcurrentConnection": 1000000,
                            "PublicIpAddressSet": [
                                {"AddressId": "eip-1", "PublicIpAddress": "1.1.1.1"},
                                {"AddressId": "eip-2", "PublicIpAddress": "2.2.2.2"},
                            ],
                            "NatProductVersion": 2,
                            "RestrictState": "NORMAL",
                            "CreatedTime": "2024-04-01T00:00:00Z",
                            "TagSet": [{"TagKey": "env", "TagValue": "prod"}],
                        }
                    ]
                }
            }
        if action == "DescribeVpnGateways":
            return {
                "Response": {
                    "VpnGatewaySet": [
                        {
                            "VpnGatewayId": "vpngw-1",
                            "VpnGatewayName": "gw",
                            "Zone": "ap-guangzhou-3",
                            "VpcId": "vpc-1",
                            "State": "AVAILABLE",
                            "Type": "IPSEC",
                            "PublicIpAddress": "9.9.9.9",
                            "InternetMaxBandwidthOut": 20,
                            "InstanceChargeType": "POSTPAID_BY_HOUR",
                            "CreatedTime": "2024-01-01T00:00:00Z",
                            "ExpiredTime": "",
                            "RenewFlag": "NOTIFY_AND_AUTO_RENEW",
                            "Version": "IKEV2",
                            "MaxConnection": 50,
                            "TagSet": [],
                        }
                    ]
                }
            }
        return {
            "Response": {
                "CustomerGatewaySet": [
                    {
                        "CustomerGatewayId": "cgw-1",
                        "CustomerGatewayName": "peer",
                        "IpAddress": "8.8.8.8",
                        "CreatedTime": "2024-01-01T00:00:00Z",
                        "TagSet": [],
                    }
                ]
            }
        }

    manager = _manager_with_client(handler, ["ap-guangzhou"])
    connection = manager.get_qcloud_vpn_connection()[0]
    rendered = str(connection)
    assert sentinel not in rendered
    assert "PreShareKey" not in connection
    assert connection["vpn_gateway_id"] == "vpngw-1"
    assert connection["customer_gateway_id"] == "cgw-1"
    assert connection["tag"] == "team:net"
    nat = manager.get_qcloud_nat_gateway()[0]
    assert nat["eip_ids"] == "eip-1,eip-2"
    assert nat["eip_addrs"] == "1.1.1.1,2.2.2.2"
    assert nat["bandwidth_mbps"] == 100
    assert nat["tag"] == "env:prod"
    gateway = manager.get_qcloud_vpn_gateway()[0]
    assert gateway["resource_id"] == "vpngw-1"
    assert gateway["max_connection"] == 50
    customer = manager.get_qcloud_customer_gateway()[0]
    assert customer["ip_addr"] == "8.8.8.8"


def test_qcloud_exec_script_registers_p0_collectors():
    manager = TencentCloudManager({"secret_id": "test-secret-id", "secret_key": "test-secret-key", "region_id": "ap-guangzhou"})
    names = [
        "get_qcloud_cvm",
        "get_qcloud_rocketmq",
        "get_qcloud_mysql",
        "get_qcloud_redis",
        "get_qcloud_mongodb",
        "get_qcloud_pgsql",
        "get_qcloud_pulsar_cluster",
        "get_qcloud_cmq",
        "get_qcloud_cmq_topic",
        "get_qcloud_clb",
        "get_qcloud_eip",
        "get_qcloud_tke_cluster",
        "get_qcloud_tke_node",
        "get_qcloud_vpn_gateway",
        "get_qcloud_customer_gateway",
        "get_qcloud_vpn_connection",
        "get_qcloud_nat_gateway",
        "get_qcloud_bucket",
        "get_qcloud_filesystem",
        "get_qcloud_domain",
    ]
    for name in names:
        setattr(manager, name, lambda name=name: [])

    result = manager.exec_script()

    assert set(result) == {
        "qcloud_cvm",
        "qcloud_rocketmq",
        "qcloud_mysql",
        "qcloud_redis",
        "qcloud_mongodb",
        "qcloud_pgsql",
        "qcloud_pulsar_cluster",
        "qcloud_cmq",
        "qcloud_cmq_topic",
        "qcloud_clb",
        "qcloud_eip",
        "qcloud_tke_cluster",
        "qcloud_tke_node",
        "qcloud_vpn_gateway",
        "qcloud_customer_gateway",
        "qcloud_vpn_connection",
        "qcloud_nat_gateway",
        "qcloud_bucket",
        "qcloud_filesystem",
        "qcloud_domain",
    }
    assert all(result[key] == [] for key in result)


def test_qcloud_empty_secret_matches_edit_task_sdk_error():
    manager = TencentCloudManager({"model_id": "qcloud", "cloud_id": "fusion-collector-default"})
    try:
        manager.get_credentials()
    except TencentCloudSDKException as err:
        assert err.code == "InvalidCredential"
        assert "secret id should not be none or empty" in err.message
        return
    raise AssertionError("expected TencentCloudSDKException for empty secret_id")
