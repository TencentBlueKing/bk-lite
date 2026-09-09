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


def test_qcloud_empty_secret_matches_edit_task_sdk_error():
    manager = TencentCloudManager({"model_id": "qcloud", "cloud_id": "fusion-collector-default"})
    try:
        manager.get_credentials()
    except TencentCloudSDKException as err:
        assert err.code == "InvalidCredential"
        assert "secret id should not be none or empty" in err.message
        return
    raise AssertionError("expected TencentCloudSDKException for empty secret_id")
