"""阿里云配置采集回归：真实 SDK 响应模型、分页和传输边界，无外部 IO。"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alibabacloud_alikafka20190916 import models as kafka
from alibabacloud_oss20190517 import models as oss
from core.collection.contracts import StructuredMetricsPayload
from plugins.base_utils import convert_to_prometheus_format
from plugins.inputs.aliyun.aliyun_info import Aliyun
from tasks.utils.nats_helper import convert_structured_metrics_to_influx


@pytest.mark.parametrize("formatter", [Aliyun.format_aliyun_mysql, Aliyun.format_aliyun_pgsql])
def test_rds_retains_api_billing_type(formatter):
    actual = formatter([{"DBInstanceId": "rds-test", "DBInstanceDescription": "test", "PayType": "Postpaid"}])[0]
    assert actual["charge_type"] == "Postpaid"


def test_mysql_retains_api_network_type():
    actual = Aliyun.format_aliyun_mysql([{"DBInstanceId": "rds-test", "DBInstanceDescription": "test", "DBInstanceNetType": "Intranet"}])[0]
    assert actual.get("net_type") == "Intranet"


def test_kafka_real_sdk_identity_and_status():
    raw = kafka.GetInstanceListResponseBodyInstanceListInstanceVO(
        instance_id="alikafka-test",
        name="test-kafka",
        region_id="cn-shenzhen",
        zone_id="zone-test",
        vpc_id="vpc-test",
        service_status=5,
        view_instance_status_code=5,
        io_max_spec="alikafka.hw.2xlarge",
        disk_size=100,
        disk_type=0,
        msg_retain=72,
        topic_num_limit=50,
        io_max_read=100,
        io_max_write=50,
        paid_type=0,
        create_time=1704067200000,
    ).to_map()
    actual = Aliyun.format_aliyun_kafka_inst([raw])[0]
    assert actual["resource_id"] == "alikafka-test"
    assert actual["resource_name"] == "test-kafka"
    assert actual["status"] == 5
    assert actual["class"] == "alikafka.hw.2xlarge"


def test_oss_sdk_response_formats_without_unsupported_field():
    raw = oss.BucketInfoBucket(
        name="test-bucket",
        location="oss-cn-shenzhen",
        extranet_endpoint="oss-cn-shenzhen.aliyuncs.com",
        intranet_endpoint="oss-cn-shenzhen-internal.aliyuncs.com",
        storage_class="Standard",
        cross_region_replication="Disabled",
        creation_date="2024-01-01T00:00:00.000Z",
    ).to_map()
    actual = Aliyun.format_bucket_data([raw])[0]
    assert actual["resource_id"] == "test-bucket"
    assert actual["block_public_access"] == ""
    raw["BlockPublicAccess"] = False
    assert Aliyun.format_bucket_data([raw])[0]["block_public_access"] is False


def test_oss_collects_all_pages():
    plugin = Aliyun.__new__(Aliyun)
    plugin.RegionId, plugin.custom_endpoint, plugin.collection_task_id = "cn-shenzhen", None, "audit"
    pages = [
        oss.ListBucketsResponseBody(buckets=[oss.Bucket(name="bucket-a")], is_truncated=True, next_marker="next-page"),
        oss.ListBucketsResponseBody(buckets=[oss.Bucket(name="bucket-b")], is_truncated=False),
    ]
    requests = []

    def list_page(request, *_args):
        requests.append(request.marker)
        return SimpleNamespace(body=pages[len(requests) - 1])

    plugin.oss_client = SimpleNamespace(
        list_buckets_with_options=list_page,
        get_bucket_info_with_options=lambda *_args: SimpleNamespace(body=oss.BucketInfo()),
    )
    result = plugin.list_buckets()
    assert result["result"] is True
    assert len(result["data"]) == 2
    assert requests == [None, "next-page"]


@pytest.mark.parametrize("path", ["prometheus", "structured"])
def test_zero_numeric_fields_survive_transport(path):
    data = {"aliyun_kafka_inst": [{"resource_id": "test", "charge_type": 0, "storage_type": 0, "io_max_read": 0}]}
    if path == "prometheus":
        output = convert_to_prometheus_format(data)
        assert 'io_max_read="0"' in output
    else:
        output = convert_structured_metrics_to_influx(StructuredMetricsPayload(data=data), {})[0]
        assert "io_max_read=0" in output


def test_formatter_failure_preserves_other_successful_resources():
    plugin = Aliyun.__new__(Aliyun)
    plugin.RegionId, plugin.custom_endpoint, plugin.collection_task_id = "cn-shenzhen", None, "audit"
    for method in ["list_vms", "list_rds", "list_redis", "list_mongodb", "list_kafka", "list_clb"]:
        setattr(plugin, method, Mock(return_value={"result": True, "data": []}))
    plugin.list_rds = Mock(return_value={"result": True, "data": [{"DBInstanceId": "rds-test", "DBInstanceDescription": "test"}]})
    plugin.list_buckets = Mock(return_value={"result": True, "data": [{"Name": "bucket-test"}]})
    result = plugin._list_all_resources_sync()
    assert result["result"].get("aliyun_mysql"), "A malformed OSS row discarded successful RDS resources"


def test_ecs_requests_only_required_pages():
    plugin = Aliyun.__new__(Aliyun)
    plugin.RegionId, plugin.custom_endpoint, plugin.collection_task_id = "cn-shenzhen", None, "audit"
    request = SimpleNamespace(set_PageSize=Mock(), set_PageNumber=Mock())
    plugin._get_result = Mock(return_value={"TotalCount": 1, "Instances": {"Instance": [{"InstanceId": "i-test"}]}})
    plugin._format_resource_result = Mock(return_value=[])
    plugin._handle_list_request_with_page("vm", request)
    assert plugin._get_result.call_count == 1


@pytest.mark.parametrize("total,pages", [(0, 1), (1, 1), (50, 1), (51, 2), (100, 2), (101, 3)])
def test_ecs_pagination_collects_each_instance_once(total, pages):
    from aliyunsdkecs.request.v20140526.DescribeInstancesRequest import DescribeInstancesRequest

    plugin = Aliyun.__new__(Aliyun)
    seen = []

    def get_page(request, flag):
        assert flag is True
        page = int(request.get_query_params()["PageNumber"])
        seen.append(page)
        return {
            "TotalCount": total,
            "Instances": {"Instance": [{"InstanceId": f"i-{index}"} for index in range((page - 1) * 50, min(page * 50, total))]},
        }

    plugin._get_result = get_page
    plugin._format_resource_result = lambda resource, response: response["Instances"]["Instance"]
    result = plugin._handle_list_request_with_page("vm", DescribeInstancesRequest())
    assert result == {"result": True, "data": [{"InstanceId": f"i-{i}"} for i in range(total)]}
    assert seen == list(range(1, pages + 1))


@pytest.mark.parametrize("markers", [[None], ["same", "same"], ["first", "second", "first"]])
def test_oss_invalid_pagination_fails_instead_of_publishing_incomplete_snapshot(markers):
    plugin = Aliyun.__new__(Aliyun)
    plugin.RegionId, plugin.custom_endpoint, plugin.collection_task_id = "cn-shenzhen", None, "audit"
    responses = [SimpleNamespace(body=oss.ListBucketsResponseBody(buckets=[], is_truncated=True, next_marker=m)) for m in markers]
    list_page = Mock(side_effect=responses)
    plugin.oss_client = SimpleNamespace(list_buckets_with_options=list_page)
    result = plugin.list_buckets()
    assert result == {"result": False, "message": "ValueError('OSS pagination did not advance')"}
    assert list_page.call_count == len(markers)


@pytest.mark.parametrize("zone", ["UTC", "Asia/Shanghai", "America/New_York"])
def test_kafka_timestamp_is_independent_of_collector_timezone(monkeypatch, zone):
    import os
    import time

    original = os.environ.get("TZ")
    try:
        monkeypatch.setenv("TZ", zone)
        time.tzset()
        row = Aliyun.format_aliyun_kafka_inst([{"InstanceId": "kafka-test", "CreateTime": 1704067200000}])[0]
        assert row["create_time"] == "2024-01-01 08:00:00"
        assert row["resource_name"] == "kafka-test"
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


def test_kafka_preserves_zero_status_and_handles_missing_optional_time():
    row = Aliyun.format_aliyun_kafka_inst([{"InstanceId": "kafka-test", "ViewInstanceStatusCode": 0, "ServiceStatus": 5}])[0]
    assert row["status"] == 0
    assert row["create_time"] == ""
    assert Aliyun.format_aliyun_kafka_inst([{"InstanceId": "kafka-test", "ServiceStatus": 5}])[0]["status"] == 5


def test_transport_paths_preserve_scalar_zero_and_false_but_omit_empty_or_nested_values(monkeypatch):
    from tasks.utils import nats_helper

    monkeypatch.setattr("plugins.base_utils.time.time", lambda: 1700000000.123)
    row = {
        "resource_id": "test",
        "integer": 0,
        "float": 0.0,
        "boolean": False,
        "string": "0",
        "empty": "",
        "none": None,
        "list": [],
        "dict": {},
        "quoted": 'a"b\\c',
    }
    data = {"aliyun_kafka_inst": [row]}
    text = convert_to_prometheus_format(data)
    for label in ['integer="0"', 'float="0.0"', 'boolean="False"', 'string="0"']:
        assert label in text
    for field in ["empty", "none", "list", "dict"]:
        assert f"{field}=" not in text
    assert nats_helper.convert_prometheus_to_influx(text, {}) == convert_structured_metrics_to_influx(StructuredMetricsPayload(data=data), {})


def test_format_failure_owns_safe_traceback_and_preserves_other_resources(monkeypatch, caplog, capsys):
    import logging

    import plugins.inputs.aliyun.aliyun_info as module

    secret = "SENTINEL_ALIYUN_FORMAT_PAYLOAD_SECRET"
    original = ValueError(secret)
    plugin = Aliyun.__new__(Aliyun)
    plugin.RegionId, plugin.custom_endpoint, plugin.collection_task_id = "cn-shenzhen", None, "audit"
    for method in ["list_vms", "list_redis", "list_mongodb", "list_kafka", "list_clb"]:
        setattr(plugin, method, Mock(return_value={"result": True, "data": []}))
    plugin.list_rds = Mock(return_value={"result": True, "data": [{"DBInstanceId": "rds-test", "DBInstanceDescription": "test"}]})
    plugin.list_buckets = Mock(return_value={"result": True, "data": [{"Name": secret}]})

    def bad_format(_rows):
        raise original

    plugin.format_bucket_data = bad_format
    test_logger = logging.getLogger("test.aliyun.format_resource")
    monkeypatch.setattr(module, "logger", test_logger)
    with caplog.at_level(logging.ERROR, logger=test_logger.name):
        result = plugin._list_all_resources_sync()
    records = [r for r in caplog.records if r.name == test_logger.name and r.exc_info]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=aliyun_format_resource_failed resource=%s region=%s task_id=%s failed_stage=%s error_type=%s"
    assert record.args == ("aliyun_bucket", "cn-shenzhen", "audit", "format_metrics", "ValueError")
    rendered = logging.Formatter().format(record)
    assert "task_id=audit failed_stage=format_metrics error_type=ValueError" in rendered
    assert record.exc_info[2] is original.__traceback__
    assert record.exc_info[1] is not original
    assert original.args == (secret,)
    assert result["success"] is True
    assert result["result"]["aliyun_mysql"][0]["resource_id"] == "rds-test"
    assert result["result"]["aliyun_bucket"] == [{"collect_status": "failed", "cmdb_collect_error": "format_metrics failed: ValueError"}]
    assert secret not in rendered + repr(record.args) + repr(result) + capsys.readouterr().out
