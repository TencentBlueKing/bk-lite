"""阿里云配置采集回归：真实 SDK 响应模型、分页和传输边界，无外部 IO。"""
import json
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


def _ecs_source(**extra):
    source = {
        "resource_name": "ecs",
        "resource_id": "i-1",
        "inner_ip": ["10.0.0.8"],
        "public_ip": [],
        "region": "cn-guangzhou",
        "zone": "cn-guangzhou-a",
        "vpc": "vpc-1",
        "status": "Running",
        "instance_type": "ecs.g6",
        "os_name": "linux",
        "vcpus": 2,
        "memory": 4096,
        "charge_type": "PostPaid",
        "create_time": "",
        "expired_time": "",
    }
    source.update(extra)
    return source


def test_ecs_collects_system_tags_empty_values_and_drops_newlines(monkeypatch, caplog):
    import logging

    import plugins.inputs.aliyun.aliyun_info as module

    secret = "SENTINEL_ALIYUN_TAG_VALUE"
    test_logger = logging.getLogger("test.aliyun.tag")
    monkeypatch.setattr(module, "logger", test_logger)
    with caplog.at_level(logging.WARNING, logger=test_logger.name):
        row = Aliyun.format_ecs_data(
            [
                _ecs_source(
                    tag=[
                        {"TagKey": "env", "TagValue": "prod"},
                        {"TagKey": "acs:rm:rgId", "TagValue": secret},
                        {"TagKey": "team", "TagValue": "net"},
                        {"TagKey": "blank", "TagValue": ""},
                        {"TagKey": "bad", "TagValue": "a\nb"},
                    ]
                )
            ]
        )[0]
    assert row["tag"] == ["env:prod", f"acs%3Arm%3ArgId:{secret}", "team:net", "blank:"]
    assert row["ip_addr"] == "10.0.0.8"
    records = [record for record in caplog.records if record.name == test_logger.name]
    assert len(records) == 1
    assert records[0].msg == "event=aliyun_tag_normalized skipped=%s truncated=%s"
    assert records[0].args == (1, 0)
    rendered = records[0].getMessage()
    assert secret not in rendered
    assert secret not in repr(records[0].args)
    assert "tag" not in Aliyun.format_ecs_data([_ecs_source()])[0]
    assert Aliyun.format_ecs_data([_ecs_source(tag=[])])[0]["tag"] == []


@pytest.mark.parametrize(
    "formatter,source,expected",
    [
        (
            Aliyun.format_aliyun_clb,
            {
                "LoadBalancerId": "lb-1",
                "LoadBalancerName": "lb",
                "CreateTime": "2024-01-01T00:00Z",
                "Tags": {"Tag": [{"TagKey": "env", "TagValue": "prod"}]},
            },
            ["env:prod"],
        ),
        (
            Aliyun.format_aliyun_redis,
            {
                "InstanceId": "r-1",
                "InstanceName": "redis",
                "RegionId": "cn-guangzhou",
                "ZoneId": "cn-guangzhou-a",
                "EngineVersion": "5.0",
                "ArchitectureType": "cluster",
                "Capacity": 1024,
                "NetworkType": "VPC",
                "ConnectionDomain": "r-1.redis.rds.aliyuncs.com",
                "Port": 6379,
                "Bandwidth": 10,
                "QPS": 1000,
                "InstanceClass": "redis.master.small.default",
                "PackageType": "standard",
                "ChargeType": "PostPaid",
                "Tags": {"Tag": [{"Key": "cache", "Value": "hot"}]},
            },
            ["cache:hot"],
        ),
        (
            Aliyun.format_aliyun_mongodb,
            {"DBInstanceId": "dds-1", "Tags": {"Tag": [{"Key": "db", "Value": "mongo"}]}},
            ["db:mongo"],
        ),
        (
            Aliyun.format_aliyun_kafka_inst,
            {"InstanceId": "alikafka-1", "Tags": {"TagVO": [{"Key": "mq", "Value": "core"}]}},
            ["mq:core"],
        ),
        (
            Aliyun.format_aliyun_mysql,
            {"DBInstanceId": "rm-1", "Tags": {"Tag": [{"TagKey": "db", "TagValue": "mysql"}]}},
            ["db:mysql"],
        ),
    ],
)
def test_aliyun_resource_formatters_keep_native_tag_shapes(formatter, source, expected):
    assert formatter([source])[0]["tag"] == expected
    bare = {key: value for key, value in source.items() if key != "Tags"}
    assert "tag" not in formatter([bare])[0]


def test_list_rds_attaches_tags_across_pages_and_survives_tag_api_failure(monkeypatch, caplog):
    import logging

    import plugins.inputs.aliyun.aliyun_info as module
    from alibabacloud_rds20140815 import models as rds
    from Tea.exceptions import TeaException

    plugin = Aliyun.__new__(Aliyun)
    plugin.RegionId, plugin.custom_endpoint, plugin.collection_task_id = "cn-guangzhou", None, "audit"
    secret = "SENTINEL_RDS_TAG_ERROR"
    described = {"count": 0}

    def describe(_request, _runtime):
        described["count"] += 1
        if described["count"] == 1:
            body = rds.DescribeDBInstancesResponseBody(
                items=rds.DescribeDBInstancesResponseBodyItems(
                    dbinstance=[rds.DescribeDBInstancesResponseBodyItemsDBInstance(dbinstance_id="rm-1", pay_type="Postpaid")]
                )
            )
        else:
            body = rds.DescribeDBInstancesResponseBody()
        return SimpleNamespace(body=body)

    tag_requests = []

    def list_tags(request, _runtime):
        tag_requests.append(request.resource_id)
        if request.next_token:
            body = rds.ListTagResourcesResponseBody(
                tag_resources=rds.ListTagResourcesResponseBodyTagResources(
                    tag_resource=[rds.ListTagResourcesResponseBodyTagResourcesTagResource(resource_id="rm-1", tag_key="team", tag_value="net")]
                )
            )
        else:
            body = rds.ListTagResourcesResponseBody(
                next_token="page-2",
                tag_resources=rds.ListTagResourcesResponseBodyTagResources(
                    tag_resource=[rds.ListTagResourcesResponseBodyTagResourcesTagResource(resource_id="rm-1", tag_key="env", tag_value="prod")]
                ),
            )
        return SimpleNamespace(body=body)

    plugin.rds_client = SimpleNamespace(
        describe_dbinstances_with_options=describe,
        list_tag_resources_with_options=list_tags,
    )
    result = plugin.list_rds(engine="MySQL")
    assert result["result"] is True
    assert result["data"][0]["Tags"]["Tag"] == [
        {"TagKey": "env", "TagValue": "prod"},
        {"TagKey": "team", "TagValue": "net"},
    ]
    assert tag_requests == [["rm-1"], ["rm-1"]]
    assert Aliyun.format_aliyun_mysql(result["data"])[0]["tag"] == ["env:prod", "team:net"]

    def deny(_request, _runtime):
        raise TeaException({"code": "AccessDenied", "message": secret, "data": {}})

    described["count"] = 0
    plugin.rds_client.list_tag_resources_with_options = deny
    test_logger = logging.getLogger("test.aliyun.rds.tag")
    monkeypatch.setattr(module, "logger", test_logger)
    with caplog.at_level(logging.WARNING, logger=test_logger.name):
        failed = plugin.list_rds(engine="MySQL")
    assert failed["result"] is True
    assert "Tags" not in failed["data"][0]
    records = [record for record in caplog.records if record.name == test_logger.name]
    assert records[-1].msg == "event=aliyun_rds_tag_skipped host=%s region=%s task_id=%s failed_stage=%s error_type=%s"
    assert records[-1].args == (None, "cn-guangzhou", "audit", "list_tag_resources", "TeaException")
    rendered = records[-1].getMessage()
    assert secret not in rendered + repr(records[-1].args)


def test_list_buckets_reads_tags_and_skips_tag_errors_without_dropping_buckets(monkeypatch, caplog):
    import logging

    import plugins.inputs.aliyun.aliyun_info as module
    from alibabacloud_oss20190517 import models as oss
    from Tea.exceptions import TeaException

    plugin = Aliyun.__new__(Aliyun)
    plugin.RegionId, plugin.custom_endpoint, plugin.collection_task_id = "cn-guangzhou", None, "audit"
    secret = "SENTINEL_OSS_TAG_ERROR"
    pages = {
        "tagged": oss.GetBucketTagsResponseBody(tag_set=oss.TagSet(tags=[oss.Tag(key="env", value="prod")])),
    }

    def list_page(_request, *_args):
        return SimpleNamespace(
            body=oss.ListBucketsResponseBody(
                buckets=[oss.Bucket(name="tagged"), oss.Bucket(name="empty"), oss.Bucket(name="broken")],
                is_truncated=False,
            )
        )

    def bucket_tags(bucket_name, *_args):
        if bucket_name == "broken":
            raise TeaException({"code": "AccessDenied", "message": secret, "data": {}})
        if bucket_name == "empty":
            raise TeaException({"code": "NoSuchTagSet", "message": "no tags", "data": {}})
        return SimpleNamespace(body=pages["tagged"])

    def bucket_info(bucket_name, *_args):
        return SimpleNamespace(
            body=oss.BucketInfo(
                bucket=oss.BucketInfoBucket(
                    name=bucket_name,
                    location="oss-cn-guangzhou",
                    extranet_endpoint="oss-cn-guangzhou.aliyuncs.com",
                    intranet_endpoint="oss-cn-guangzhou-internal.aliyuncs.com",
                    storage_class="Standard",
                    cross_region_replication="Disabled",
                    creation_date="2024-01-01T00:00:00.000Z",
                )
            )
        )

    plugin.oss_client = SimpleNamespace(
        list_buckets_with_options=list_page,
        get_bucket_info_with_options=bucket_info,
        get_bucket_tags_with_options=bucket_tags,
    )
    test_logger = logging.getLogger("test.aliyun.bucket.tag")
    monkeypatch.setattr(module, "logger", test_logger)
    with caplog.at_level(logging.WARNING, logger=test_logger.name):
        result = plugin.list_buckets()
    assert result["result"] is True
    by_name = {item["Name"]: item for item in result["data"]}
    assert by_name["tagged"]["Tags"] == {"Tag": [{"Key": "env", "Value": "prod"}]}
    assert by_name["empty"]["Tags"] == {"Tag": []}
    assert "Tags" not in by_name["broken"]
    assert Aliyun.format_bucket_data([by_name["tagged"]])[0]["tag"] == ["env:prod"]
    records = [record for record in caplog.records if record.name == test_logger.name]
    assert records[0].msg == ("event=aliyun_bucket_tag_skipped host=%s region=%s task_id=%s bucket=%s failed_stage=%s error_type=%s")
    assert records[0].args == (None, "cn-guangzhou", "audit", "broken", "get_bucket_tags", "TeaException")
    assert secret not in records[0].getMessage() + repr(records[0].args)


def test_aliyun_ecs_tag_survives_prometheus_transport():
    from urllib.parse import unquote

    tags = ["owner:acme,inc", "env:prod"]
    text = convert_to_prometheus_format({"aliyun_ecs": [Aliyun.format_ecs_data([_ecs_source(tag=tags)])[0]]})
    marker = 'tag="'
    start = text.index(marker) + len(marker)
    encoded = text[start : text.index('"', start)]
    assert json.loads(unquote(encoded)) == tags
    empty = convert_to_prometheus_format({"aliyun_ecs": [Aliyun.format_ecs_data([_ecs_source(tag=[])])[0]]})
    empty_start = empty.index(marker) + len(marker)
    assert json.loads(unquote(empty[empty_start : empty.index('"', empty_start)])) == []


def test_service_tags_replace_product_tags_and_failure_omits_them(monkeypatch, caplog):
    import logging

    import plugins.inputs.aliyun.aliyun_info as module

    plugin = Aliyun.__new__(Aliyun)
    plugin.RegionId = "cn-guangzhou"
    plugin.custom_endpoint = None
    plugin.collection_task_id = "audit"
    plugin.auth_config = object()
    secret = "SENTINEL_TAG_SERVICE"
    items = [{"resource_id": "i-1", "tag": ["env:prod"]}, {"resource_id": "i-2", "tag": []}]

    def found(_kind, _region, _ids):
        return {"i-1": [("acs:rm:rgId", secret), ("env", "prod")]}

    plugin._list_service_tags = found
    plugin._overlay_service_tags(items, "ecs", "resource_id")
    assert items[0]["tag"] == [{"TagKey": "acs:rm:rgId", "TagValue": secret}, {"TagKey": "env", "TagValue": "prod"}]
    assert items[1]["tag"] == []
    assert module._serialize_aliyun_tags(items[0]["tag"]) == [f"acs%3Arm%3ArgId:{secret}", "env:prod"]
    assert module._serialize_aliyun_tags(items[1]["tag"]) == []

    plugin._list_service_tags = lambda *_args: None
    test_logger = logging.getLogger("test.aliyun.tag.service")
    monkeypatch.setattr(module, "logger", test_logger)
    failed = [{"resource_id": "i-1", "tag": ["env:prod"]}]
    with caplog.at_level(logging.WARNING, logger=test_logger.name):
        plugin._overlay_service_tags(failed, "ecs", "resource_id")
    assert "tag" not in failed[0]
    assert secret not in caplog.text


def test_tag_service_failure_logs_stage_without_payload(monkeypatch, caplog):
    import logging

    import plugins.inputs.aliyun.aliyun_info as module

    secret = "SENTINEL_TAG_SERVICE_BODY"
    plugin = Aliyun.__new__(Aliyun)
    plugin.RegionId = "cn-guangzhou"
    plugin.custom_endpoint = None
    plugin.collection_task_id = "audit"
    plugin._cached_account_id = "100"

    def boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    plugin._openapi_call = boom
    test_logger = logging.getLogger("test.aliyun.tag.service.fail")
    monkeypatch.setattr(module, "logger", test_logger)
    with caplog.at_level(logging.WARNING, logger=test_logger.name):
        assert plugin._list_service_tags("ecs", "cn-guangzhou", ["i-1"]) is None
    records = [record for record in caplog.records if record.name == test_logger.name]
    assert records[-1].msg == "event=aliyun_tag_service_skipped host=%s region=%s task_id=%s failed_stage=%s error_type=%s"
    assert records[-1].args == (None, "cn-guangzhou", "audit", "list_tag_resources", "RuntimeError")
    rendered = records[-1].getMessage()
    assert secret not in rendered
    assert secret not in repr(records[-1].args)
