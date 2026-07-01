# -*- coding: utf-8 -*-
"""MiddlewareCollectMetrics 采集解析测试。

不连 DB/VM：model_id 桩为 "nginx"，喂真实形态的 stargazer 中间件指标 dict。
覆盖：pick_value 占位符/空值跳过、实例名与 IP/端口推断、result JSON 反转义解析、
失败状态过滤、host 关联构造、端口提取、JSON 字段序列化，以及 nginx 真实
field_mapping 的 format_metrics 端到端转换。
"""
import pydantic.root_model  # noqa: F401  预热
import time

import pytest

from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setattr(MiddlewareCollectMetrics, "model_id", property(lambda self: "nginx"))
    return MiddlewareCollectMetrics("nginx-inst", "cmdb_5", 5)


def _now_ts():
    return int(time.time())


# ---------------------------------------------------------------------------
# pick_value
# ---------------------------------------------------------------------------


def test_pick_value_non_dict():
    assert MiddlewareCollectMetrics.pick_value("x", ("a",), default="d") == "d"


def test_pick_value_skips_placeholder_and_blank():
    data = {"ip_addr": "{{bk_host_innerip}}", "host": "   ", "bk_host_innerip": "10.1.1.1"}
    assert MiddlewareCollectMetrics.pick_value(data, ("ip_addr", "host", "bk_host_innerip")) == "10.1.1.1"


def test_pick_value_strips_string():
    assert MiddlewareCollectMetrics.pick_value({"port": "  8080 "}, ("port",)) == "8080"


def test_pick_value_returns_non_string_as_is():
    assert MiddlewareCollectMetrics.pick_value({"port": 8080}, ("port",)) == 8080


def test_pick_value_default_when_missing():
    assert MiddlewareCollectMetrics.pick_value({}, ("port",), default=0) == 0


# ---------------------------------------------------------------------------
# IP / 实例名 / 端口推断
# ---------------------------------------------------------------------------


def test_get_ip_addr_from_ip_field(runner):
    assert runner.get_ip_addr({"ip_addr": "10.0.0.1"}) == "10.0.0.1"


def test_get_ip_addr_falls_back_to_instance_id(runner):
    assert runner.get_ip_addr({"instance_id": "cmdb_10.0.0.2"}) == "10.0.0.2"


def test_get_ip_addr_falls_back_to_inst_name(runner):
    assert runner.get_ip_addr({}) == "nginx-inst"


def test_get_inst_name_ip_and_port(runner):
    assert runner.get_inst_name({"ip_addr": "10.0.0.1", "port": "80"}) == "10.0.0.1-nginx-80"


def test_get_inst_name_ip_only(runner):
    assert runner.get_inst_name({"ip_addr": "10.0.0.1"}) == "10.0.0.1"


def _empty_name_runner(monkeypatch):
    monkeypatch.setattr(MiddlewareCollectMetrics, "model_id", property(lambda self: "nginx"))
    r = MiddlewareCollectMetrics("placeholder", "cmdb_5", 5)
    r.inst_name = ""
    return r


def test_get_inst_name_fallback_identifier(monkeypatch):
    r = _empty_name_runner(monkeypatch)
    # 无 IP/端口 -> 走 _extract_instance_identifier
    assert r.get_inst_name({"instance_id": "cmdb_abc"}) == "abc"


def test_extract_instance_identifier_branches():
    assert MiddlewareCollectMetrics._extract_instance_identifier("x") == ""
    assert MiddlewareCollectMetrics._extract_instance_identifier({"instance_id": "cmdb_1.2.3.4"}) == "1.2.3.4"
    assert MiddlewareCollectMetrics._extract_instance_identifier({"instance_id": "plain"}) == "plain"


def test_get_port(runner):
    assert runner.get_port({"listen_port": "9000"}) == "9000"


def test_get_keepalived_inst_name(runner):
    assert runner.get_keepalived_inst_name({"ip_addr": "10.0.0.1", "virtual_router_id": "51"}) == "10.0.0.1-nginx-51"
    # 有 IP 无 router_id -> 退化到 get_inst_name
    assert runner.get_keepalived_inst_name({"ip_addr": "10.0.0.1"}) == "10.0.0.1"


def test_get_keepalived_inst_name_router_only(monkeypatch):
    r = _empty_name_runner(monkeypatch)
    assert r.get_keepalived_inst_name({"virtual_router_id": "51"}) == "51"


def test_get_docker_inst_name_prefers_existing(runner):
    assert runner.get_docker_inst_name({"inst_name": "my-container"}) == "my-container"
    assert runner.get_docker_inst_name({"ip_addr": "10.0.0.1", "port": "2375"}) == "10.0.0.1-nginx-2375"


# ---------------------------------------------------------------------------
# host 关联
# ---------------------------------------------------------------------------


def test_get_host_assos_builds_relation(runner):
    assos = runner.get__host_assos({"ip_addr": "10.0.0.1"})
    assert assos == [
        {"model_id": "host", "inst_name": "10.0.0.1", "asst_id": "run", "model_asst_id": "rabbitmq_run_host"}
    ]


def test_get_host_assos_empty_when_no_ip(monkeypatch):
    r = _empty_name_runner(monkeypatch)
    assert r.get__host_assos({"node_name": "n1"}) == []


# ---------------------------------------------------------------------------
# 端口 / JSON 工具
# ---------------------------------------------------------------------------


def test_extract_primary_port_direct():
    assert MiddlewareCollectMetrics._extract_primary_port({"port": "8080"}) == "8080"


def test_extract_primary_port_from_list():
    data = {"ports": [{"host_port": "8081", "container_port": "80"}]}
    assert MiddlewareCollectMetrics._extract_primary_port(data) == "8081"


def test_extract_primary_port_from_json_string():
    data = {"ports": '[{"container_port": "5432"}]'}
    assert MiddlewareCollectMetrics._extract_primary_port(data) == "5432"


def test_extract_primary_port_bad_json():
    assert MiddlewareCollectMetrics._extract_primary_port({"ports": "not json"}) == ""


def test_extract_primary_port_non_dict():
    assert MiddlewareCollectMetrics._extract_primary_port("x") == ""


def test_format_json_field():
    assert MiddlewareCollectMetrics.format_json_field(None) == ""
    assert MiddlewareCollectMetrics.format_json_field("raw") == "raw"
    assert MiddlewareCollectMetrics.format_json_field({"a": 1}) == '{"a": 1}'


def test_extract_nested_value():
    assert MiddlewareCollectMetrics.extract_nested_value({"p": {"c": "v"}}, "p", "c") == "v"
    assert MiddlewareCollectMetrics.extract_nested_value({"p": "flat"}, "p", "c", default="d") == "d"


# ---------------------------------------------------------------------------
# format_data 解析 result JSON
# ---------------------------------------------------------------------------


def test_format_data_parses_result_json(runner):
    row = {
        "metric": {
            "__name__": "nginx_info_gauge",
            "collect_status": "success",
            "success": True,
            "result": '{\\"version\\": \\"1.20\\", \\"port\\": \\"80\\"}',
            "ip_addr": "10.0.0.1",
        },
        "value": [_now_ts(), "1"],
    }
    runner.format_data({"result": [row]})
    collected = runner.collection_metrics_dict["nginx_info_gauge"]
    assert len(collected) == 1
    assert collected[0]["version"] == "1.20"
    assert collected[0]["port"] == "80"


def test_format_data_skips_failed(runner):
    row = {
        "metric": {"__name__": "nginx_info_gauge", "collect_status": "failed"},
        "value": [_now_ts(), "1"],
    }
    runner.format_data({"result": [row]})
    assert runner.collection_metrics_dict["nginx_info_gauge"] == []


def test_format_data_skips_empty_result_dict(runner):
    # success 但 result 解析为空 dict -> continue
    row = {
        "metric": {"__name__": "nginx_info_gauge", "collect_status": "success", "result": "{}", "success": True},
        "value": [_now_ts(), "1"],
    }
    runner.format_data({"result": [row]})
    assert runner.collection_metrics_dict["nginx_info_gauge"] == []


# ---------------------------------------------------------------------------
# format_metrics 端到端（nginx 真实 field_mapping）
# ---------------------------------------------------------------------------


def test_format_metrics_nginx_mapping(runner):
    index = {
        "index_key": "nginx_info_gauge",
        "ip_addr": "10.0.0.1",
        "listen_port": "8080",
        "nginx_path": "/usr/sbin/nginx",
        "version": "1.20",
        "log_path": "/var/log/nginx",
        "config_path": "/etc/nginx/nginx.conf",
        "server_name": "example.com",
        "include": "conf.d/*.conf",
        "ssl_version": "TLSv1.3",
    }
    runner.collection_metrics_dict["nginx_info_gauge"] = [index]
    runner.format_metrics()
    result = runner.result["nginx"]
    assert len(result) == 1
    item = result[0]
    assert item["ip_addr"] == "10.0.0.1"
    assert item["port"] == "8080"  # pick_value(port, listen_port)
    assert item["bin_path"] == "/usr/sbin/nginx"  # pick_value(bin_path, nginx_path)
    assert item["conf_path"] == "/etc/nginx/nginx.conf"  # pick_value(conf_path, config_path)
    assert item["version"] == "1.20"
    assert item["inst_name"] == "10.0.0.1-nginx-8080"  # get_inst_name
