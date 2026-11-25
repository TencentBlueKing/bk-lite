# -*- coding: utf-8 -*-
"""火山引擎清单客户端：分页、权限、限流和 TOS 过滤不访问公网。"""
import json

import pytest
from plugins.inputs.volcengine.client import VolcengineApiError, VolcengineClient
from plugins.inputs.volcengine.volcengine_info import CwVolcengine

SECRET = "SK-SENTINEL-volcengine"


def _client(transport, region="cn-beijing", **kwargs):
    return VolcengineClient(
        "AK-SENTINEL",
        SECRET,
        region,
        transport=transport,
        sleeper=kwargs.pop("sleeper", lambda _seconds: None),
        **kwargs,
    )


def test_ecs_pages_follow_next_token():
    seen = []

    def transport(method, url, headers, body):
        payload = json.loads(body)
        seen.append(payload)
        if "NextToken" not in payload:
            return 200, {"Result": {"Instances": [{"InstanceId": "i-1"}], "NextToken": "n2"}}
        return 200, {"Result": {"Instances": [{"InstanceId": "i-2"}], "NextToken": ""}}

    rows = _client(transport).describe_instances()

    assert [row["InstanceId"] for row in rows] == ["i-1", "i-2"]
    assert seen[0]["MaxResults"] == 100
    assert seen[1]["NextToken"] == "n2"


def test_signature_header_does_not_carry_the_secret():
    captured = {}

    def transport(method, url, headers, body):
        captured.update(headers=headers, url=url, body=body)
        return 200, {"Result": {"Regions": [{"RegionId": "cn-beijing"}], "NextToken": ""}}

    assert _client(transport).describe_regions()[0]["RegionId"] == "cn-beijing"
    authorization = captured["headers"]["Authorization"]
    assert authorization.startswith("HMAC-SHA256 ")
    assert SECRET not in authorization
    assert SECRET not in captured["url"]
    assert SECRET.encode() not in captured["body"]
    assert captured["headers"]["Host"] == "ecs.cn-beijing.volcengineapi.com"


def test_access_denied_is_not_an_empty_list():
    def transport(method, url, headers, body):
        return 403, {"ResponseMetadata": {"Error": {"Code": "AccessDenied", "Message": f"denied {SECRET}"}}}

    with pytest.raises(VolcengineApiError) as raised:
        _client(transport).describe_instances()
    assert raised.value.code == "AccessDenied"
    assert SECRET not in str(raised.value)


def test_flow_limit_retries_then_returns_rows():
    calls = {"count": 0}
    sleeps = []

    def transport(method, url, headers, body):
        calls["count"] += 1
        if calls["count"] == 1:
            return 429, {"ResponseMetadata": {"Error": {"Code": "FlowLimitExceeded", "Message": "slow"}}}
        return 200, {"Result": {"Instances": [{"InstanceId": "i-1"}], "NextToken": ""}}

    rows = _client(transport, sleeper=lambda seconds: sleeps.append(seconds)).describe_instances()

    assert [row["InstanceId"] for row in rows] == ["i-1"]
    assert calls["count"] == 2
    assert sleeps == [0.2]


def test_postgresql_task_id_is_not_an_empty_list():
    def transport(method, url, headers, body):
        return 200, {"Result": {"TaskId": "task-1"}}

    with pytest.raises(VolcengineApiError) as raised:
        _client(transport).describe_postgresql()
    assert raised.value.code == "AsyncTask"


def test_truncated_token_loop_fails():
    def transport(method, url, headers, body):
        return 200, {"Result": {"Instances": [{"InstanceId": "i-1"}], "NextToken": "same"}}

    with pytest.raises(VolcengineApiError) as raised:
        _client(transport).describe_instances()
    assert raised.value.code == "Truncated"


def test_tos_parser_keeps_location_and_stops_on_truncated_marker():
    xml = """<?xml version="1.0"?>
    <ListAllMyBucketsResult>
      <Buckets>
        <Bucket>
          <Name>keep-bucket</Name>
          <Location>cn-beijing</Location>
          <ExtranetEndpoint>keep.tos-cn-beijing.volces.com</ExtranetEndpoint>
          <IntranetEndpoint>keep.tos-cn-beijing.ivolces.com</IntranetEndpoint>
          <BucketType>fns</BucketType>
          <CreationDate>2024-01-02T03:04:05.000Z</CreationDate>
        </Bucket>
        <Bucket><Name>other-bucket</Name><Location>cn-shanghai</Location></Bucket>
      </Buckets>
      <IsTruncated>true</IsTruncated>
    </ListAllMyBucketsResult>
    """

    def transport(method, url, headers, body):
        return 200, xml

    with pytest.raises(VolcengineApiError) as raised:
        _client(transport).list_buckets()
    assert raised.value.code == "Truncated"


def test_collector_filters_other_region_buckets_and_isolates_product_errors():
    class FakeClient:
        def describe_instances(self):
            raise VolcengineApiError("AccessDenied", "no ecs")

        def describe_load_balancers(self):
            return []

        def describe_eips(self):
            return []

        def describe_mysql(self):
            return []

        def describe_postgresql(self):
            raise VolcengineApiError("AsyncTask", "instance list missing")

        def list_buckets(self):
            return [
                {"Name": "keep-bucket", "Location": "cn-beijing", "BucketType": "fns"},
                {"Name": "other-bucket", "Location": "cn-shanghai"},
            ]

    manager = CwVolcengine({"accessKey": "AK", "accessSecret": SECRET, "region": "cn-beijing"}, client=FakeClient())
    result = manager._list_all_resources_sync()

    assert result["success"] is True
    assert result["result"]["volcengine_ecs"][0]["collect_status"] == "failed"
    assert result["result"]["volcengine_ecs"][0]["region"] == "cn-beijing"
    assert "resource_id" not in result["result"]["volcengine_ecs"][0]
    assert result["result"]["volcengine_tos"] == [
        {
            "resource_id": "keep-bucket",
            "resource_name": "keep-bucket",
            "region": "cn-beijing",
            "tag": [],
            "location": "cn-beijing",
            "extranet_endpoint": "",
            "intranet_endpoint": "",
            "bucket_type": "fns",
            "creation_date": "",
        }
    ]
    assert SECRET not in json.dumps(result)


def test_custom_endpoint_replaces_openapi_and_tos_hosts():
    seen = []

    def transport(method, url, headers, body):
        seen.append((headers.get("Host"), url))
        if method == "GET":
            return 200, "<ListAllMyBucketsResult></ListAllMyBucketsResult>"
        return 200, {"Result": {"Instances": []}}

    client = _client(transport, endpoint="https://openapi.example.com")
    assert client.describe_instances() == []
    assert client.list_buckets() == []
    assert seen[0][0] == "openapi.example.com"
    assert seen[0][1].startswith("https://openapi.example.com/")
    assert seen[1][0] == "openapi.example.com"
    assert seen[1][1].startswith("https://openapi.example.com/")


def test_transport_rejects_an_unbounded_body(monkeypatch):
    from plugins.inputs.volcengine import client as client_module

    class _Body:
        status = 200

        def read(self, _size=-1):
            return b"x" * (_size if _size and _size > 0 else client_module._MAX_BODY + 1)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(client_module.urllib.request, "urlopen", lambda *_args, **_kwargs: _Body())
    with pytest.raises(VolcengineApiError) as caught:
        client_module._urllib_transport("GET", "https://example.invalid/", {}, b"")
    assert caught.value.code == "ResponseTooLarge"
    assert SECRET not in str(caught.value)


def test_one_product_failure_keeps_other_products_and_owns_one_traceback():
    import logging
    import traceback

    from core.logger import logger

    class FakeClient:
        def describe_instances(self):
            raise RuntimeError(SECRET)

        def describe_load_balancers(self):
            return [{"LoadBalancerId": "clb-1", "LoadBalancerName": "lb"}]

        def describe_eips(self):
            return [
                {"AllocationId": "eip-ok", "Name": "eip", "EipAddress": "1.1.1.1"},
                {"AllocationId": "eip-bad", "Tags": 1},
            ]

        def describe_mysql(self):
            return [{"InstanceName": "nameless"}]

        def describe_postgresql(self):
            return []

        def list_buckets(self):
            return []

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    logger.addHandler(handler)
    previous = logger.level
    logger.setLevel(logging.INFO)
    try:
        result = CwVolcengine({"region": "cn-beijing\nforged"}, client=FakeClient())._list_all_resources_sync()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)

    errors = [record for record in records if record.levelno >= logging.ERROR]
    assert len(errors) == 3
    template = "event=volcengine_product_failed region=%s product=%s resource_id=%s failed_stage=list error_type=%s error_code=%s"
    rendered = []
    for record in errors:
        assert record.msg == template
        assert record.args[1] in {"volcengine_ecs", "volcengine_eip", "volcengine_mysql"}
        assert "\n" not in record.getMessage()
        assert record.exc_info[2] is not None
        rendered.append(record.getMessage())
        rendered.append("".join(traceback.format_exception(*record.exc_info)))
    assert SECRET not in "\n".join(rendered)
    ecs = result["result"]["volcengine_ecs"][0]
    assert ecs["collect_status"] == "failed"
    assert ecs["cmdb_collect_error"] == "RuntimeError"
    assert ecs["product"] == "volcengine_ecs"
    assert "resource_id" not in ecs
    assert result["result"]["volcengine_clb"][0]["resource_id"] == "clb-1"
    failed_eip = next(row for row in result["result"]["volcengine_eip"] if row.get("collect_status") == "failed")
    assert failed_eip["resource_id"] == "eip-bad"
    assert failed_eip["product"] == "volcengine_eip"
    assert any(row.get("resource_id") == "eip-ok" for row in result["result"]["volcengine_eip"])
    mysql = result["result"]["volcengine_mysql"][0]
    assert mysql["cmdb_collect_error"] == "InvalidResource"
    assert "resource_id" not in mysql
    assert result["success"] is True
