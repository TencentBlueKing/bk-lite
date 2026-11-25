# -*- coding: utf-8 -*-
"""火山引擎模型契约，以及 mock 云和本地 VM 上的采集入库链路。"""
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from apps.cmdb.collection.metrics_cannula import MetricsCannula, collection_match_keys
from apps.cmdb.collection.plugins.community.cloud.volcengine import VolcengineAccountCollectionPlugin
from apps.cmdb.constants.constants import DataCleanupStrategy
from apps.cmdb.constants.monitor_link import CMDB_MODEL_TO_MONITOR_OBJECT
from apps.cmdb.models import CollectModels
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.services.app_topo_layer import default_app_topo_layer
from apps.cmdb.tests.test_vmware_collection_ownership_service import Graph
from apps.module_link.constants import is_platform_tree_model

REPO = Path(__file__).resolve().parents[4]
XLSX = Path(__file__).resolve().parents[1] / "support-files" / "model_config.xlsx"
SECRET = "SK-SENTINEL-volcengine"
ACCOUNT = "火山账号"
OLD = "2026-08-24T04:00:00+00:00"
CHAIN_SCRIPT = r"""
import json
import sys

from plugins.base_utils import convert_to_prometheus_format
from plugins.inputs.volcengine.volcengine_info import CwVolcengine
from service.collection_service import CollectionService
from tasks.utils.nats_helper import convert_prometheus_to_influx

params = json.load(sys.stdin)
task_id = params.pop("task_id")
collected = CwVolcengine(params)._list_all_resources_sync()
processed = CollectionService({"model_id": "volcengine", "plugin_name": "volcengine_info"})._process_result(collected)
text = convert_to_prometheus_format(processed)
lines = convert_prometheus_to_influx(
    text,
    {
        "tags": {"instance_id": "cmdb_%s" % task_id, "collect_type": "http"},
        "host": "node-1",
        "plugin_name": "volcengine_info",
    },
)
json.dump({"prometheus": text, "influx": lines}, sys.stdout)
"""


def test_volcengine_models_are_configuration_only():
    import openpyxl

    workbook = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    classifications = {row[0] for row in workbook["classifications"].iter_rows(min_row=3, values_only=True) if row[0]}
    assert "volcengine" in classifications
    models = {}
    for row in workbook["models"].iter_rows(min_row=3, values_only=True):
        if row[0] and str(row[0]).startswith("volcengine"):
            models[row[0]] = {"name": row[1], "classification_id": row[3], "app_topo_layer": row[4]}
    assert set(models) == {
        "volcengine_account",
        "volcengine_ecs",
        "volcengine_eip",
        "volcengine_clb",
        "volcengine_mysql",
        "volcengine_pgsql",
        "volcengine_tos",
    }
    assert models["volcengine_account"]["app_topo_layer"] == "none"
    assert models["volcengine_ecs"]["app_topo_layer"] == "host"
    assert models["volcengine_mysql"]["app_topo_layer"] == "appService"
    assert models["volcengine_pgsql"]["app_topo_layer"] == "appService"
    assert default_app_topo_layer("volcengine_ecs", "volcengine") == "host"
    assert default_app_topo_layer("volcengine_mysql", "volcengine") == "appService"
    assert default_app_topo_layer("volcengine_eip", "volcengine") == "none"

    def attrs(sheet):
        rows = list(workbook[sheet].iter_rows(min_row=3, values_only=True))
        headers = list(workbook[sheet].iter_rows(min_row=2, max_row=2, values_only=True))[0]
        return {row[0]: dict(zip(headers, row)) for row in rows if row[0]}

    account = attrs("attr-volcengine_account")
    assert account["inst_name"]["is_only"] is True
    assert "resource_id" not in account
    ecs = attrs("attr-volcengine_ecs")
    assert ecs["inst_name"]["is_only"] is True
    assert ecs["resource_id"]["is_only"] is True
    eip_asso = list(workbook["asso-volcengine_eip"].iter_rows(min_row=3, values_only=True))
    assert ("volcengine_eip", "volcengine_account", "belong", "n:1", True) in eip_asso
    assert ("volcengine_eip", "volcengine_ecs", "connect", "n:n", False) in eip_asso
    assert ("volcengine_eip", "volcengine_clb", "connect", "n:n", False) in eip_asso
    for model_id in models:
        assert model_id not in CMDB_MODEL_TO_MONITOR_OBJECT
        if model_id != "volcengine_account":
            assert is_platform_tree_model(model_id)
    assert collection_match_keys("volcengine_ecs") == ["resource_id"]
    assert collection_match_keys("volcengine_account") == ["inst_name"]
    assert collection_match_keys("aliyun_ecs") == ["inst_name"]
    assert VolcengineAccountCollectionPlugin.supported_model_id == "volcengine_account"


def test_format_names_resources_and_blocks_cleanup_after_a_product_error():
    task = type("Task", (), {"model_id": "volcengine_account", "_sync_snapshot_complete": True})()
    runner = VolcengineAccountCollectionPlugin(ACCOUNT, 1, 7, collect_inst=task)
    runner.raw_data = [
        {"metric": {"__name__": "volcengine_mysql_info_gauge", "collect_status": "failed", "cmdb_collect_error": "AccessDenied"}},
    ]
    runner.format_data(
        {
            "result": [
                _metric(
                    "volcengine_ecs_info_gauge",
                    resource_name="web",
                    resource_id="i-web",
                    region="cn-beijing",
                    status="RUNNING",
                    vcpus="2",
                    memory_mb="4096",
                    create_time="2024-01-02 03:04:05",
                    expired_time="",
                    tag="%5B%22env%3Dprod%22%5D",
                ),
                _metric(
                    "volcengine_clb_info_gauge",
                    resource_name="clb",
                    resource_id="clb-1",
                    charge_type="1",
                    create_time="2024-01-02 03:04:05",
                ),
                _metric(
                    "volcengine_eip_info_gauge",
                    resource_name="eip",
                    resource_id="eip-1",
                    bind_instance_type="EcsInstance",
                    bind_instance_id="i-web",
                    bandwidth="10",
                ),
            ]
        }
    )
    runner.format_metrics()

    ecs = runner.result["volcengine_ecs"][0]
    assert ecs["inst_name"] == "web(i-web)"
    assert ecs["status"] == "RUNNING"
    assert ecs["vcpus"] == 2
    assert ecs["memory_mb"] == 4096
    assert ecs["assos"][0]["model_asst_id"] == "volcengine_ecs_belong_volcengine_account"
    assert runner.result["volcengine_clb"][0]["charge_type"] == "1"
    eip_edges = runner.result["volcengine_eip"][0]["assos"]
    assert eip_edges[1]["inst_name"] == "web(i-web)"
    assert eip_edges[1]["model_asst_id"] == "volcengine_eip_connect_volcengine_ecs"
    assert runner.snapshot_complete is False


def test_missing_identity_and_failed_samples_do_not_become_assets():
    task = type("Task", (), {"model_id": "volcengine_account", "_sync_snapshot_complete": True})()
    runner = VolcengineAccountCollectionPlugin(ACCOUNT, 1, 7, collect_inst=task)
    runner.format_data(
        {
            "result": [
                _metric("volcengine_ecs_info_gauge", resource_name="web", resource_id="i-web"),
                _metric("volcengine_ecs_info_gauge", resource_name="", resource_id=""),
                _metric(
                    "volcengine_eip_info_gauge",
                    resource_name="eip",
                    resource_id="eip-bad",
                    collect_status="failed",
                    cmdb_collect_error="TypeError",
                    product="volcengine_eip",
                ),
            ]
        }
    )
    runner.format_metrics()

    assert [row["resource_id"] for row in runner.result["volcengine_ecs"]] == ["i-web"]
    assert runner.result["volcengine_eip"] == []
    assert runner.snapshot_complete is False


def _metric(name, **labels):
    now = time.time()
    metric = {"__name__": name, "instance_id": "cmdb_7", "collect_status": "success", "resource_name": labels.get("resource_name", "named")}
    metric.update(labels)
    return {"metric": metric, "value": [now, "1"]}


class _Server:
    def __init__(self, handler):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        host, port = self.httpd.server_address
        return f"http://{host}:{port}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _start_cloud(state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._reply(200, _tos_xml().encode(), "application/xml")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            action = parse_qs(urlparse(self.path).query).get("Action", [""])[0]
            service = _signed_service(self.headers.get("Authorization"))
            self._reply(200, json.dumps(_cloud_body(state, action, body, service)).encode(), "application/json")

        def _reply(self, status, payload, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            return

    return _Server(Handler)


def _start_vm(samples):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            query = parse_qs(self.rfile.read(length).decode()).get("query", [""])[0]
            result = [row for row in samples if row["metric"]["__name__"] in query and row["metric"].get("instance_id", "") in query]
            payload = json.dumps({"status": "success", "data": {"resultType": "vector", "result": result}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            return

    return _Server(Handler)


def _signed_service(authorization):
    credential = str(authorization or "").split("Credential=", 1)
    if len(credential) < 2:
        return ""
    scope = credential[1].split(",", 1)[0].split("/")
    return scope[3] if len(scope) > 3 else ""


def _cloud_body(state, action, body, service):
    if action == "DescribeInstances" and state["phase"] == "ecs-failed":
        return {"ResponseMetadata": {"Error": {"Code": "AccessDenied", "Message": "no ecs"}}}
    if action == "DescribeDBInstances":
        rows = [_pgsql()] if service == "rds-postgresql" else [_mysql()]
        return {"Result": {"Instances": rows, "TotalCount": len(rows)}}
    if action == "DescribeInstances":
        rows = _ecs(state)
        if body.get("NextToken") == "page-2":
            return {"Result": {"Instances": rows[1:], "NextToken": ""}}
        return {"Result": {"Instances": rows[:1], "NextToken": "page-2"}}
    if action == "DescribeEipAddresses":
        return {"Result": {"EipAddresses": [_eip(state)], "NextToken": ""}}
    if action == "DescribeLoadBalancers":
        return {"Result": {"LoadBalancers": [_clb()], "TotalCount": 1}}
    return {"ResponseMetadata": {"Error": {"Code": "UnknownAction", "Message": action}}}


def _ecs(state):
    name = "web-renamed" if state["phase"] == "rename" else "web"
    return [
        {
            "InstanceId": "i-web",
            "InstanceName": name,
            "Status": "RUNNING",
            "InstanceChargeType": "PostPaid",
            "ZoneId": "cn-beijing-a",
            "VpcId": "vpc-1",
            "InstanceTypeId": "ecs.g3i.large",
            "OsName": "Ubuntu",
            "Cpus": 2,
            "MemorySize": 4096,
            "CreatedAt": "2024-01-02T03:04:05Z",
            "ExpiredAt": "2025-01-02T03:04:05Z",
            "NetworkInterfaces": [{"Type": "primary", "PrimaryIpAddress": "10.0.0.8"}],
            "EipAddress": {"IpAddress": "1.2.3.4"},
            "Tags": [{"Key": "env", "Value": "prod"}],
        },
        {
            "InstanceId": "i-db",
            "InstanceName": "db",
            "Status": "STOPPED",
            "Cpus": 1,
            "MemorySize": 2048,
            "NetworkInterfaces": [{"Type": "primary", "PrimaryIpAddress": "10.0.0.9"}],
        },
    ]


def _eip(state):
    rebound = state["phase"] == "rename"
    return {
        "AllocationId": "eip-1",
        "Name": "eip",
        "EipAddress": "1.2.3.4",
        "Status": "Attached",
        "Bandwidth": 10,
        "InstanceType": "ClbInstance" if rebound else "EcsInstance",
        "InstanceId": "clb-1" if rebound else "i-web",
        "Tags": [],
    }


def _clb():
    return {
        "LoadBalancerId": "clb-1",
        "LoadBalancerName": "clb",
        "VpcId": "vpc-1",
        "Address": "10.0.1.8",
        "EipAddress": "1.2.3.5",
        "Status": "Active",
        "Type": "public",
        "LoadBalancerBillingType": 1,
        "CreateTime": "2024-01-02T03:04:05Z",
    }


def _mysql():
    return {
        "InstanceId": "mysql-1",
        "InstanceName": "mysql",
        "ZoneId": "cn-beijing-a",
        "VpcId": "vpc-1",
        "DBEngineVersion": "MySQL_8_0",
        "InstanceStatus": "Running",
        "StorageSpace": 100,
        "StorageType": "LocalSSD",
        "ChargeType": "PostPaid",
        "CreateTime": "2024-01-02T03:04:05Z",
        "AddressObject": [{"EipType": "Private", "IPAddress": "10.0.2.8", "Port": "3306"}],
    }


def _pgsql():
    row = _mysql()
    row.update(
        InstanceId="pg-1",
        InstanceName="pg",
        DBEngineVersion="PostgreSQL_14",
        AddressObject=[{"EipType": "Private", "IPAddress": "10.0.2.9", "Port": "5432"}],
    )
    return row


def _tos_xml():
    return """<?xml version="1.0"?>
<ListAllMyBucketsResult>
  <Buckets>
    <Bucket>
      <Name>keep-bucket</Name><Location>cn-beijing</Location>
      <ExtranetEndpoint>keep.tos-cn-beijing.volces.com</ExtranetEndpoint>
      <IntranetEndpoint>keep.tos-cn-beijing.ivolces.com</IntranetEndpoint>
      <BucketType>fns</BucketType><CreationDate>2024-01-02T03:04:05.000Z</CreationDate>
    </Bucket>
    <Bucket><Name>other-bucket</Name><Location>cn-shanghai</Location></Bucket>
  </Buckets>
  <IsTruncated>false</IsTruncated>
</ListAllMyBucketsResult>
"""


def _collect(cloud_url, task_id):
    completed = subprocess.run(
        ["uv", "run", "python", "-c", CHAIN_SCRIPT],
        cwd=REPO / "agents" / "stargazer",
        input=json.dumps(
            {
                "task_id": task_id,
                "accessKey": "AK-SENTINEL",
                "accessSecret": SECRET,
                "region": "cn-beijing",
                "host": cloud_url,
            }
        ),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert SECRET not in completed.stdout
    payload = json.loads(completed.stdout)
    assert SECRET not in payload["prometheus"]
    return payload


def _samples_from_influx(lines):
    samples = []
    for line in lines:
        parsed = _parse_influx(line)
        if parsed is None:
            continue
        measurement, tags, field, timestamp = parsed
        if field != "gauge":
            continue
        seconds = int(timestamp) / 1_000_000_000 if len(str(timestamp)) >= 16 else float(timestamp or time.time())
        samples.append({"metric": {"__name__": f"{measurement}_{field}", **tags}, "value": [seconds, "1"]})
    return samples


def _unescaped_indexes(text, target):
    indexes = []
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == target:
            indexes.append(index)
    return indexes


def _parse_influx(line):
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    spaces = _unescaped_indexes(text, " ")
    if len(spaces) < 2:
        return None
    timestamp = text[spaces[-1] + 1 :]
    body = text[: spaces[-1]]
    meta = body[: spaces[-2]]
    field_part = body[spaces[-2] + 1 :]
    measurement, tag_text = _split_measurement(meta)
    tags = _parse_tags(tag_text)
    field_name, _value = field_part.split("=", 1)
    return measurement, tags, field_name, timestamp


def _split_measurement(meta):
    chars = []
    index = 0
    while index < len(meta):
        if meta[index] == "\\" and index + 1 < len(meta):
            chars.append(meta[index + 1])
            index += 2
            continue
        if meta[index] == ",":
            return "".join(chars), meta[index + 1 :]
        chars.append(meta[index])
        index += 1
    return "".join(chars), ""


def _parse_tags(text):
    tags = {}
    token = []
    escaped = False
    parts = []
    for char in text:
        if escaped:
            token.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == ",":
            parts.append("".join(token))
            token = []
            continue
        token.append(char)
    if token:
        parts.append("".join(token))
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        tags[key] = value
    return tags


def _rows(graph, model_id):
    return [row for row in graph.rows.values() if row.get("model_id") == model_id]


def _attrs(model_id):
    fields = [
        "inst_name",
        "resource_name",
        "resource_id",
        "region",
        "ip_addr",
        "public_ip",
        "zone",
        "vpc",
        "status",
        "instance_type",
        "os_name",
        "vcpus",
        "memory_mb",
        "charge_type",
        "create_time",
        "expired_time",
        "bandwidth",
        "instance_id",
        "port",
        "version",
        "storage_gb",
        "storage_type",
        "location",
        "extranet_endpoint",
        "intranet_endpoint",
        "bucket_type",
        "creation_date",
        "tag",
        "type",
        "organization",
        "auto_collect",
        "collect_time",
        "collect_task",
        "inst_uuid",
    ]
    return [
        dict(
            attr_id=field,
            attr_name=field,
            is_only=field in {"inst_name", "resource_id"},
            is_required=field in {"inst_name", "organization"},
            editable=True,
        )
        for field in fields
    ]


@pytest.mark.django_db
def test_mock_cloud_task_reaches_vm_and_cmdb(monkeypatch):
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(key, raising=False)
    task = CollectModels.objects.create(
        name="火山引擎北京",
        task_type="cloud",
        driver_type="protocol",
        model_id="volcengine_account",
        timeout=60,
        team=[1],
        is_interval=False,
        cycle_value_type="cycle",
        instances=[{"inst_name": ACCOUNT, "model_id": "volcengine_account", "endpoint": ""}],
        access_point=[{"id": "node-1"}],
        credential=[{"accessKey": "AK-SENTINEL", "accessSecret": SECRET, "regions": {"resource_id": "cn-beijing", "resource_name": "cn-beijing"}}],
        params={},
        data_cleanup_strategy=DataCleanupStrategy.IMMEDIATELY,
    )
    node = NodeParamsFactory.get_node_params(task)
    pushed = node.main("push")
    assert SECRET not in pushed[0]["content"]
    headers = node.custom_headers()
    assert headers["cmdbplugin_name"] == "volcengine_info"
    assert headers["cmdbregion"] == "cn-beijing"
    assert headers["cmdbaccessSecret"].startswith("${PASSWORD_")
    assert node.env_config()[f"PASSWORD_access_secret_cmdb_{task.id}"] == SECRET

    graph = Graph()
    graph.insert(ACCOUNT, model="volcengine_account", owner=str(task.id))
    stale = graph.insert("stale(i-stale)", model="volcengine_ecs", owner=str(task.id), collect_time=OLD, resource_id="i-stale")
    for module_name in ("apps.cmdb.collection.common", "apps.cmdb.collection.metrics_cannula"):
        monkeypatch.setattr(f"{module_name}.GraphClient", lambda **kwargs: graph)
    monkeypatch.setattr("apps.cmdb.collection.common.ModelManage.search_model_attr", lambda model_id: _attrs(model_id))
    monkeypatch.setattr("apps.cmdb.collection.common.write_collect_instance_change_records", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.cmdb.services.auto_relation_reconcile.schedule_incoming_rule_full_sync_by_model_ids", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.cmdb.display_field.handler.DisplayFieldConverter.convert_organization", staticmethod(lambda value: ""))

    state = {"phase": "collect"}
    cloud = _start_cloud(state)
    vm_samples = []
    vm = _start_vm(vm_samples)
    monkeypatch.setattr("apps.cmdb.collection.query_vm.VICTORIAMETRICS_HOST", vm.url)
    try:
        _ingest(task, graph, vm_samples, _collect(cloud.url, task.id)["influx"])
        web = next(row for row in _rows(graph, "volcengine_ecs") if row["resource_id"] == "i-web")
        assert web["inst_name"] == "web(i-web)"
        assert web["status"] == "RUNNING"
        assert web["ip_addr"] == "10.0.0.8"
        assert web["public_ip"] == "1.2.3.4"
        assert web["vcpus"] == 2
        assert web["memory_mb"] == 4096
        assert web["charge_type"] == "PostPaid"
        assert web["tag"] == ["env:prod"]
        assert stale["_id"] not in graph.rows
        assert {row["resource_id"] for row in _rows(graph, "volcengine_tos")} == {"keep-bucket"}
        assert next(row["charge_type"] for row in _rows(graph, "volcengine_clb")) == "1"
        assert next(row["port"] for row in _rows(graph, "volcengine_mysql")) == 3306
        assert next(row["version"] for row in _rows(graph, "volcengine_pgsql")) == "PostgreSQL_14"
        assert _edge_ids(graph, "volcengine_eip_connect_volcengine_ecs")
        original_uuid = web["inst_uuid"]

        state["phase"] = "rename"
        _ingest(task, graph, vm_samples, _collect(cloud.url, task.id)["influx"])
        renamed = next(row for row in _rows(graph, "volcengine_ecs") if row["resource_id"] == "i-web")
        assert renamed["_id"] == web["_id"]
        assert renamed["inst_uuid"] == original_uuid
        assert renamed["inst_name"] == "web-renamed(i-web)"
        assert _edge_ids(graph, "volcengine_eip_connect_volcengine_ecs")
        assert _edge_ids(graph, "volcengine_eip_connect_volcengine_clb")

        state["phase"] = "ecs-failed"
        _ingest(task, graph, vm_samples, _collect(cloud.url, task.id)["influx"])
        assert any(row["resource_id"] == "i-web" and row["inst_name"] == "web-renamed(i-web)" for row in _rows(graph, "volcengine_ecs"))
        assert next(row["version"] for row in _rows(graph, "volcengine_mysql")) == "MySQL_8_0"
    finally:
        cloud.close()
        vm.close()


def _edge_ids(graph, model_asst_id):
    return [edge for edge in graph.edges if edge[2] == model_asst_id]


def _ingest(task, graph, vm_samples, lines):
    vm_samples[:] = _samples_from_influx(lines)
    task._sync_snapshot_complete = True
    cannula = MetricsCannula(
        None,
        [1],
        ACCOUNT,
        task.id,
        VolcengineAccountCollectionPlugin,
        task=task,
        reconcile_task_assets=True,
        data_cleanup_strategy=task.data_cleanup_strategy,
        plugin_kwargs={"collect_inst": task},
    )
    result = cannula.collect_controller()
    for model_id, outcome in result.items():
        if not isinstance(outcome, dict) or "add" not in outcome:
            continue
        assert outcome["add"]["failed"] == [], outcome
        assert outcome["update"]["failed"] == [], outcome
    assert SECRET not in json.dumps(result, default=str)
