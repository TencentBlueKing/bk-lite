"""Issue #3337：告警策略序列化器入参校验（threshold/query_condition/source/algorithm）单测。

MonitorPolicySerializer 继承 DRF ModelSerializer 且 import 了 Django 模型，本仓 pytest 因缺
license_mgmt/MINIO 无法 django.setup()。这些 validate_* 方法不依赖 ORM（仅校验入参结构/枚举），
故沿用注入式 harness：stub rest_framework / 模型 / 常量后 importlib 加载，在 bare 实例上直接调。
"""
import importlib.util
import sys
import types
from pathlib import Path


class _StubValidationError(Exception):
    pass


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_serializer_module(monkeypatch, module_name):
    rest_serializers = _install_module(
        monkeypatch,
        "rest_framework.serializers",
        ModelSerializer=object,
        ValidationError=_StubValidationError,
    )
    _install_module(monkeypatch, "rest_framework", serializers=rest_serializers)
    _install_module(
        monkeypatch,
        "apps.monitor.constants.alert_policy",
        AlertConstants=types.SimpleNamespace(
            THRESHOLD_METHODS={">": 1, "<": 1, "=": 1, "!=": 1, ">=": 1, "<=": 1},
        ),
    )
    _install_module(monkeypatch, "apps.monitor.models.monitor_policy", MonitorPolicy=object)

    spec = importlib.util.spec_from_file_location(
        module_name,
        Path(__file__).resolve().parents[1] / "serializers" / "monitor_policy.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _serializer(module):
    return module.MonitorPolicySerializer.__new__(module.MonitorPolicySerializer)


def _assert_raises(fn):
    try:
        fn()
    except _StubValidationError:
        return
    raise AssertionError("预期抛 ValidationError，但未抛出")


# ---------------- threshold ----------------


def test_validate_threshold_accepts_valid_and_empty(monkeypatch):
    s = _serializer(_load_serializer_module(monkeypatch, "mp_threshold_ok_module"))
    assert s.validate_threshold([]) == []
    valid = [{"method": ">", "value": 90, "level": "critical"}, {"method": "<=", "value": 1, "level": "warning"}]
    assert s.validate_threshold(valid) == valid


def test_validate_threshold_rejects_missing_keys_and_bad_enums(monkeypatch):
    s = _serializer(_load_serializer_module(monkeypatch, "mp_threshold_bad_module"))
    _assert_raises(lambda: s.validate_threshold([{"value": 1, "level": "warning"}]))  # 缺 method
    _assert_raises(lambda: s.validate_threshold([{"method": ">", "level": "warning"}]))  # 缺 value
    _assert_raises(lambda: s.validate_threshold([{"method": ">", "value": 1}]))  # 缺 level
    _assert_raises(lambda: s.validate_threshold([{"method": "=~", "value": 1, "level": "warning"}]))  # 非法 method
    _assert_raises(lambda: s.validate_threshold([{"method": ">", "value": 1, "level": "fatal"}]))  # 非法 level
    _assert_raises(lambda: s.validate_threshold(["not-a-dict"]))
    _assert_raises(lambda: s.validate_threshold("not-a-list"))


# ---------------- query_condition ----------------


def test_validate_query_condition_pmq_requires_query(monkeypatch):
    s = _serializer(_load_serializer_module(monkeypatch, "mp_qc_pmq_module"))
    assert s.validate_query_condition({"type": "pmq", "query": "up{}"}) == {"type": "pmq", "query": "up{}"}
    _assert_raises(lambda: s.validate_query_condition({"type": "pmq"}))
    _assert_raises(lambda: s.validate_query_condition({"type": "pmq", "query": ""}))


def test_validate_query_condition_metric_requires_metric_id(monkeypatch):
    s = _serializer(_load_serializer_module(monkeypatch, "mp_qc_metric_module"))
    assert s.validate_query_condition({"type": "metric", "metric_id": 7}) == {"type": "metric", "metric_id": 7}
    assert s.validate_query_condition({}) == {}  # 空（草稿）放行
    _assert_raises(lambda: s.validate_query_condition({"type": "metric"}))  # 缺 metric_id
    _assert_raises(lambda: s.validate_query_condition({"filter": []}))  # 非 pmq 且无 metric_id


# ---------------- source ----------------


def test_validate_source_requires_type_values_and_valid_type(monkeypatch):
    s = _serializer(_load_serializer_module(monkeypatch, "mp_source_module"))
    assert s.validate_source({}) == {}  # 空放行
    ok = {"type": "instance", "values": ["i-1"]}
    assert s.validate_source(ok) == ok
    assert s.validate_source({"type": "organization", "values": [1]}) == {"type": "organization", "values": [1]}
    _assert_raises(lambda: s.validate_source({"type": "instance"}))  # 缺 values
    _assert_raises(lambda: s.validate_source({"values": []}))  # 缺 type
    _assert_raises(lambda: s.validate_source({"type": "host", "values": []}))  # 非法 type


# ---------------- algorithm ----------------


def test_validate_algorithm_enforces_supported_set(monkeypatch):
    s = _serializer(_load_serializer_module(monkeypatch, "mp_algo_module"))
    for ok in ("max", "avg", "last_over_time"):
        assert s.validate_algorithm(ok) == ok
    assert s.validate_algorithm("") == ""  # 空放行（交由其它校验）
    _assert_raises(lambda: s.validate_algorithm("median"))
    _assert_raises(lambda: s.validate_algorithm("p99"))
