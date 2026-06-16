"""Issue #3338：实例列表页插件状态查询并发去重（_batch_plugin_status_maps）单测。

monitor_instance.py 直接 import 了一批 Django 模型，本仓 pytest 因缺 license_mgmt/MINIO
无法完成 django.setup()，故沿用注入式 harness：sys.modules 注入伪依赖 + importlib 加载被测模块，
仅验证 Django-free 的并发去重逻辑（不碰 ORM）。
"""
import importlib.util
import sys
import threading
import types
from pathlib import Path


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_monitor_instance_module(monkeypatch, module_name):
    class _Dummy:
        pass

    class _Logger:
        def warning(self, *args, **kwargs):
            return None

        def info(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=type("BaseAppException", (Exception,), {}))
    _install_module(monkeypatch, "apps.core.logger", monitor_logger=_Logger())
    _install_module(monkeypatch, "apps.core.utils.loader", LanguageLoader=_Dummy)
    _install_module(monkeypatch, "apps.monitor.constants.language", LanguageConstants=types.SimpleNamespace(MONITOR_OBJECT_PLUGIN="plugin"))
    _install_module(monkeypatch, "apps.monitor.constants.monitor_object", MonitorObjConstants=types.SimpleNamespace())
    _install_module(monkeypatch, "apps.monitor.constants.plugin", PluginConstants=types.SimpleNamespace())
    _install_module(
        monkeypatch,
        "apps.monitor.models",
        Metric=_Dummy,
        MonitorObject=_Dummy,
        CollectConfig=_Dummy,
        MonitorPlugin=_Dummy,
        MonitorInstanceOrganization=_Dummy,
        MonitorInstance=_Dummy,
    )
    _install_module(monkeypatch, "apps.monitor.services.monitor_object", MonitorObjectService=_Dummy)
    _install_module(monkeypatch, "apps.monitor.utils.dimension", parse_instance_id=lambda value: value)
    _install_module(monkeypatch, "apps.monitor.utils.victoriametrics_api", VictoriaMetricsAPI=_Dummy)

    spec = importlib.util.spec_from_file_location(
        module_name,
        Path(__file__).resolve().parents[1] / "services" / "monitor_instance.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _bare_search(module):
    # 跳过 __init__（其会查 DB），仅测 _batch_plugin_status_maps 自身逻辑
    return module.InstanceSearch.__new__(module.InstanceSearch)


def test_batch_dedups_identical_queries_and_runs_once(monkeypatch):
    module = _load_monitor_instance_module(monkeypatch, "monitor_instance_dedup_test_module")
    search = _bare_search(module)

    lock = threading.Lock()
    calls = []

    def fake_status_map(instance_id_keys, query):
        with lock:
            calls.append(query)
        return {f"inst::{query}": "2026-06-15T00:00:00+00:00"}

    monkeypatch.setattr(search, "get_plugin_normal_status_map", fake_status_map)

    # 3 个插件、2 个去重后的 query（q_a 出现两次）
    result = search._batch_plugin_status_maps(["instance_id"], {"q_a", "q_b"})

    # 相同 query 只查一次：调用次数 == 去重后 query 数
    assert sorted(calls) == ["q_a", "q_b"]
    assert result == {
        "q_a": {"inst::q_a": "2026-06-15T00:00:00+00:00"},
        "q_b": {"inst::q_b": "2026-06-15T00:00:00+00:00"},
    }


def test_batch_skips_blank_queries(monkeypatch):
    module = _load_monitor_instance_module(monkeypatch, "monitor_instance_blank_test_module")
    search = _bare_search(module)

    calls = []
    monkeypatch.setattr(search, "get_plugin_normal_status_map", lambda keys, query: calls.append(query) or {})

    result = search._batch_plugin_status_maps(["instance_id"], {"", None, "  ", "real_q"})

    assert calls == ["real_q"]
    assert result == {"real_q": {}}


def test_batch_isolates_single_query_failure(monkeypatch):
    module = _load_monitor_instance_module(monkeypatch, "monitor_instance_failure_test_module")
    search = _bare_search(module)

    def fake_status_map(instance_id_keys, query):
        if query == "boom":
            raise RuntimeError("VM down")
        return {"ok": query}

    monkeypatch.setattr(search, "get_plugin_normal_status_map", fake_status_map)

    result = search._batch_plugin_status_maps(["instance_id"], {"boom", "good"})

    # 单 query 失败降级为空映射，不影响其余 query
    assert result == {"boom": {}, "good": {"ok": "good"}}


def test_batch_empty_returns_empty(monkeypatch):
    module = _load_monitor_instance_module(monkeypatch, "monitor_instance_empty_test_module")
    search = _bare_search(module)

    called = []
    monkeypatch.setattr(search, "get_plugin_normal_status_map", lambda keys, query: called.append(query) or {})

    assert search._batch_plugin_status_maps(["instance_id"], set()) == {}
    assert called == []
