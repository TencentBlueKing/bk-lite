"""BaseCollect 采集基类逻辑单元测试。

对照 apps/cmdb/collection/collect_tasks/base.py：
  - format_params：IP 范围模式 vs 实例模式、organization 归一化为 list
  - build_plugin_kwargs：k8s 任务透传 collector_cluster_id
  - format_collect_data：normalize 结果 → add/update/delete/association 分桶、
    raw_data 透传 / 由 add/update/delete 派生 / sanitize
  - run：调度 MetricsCannula 并返回 (collect_data, format_data)

不触 DB：通过 task= 注入 fake task，绕过 CollectModels.objects.get。
"""
import pydantic.root_model  # noqa: F401

from types import SimpleNamespace

from apps.cmdb.collection.collect_tasks.base import BaseCollect
from apps.cmdb.constants.constants import DataCleanupStrategy


def _task(**kw):
    defaults = dict(
        id=1,
        instances=[],
        team=[1],
        params={},
        model_id="host",
        is_host=True,
        is_k8s=False,
        input_method=0,
        data_cleanup_strategy=DataCleanupStrategy.NO_CLEANUP,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


# --------------------------------------------------------------------------
# format_params
# --------------------------------------------------------------------------
def test_format_params_ip_range_mode_uses_team():
    t = _task(instances=[], team=[7], is_host=True)
    c = BaseCollect(instance_id=None, task=t)
    assert c.model_id == "host"
    assert c.inst_name is None
    assert c.organization == [7]
    assert c.inst_id is None
    assert c.filter_collect_task is False  # is_host=True → not is_host = False


def test_format_params_ip_range_falls_back_to_params_org():
    t = _task(instances=[], team=None, params={"organization": 9}, is_host=False)
    c = BaseCollect(instance_id=None, task=t)
    assert c.organization == [9]  # 标量被归一化为 list
    assert c.filter_collect_task is True  # not is_host


def test_format_params_instance_mode():
    t = _task(
        instances=[{"_id": "h1", "model_id": "host", "inst_name": "10.0.0.1", "organization": 3}],
        is_host=True,
    )
    c = BaseCollect(instance_id=None, task=t)
    assert c.model_id == "host"
    assert c.inst_name == "10.0.0.1"
    assert c.inst_id == "h1"
    assert c.organization == [3]


def test_format_params_instance_mode_org_from_team_when_missing():
    t = _task(
        instances=[{"_id": "h1", "model_id": "host", "inst_name": "x"}],
        team=[5],
    )
    c = BaseCollect(instance_id=None, task=t)
    assert c.organization == [5]


# --------------------------------------------------------------------------
# build_plugin_kwargs
# --------------------------------------------------------------------------
def test_build_plugin_kwargs_k8s_from_instance():
    t = _task(
        is_k8s=True,
        instances=[{"_id": "c1", "model_id": "k8s_cluster", "inst_name": "c", "collector_cluster_id": "vm-77"}],
    )
    c = BaseCollect(instance_id=None, task=t)
    assert c.plugin_kwargs == {"collector_cluster_id": "vm-77"}


def test_build_plugin_kwargs_k8s_from_params_fallback():
    t = _task(
        is_k8s=True,
        instances=[{"_id": "c1", "model_id": "k8s_cluster", "inst_name": "c"}],
        params={"collector_cluster_id": "vm-99"},
    )
    c = BaseCollect(instance_id=None, task=t)
    assert c.plugin_kwargs == {"collector_cluster_id": "vm-99"}


def test_build_plugin_kwargs_non_k8s_empty():
    t = _task(is_k8s=False, instances=[{"_id": "h1", "model_id": "host", "inst_name": "x"}])
    c = BaseCollect(instance_id=None, task=t)
    assert c.plugin_kwargs == {}


# --------------------------------------------------------------------------
# task_id / get_collect_plugin / run
# --------------------------------------------------------------------------
def test_task_id_returns_task_id():
    t = _task(id=42, instances=[{"_id": "h", "model_id": "host", "inst_name": "x"}])
    c = BaseCollect(instance_id=None, task=t)
    assert c.task_id == 42


def test_run_raises_when_no_plugin():
    import pytest
    t = _task(instances=[{"_id": "h", "model_id": "host", "inst_name": "x"}])
    c = BaseCollect(instance_id=None, task=t)
    with pytest.raises(NotImplementedError):
        c.run()


def test_run_drives_metrics_cannula(monkeypatch):
    t = _task(instances=[{"_id": "h", "model_id": "host", "inst_name": "x"}], input_method=1)
    c = BaseCollect(instance_id=None, task=t)
    c.COLLECT_PLUGIN = object()

    class FakeCannula:
        def __init__(self, **kw):
            self.kwargs = kw
            self.collect_data = {"raw": 1}

        def collect_controller(self):
            return {
                "__raw_data__": [],
                "all": 0,
                "host": {"add": {"success": [{"inst_info": {"_id": 1, "inst_name": "x"}}]}},
            }

    captured = {}

    def _factory(**kw):
        inst = FakeCannula(**kw)
        captured["inst"] = inst
        return inst

    monkeypatch.setattr("apps.cmdb.collection.collect_tasks.base.MetricsCannula", _factory)
    collect_data, format_data = c.run()
    assert collect_data == {"raw": 1}
    assert format_data["add"][0]["_id"] == 1
    # manual = bool(input_method) → True
    assert captured["inst"].kwargs["manual"] is True
    assert captured["inst"].kwargs["plugin_kwargs"] == {}


# --------------------------------------------------------------------------
# format_collect_data
# --------------------------------------------------------------------------
def _collect_base(monkeypatch):
    t = _task(instances=[{"_id": "h", "model_id": "host", "inst_name": "x"}])
    return BaseCollect(instance_id=None, task=t)


def test_format_collect_data_success_and_failed_buckets(monkeypatch):
    c = _collect_base(monkeypatch)
    # MetricsCannula 落地的 result 恒含 __raw_data__ 与 all 两个键（见 metrics_cannula.py）
    result = {
        "__raw_data__": [],
        "all": 0,
        "host": {
            "add": {
                "success": [{"inst_info": {"_id": 1, "inst_name": "ok"}, "assos_result": {}}],
                "failed": [{"instance_info": {"inst_name": "bad"}, "error": "boom"}],
            },
        }
    }
    out = c.format_collect_data(result)
    assert len(out["add"]) == 2
    success_item = next(i for i in out["add"] if i["_status"] == "success")
    failed_item = next(i for i in out["add"] if i["_status"] == "failed")
    assert success_item["_id"] == 1
    assert failed_item["_error"] == "boom"


def test_format_collect_data_extracts_associations(monkeypatch):
    c = _collect_base(monkeypatch)
    result = {
        "__raw_data__": [],
        "all": 0,
        "host": {
            "add": {
                "success": [
                    {
                        "inst_info": {"_id": 1, "inst_name": "ok"},
                        "assos_result": {"success": [{"model_asst_id": "a_b"}], "failed": []},
                    }
                ],
            }
        },
    }
    out = c.format_collect_data(result)
    assert len(out["association"]) == 1
    assert out["association"][0]["_status"] == "success"
    assert out["association"][0]["model_asst_id"] == "a_b"


def test_format_collect_data_passes_through_raw_data(monkeypatch):
    c = _collect_base(monkeypatch)
    result = {"__raw_data__": [{"ip": "1.1.1.1"}], "all": 1, "host": {"add": {"success": []}}}
    out = c.format_collect_data(result)
    assert out["__raw_data__"] == [{"ip": "1.1.1.1"}]


def test_format_collect_data_derives_raw_data_from_buckets_when_only_all(monkeypatch):
    c = _collect_base(monkeypatch)
    result = {
        "all": 2,
        "host": {
            "add": {
                "success": [
                    {"inst_info": {"_id": 1, "inst_name": "a", "model_id": "host", "ip_addr": "1.1.1.1"}, "assos_result": {}},
                ]
            }
        },
    }
    out = c.format_collect_data(result)
    assert out["all"] == 2
    assert "__raw_data__" in out
    assert out["__raw_data__"][0]["inst_name"] == "a"
    assert out["__raw_data__"][0]["model_id"] == "host"


def test_sanitize_raw_data_item_defaults_model_id():
    item = {"inst_name": "x", "ip": "1.1.1.1", "model_id": "", "junk": "drop-me"}
    out = BaseCollect._sanitize_raw_data_item(item)
    assert out["model_id"] == "host"
    assert "junk" not in out  # 仅保留 RAW_DATA_FIELDS


def test_format_assos_result_flattens_status():
    out = BaseCollect.format_assos_result({"success": [{"x": 1}], "failed": [{"y": 2}]})
    statuses = sorted(i["_status"] for i in out)
    assert statuses == ["failed", "success"]
