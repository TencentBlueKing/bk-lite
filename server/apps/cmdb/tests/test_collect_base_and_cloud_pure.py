# -*- coding: utf-8 -*-
"""CollectBase 共享逻辑 + aliyun/qcloud 采集插件纯方法测试。

CollectBase：prom_sql 构造、convert_datetime_format ISO 转换、run() 编排、
check_metrics 断言。aliyun/qcloud：inst_name 拼接、belong 关联、check_task_id。
只 mock 真实外部边界（CollectModels DB、VM 查询）。
"""
import time

import pytest

from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.collection.collect_util import timestamp_gt_one_day_ago


# --------------------------------------------------------------------------
# collect_util
# --------------------------------------------------------------------------


def test_timestamp_gt_one_day_ago():
    now = int(time.time())
    assert timestamp_gt_one_day_ago(now - 30) is False  # 30 秒前：未超一天
    assert timestamp_gt_one_day_ago(now - 2 * 86400) is True  # 两天前：超一天


# --------------------------------------------------------------------------
# CollectBase（最小具体子类，不触发 DB）
# --------------------------------------------------------------------------


class _DummyCollect(CollectBase):
    @property
    def _metrics(self):
        return ["host_info_gauge", "host_proc_info_gauge"]

    def format_data(self, data):
        self.result["raw"] = data

    def format_metrics(self):
        self.result["formatted"] = True


def _dummy(monkeypatch, model_id="host"):
    # 直接给定 inst_name，避免 __init__ 走 get_collect_inst() 的 DB
    runner = _DummyCollect(inst_name="h1", inst_id=1, task_id=42)
    monkeypatch.setattr(type(runner), "model_id", property(lambda self: model_id))
    return runner


def test_collect_base_init_metrics_dict(monkeypatch):
    r = _dummy(monkeypatch)
    # 每个 metric 一个空列表
    assert set(r.collection_metrics_dict.keys()) == {"host_info_gauge", "host_proc_info_gauge"}
    assert r.collection_metrics_dict["host_info_gauge"] == []
    assert r._instance_id == "cmdb_42"
    assert r.asso == "assos"


def test_collect_base_prom_sql(monkeypatch):
    r = _dummy(monkeypatch)
    sql = r.prom_sql()
    assert "host_info_gauge{instance_id='cmdb_42'}" in sql
    assert "host_proc_info_gauge{instance_id='cmdb_42'}" in sql
    assert " or " in sql


def test_collect_base_check_metrics(monkeypatch):
    r = _dummy(monkeypatch)
    assert r.check_metrics() is True


def test_collect_base_convert_datetime_format():
    out = CollectBase.convert_datetime_format("2025-01-02 03:04:05")
    assert out == "2025-01-02T03:04:05+00:00"


def test_collect_base_convert_datetime_empty():
    assert CollectBase.convert_datetime_format("") == ""


def test_collect_base_convert_datetime_invalid():
    # 非法格式 → 捕获异常返回空串（不抛）
    assert CollectBase.convert_datetime_format("not-a-time") == ""


def test_collect_base_run_orchestration(monkeypatch):
    r = _dummy(monkeypatch)
    # query_data 走 Collection().query，mock 成返回固定结构
    monkeypatch.setattr(
        r, "query_data", lambda: {"result": [{"metric": {}, "value": [1, "1"]}]}
    )
    out = r.run()
    assert out["formatted"] is True
    assert r.raw_data == [{"metric": {}, "value": [1, "1"]}]


def test_collect_base_query_data(monkeypatch):
    r = _dummy(monkeypatch)
    captured = {}

    class _FakeCollection:
        def query(self, sql):
            captured["sql"] = sql
            return {"data": {"result": [1, 2, 3]}}

    monkeypatch.setattr("apps.cmdb.collection.collect_plugin.base.Collection", lambda: _FakeCollection())
    out = r.query_data()
    assert out == {"result": [1, 2, 3]}
    assert "instance_id='cmdb_42'" in captured["sql"]


# --------------------------------------------------------------------------
# Aliyun 纯方法
# --------------------------------------------------------------------------


def _aliyun(monkeypatch, model_id="aliyun_ecs", task_id="7"):
    from apps.cmdb.collection.collect_plugin.aliyun import AliyunCollectMetrics

    # _metrics property 会触发 get_collection_plugin/DB；构造期需绕开 check_metrics 用的 _metrics
    monkeypatch.setattr(AliyunCollectMetrics, "_metrics", property(lambda self: ["m_info_gauge"]))
    monkeypatch.setattr(AliyunCollectMetrics, "model_id", property(lambda self: model_id))
    return AliyunCollectMetrics(inst_name="阿里云生产", inst_id=1, task_id=task_id)


def test_aliyun_set_instance_inst_name(monkeypatch):
    from apps.cmdb.collection.collect_plugin.aliyun import AliyunCollectMetrics

    name = AliyunCollectMetrics.set_instance_inst_name({"resource_name": "web", "resource_id": "i-001"})
    assert name == "web(i-001)"


def test_aliyun_check_task_id(monkeypatch):
    # instance_id 形如 "{account}_{task_id}"；split 出的是字符串，故 self.task_id 也须为字符串才匹配
    r = _aliyun(monkeypatch, task_id="7")
    assert r.check_task_id("acct_7") is True
    assert r.check_task_id("acct_99") is False


def test_aliyun_check_task_id_type_mismatch(monkeypatch):
    # 真实行为锁定：task_id 为 int 时，与 split 出的字符串恒不相等 → 永远 False。
    r = _aliyun(monkeypatch, task_id=7)
    assert r.check_task_id("acct_7") is False


def test_aliyun_set_asso_instances(monkeypatch):
    r = _aliyun(monkeypatch)
    out = r.set_asso_instances({}, model_id="aliyun_ecs")
    assert out == [
        {
            "model_id": "aliyun_account",
            "inst_name": "阿里云生产",
            "asst_id": "belong",
            "model_asst_id": "aliyun_ecs_belong_aliyun_account",
        }
    ]


# --------------------------------------------------------------------------
# QCloud 纯方法
# --------------------------------------------------------------------------


def _qcloud(monkeypatch, model_id="qcloud_cvm"):
    from apps.cmdb.collection.collect_plugin.qcloud import QCloudCollectMetrics

    monkeypatch.setattr(QCloudCollectMetrics, "_metrics", property(lambda self: ["m_info_gauge"]))
    monkeypatch.setattr(QCloudCollectMetrics, "model_id", property(lambda self: model_id))
    return QCloudCollectMetrics(inst_name="腾讯云生产", inst_id=1, task_id=3)


def test_qcloud_set_instance_inst_name():
    from apps.cmdb.collection.collect_plugin.qcloud import QCloudCollectMetrics

    name = QCloudCollectMetrics.set_instance_inst_name({"resource_name": "cvm", "resource_id": "ins-9"})
    assert name == "cvm_ins-9"


def test_qcloud_set_asso_instances(monkeypatch):
    r = _qcloud(monkeypatch)
    out = r.set_asso_instances({}, model_id="qcloud_cvm")
    assert out == [
        {
            "model_id": "qcloud",
            "inst_name": "腾讯云生产",
            "asst_id": "belong",
            "model_asst_id": "qcloud_cvm_belong_qcloud",
        }
    ]


def test_qcloud_format_metrics_skips_collect_error(monkeypatch):
    """qcloud format_metrics：带 cmdb_collect_error 的指标被跳过，不进 result。"""
    r = _qcloud(monkeypatch, model_id="qcloud_cvm")
    monkeypatch.setattr(
        type(r),
        "model_field_mapping",
        property(lambda self: {"qcloud_cvm": {"name": "resource_name"}}),
    )
    r.collection_metrics_dict = {
        "qcloud_cvm_info_gauge": [
            {"cmdb_collect_error": "auth failed", "resource_name": "x", "resource_id": "1"},
            {"resource_name": "ok", "resource_id": "2"},
        ]
    }
    r.format_metrics()
    assert r.result["qcloud_cvm"] == [{"name": "ok"}]


def test_qcloud_format_metrics_skips_incomplete_identity(monkeypatch):
    """缺 resource_name 或 resource_id 的指标被跳过。"""
    r = _qcloud(monkeypatch, model_id="qcloud_cvm")
    monkeypatch.setattr(
        type(r),
        "model_field_mapping",
        property(lambda self: {"qcloud_cvm": {"name": "resource_name"}}),
    )
    r.collection_metrics_dict = {
        "qcloud_cvm_info_gauge": [
            {"resource_name": "noid"},  # 缺 resource_id
            {"resource_id": "noname"},  # 缺 resource_name
        ]
    }
    r.format_metrics()
    assert r.result["qcloud_cvm"] == []
