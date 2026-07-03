"""nats.monitor 纯辅助函数 + NATS create 处理器规格测试。

聚焦输入归一化、查询拼装、身份闸、序列化器落库。外部权限/VM 边界 mock。
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from apps.monitor.nats import monitor as nm


class TestNormalizeMonitorQueryData:
    def test_maps_aliases(self):
        out = nm._normalize_monitor_query_data({
            "monitor_object_id": 7, "start_time": 1, "end_time": 2,
        })
        assert out["monitor_obj_id"] == 7
        assert out["start"] == 1 and out["end"] == 2

    def test_keeps_existing(self):
        out = nm._normalize_monitor_query_data({"monitor_obj_id": 1, "start": 3, "end": 4})
        assert out["monitor_obj_id"] == 1 and out["start"] == 3


class TestNormalizePositiveInt:
    def test_default_for_empty(self):
        assert nm._normalize_positive_int(None, "page", default=1) == 1
        assert nm._normalize_positive_int("", "page", default=5) == 5

    def test_valid(self):
        assert nm._normalize_positive_int("3", "page") == 3

    def test_non_int_raises(self):
        with pytest.raises(ValueError):
            nm._normalize_positive_int("x", "page")

    def test_less_than_one_raises(self):
        with pytest.raises(ValueError):
            nm._normalize_positive_int(0, "page")


class TestNormalizeBool:
    @pytest.mark.parametrize("val,expected", [
        (True, True), (False, False), (None, False), ("", False),
        ("true", True), ("1", True), ("yes", True),
        ("false", False), ("0", False), ("no", False),
    ])
    def test_values(self, val, expected):
        assert nm._normalize_bool(val, "f") is expected

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            nm._normalize_bool("maybe", "f")


class TestNormalizeTimeValue:
    def test_empty_raises(self):
        with pytest.raises(ValueError):
            nm._normalize_time_value("", "t")

    def test_numeric_timestamp(self):
        assert isinstance(nm._normalize_time_value(1700000000, "t"), datetime)

    def test_digit_string(self):
        assert isinstance(nm._normalize_time_value("1700000000", "t"), datetime)

    def test_datetime_string(self):
        dt = nm._normalize_time_value("2026-01-01 10:00:00", "t")
        assert dt.year == 2026 and dt.hour == 10

    def test_bad_format_raises(self):
        with pytest.raises(ValueError):
            nm._normalize_time_value("01/01/2026", "t")


class TestNormalizeFilterValues:
    def test_empty(self):
        assert nm._normalize_filter_values(None, "f") == []

    def test_list(self):
        assert nm._normalize_filter_values([1, None, "a"], "f") == ["1", "a"]

    def test_comma_string(self):
        assert nm._normalize_filter_values("a, b , c", "f") == ["a", "b", "c"]

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            nm._normalize_filter_values(123, "f")


class TestBuildVmQueryFailureResult:
    def test_uses_error_and_type(self):
        out = nm._build_vm_query_failure_result(
            {"error": "boom", "errorType": "bad_data"}, "default"
        )
        assert out["result"] is False
        assert out["message"] == "bad_data: boom"

    def test_falls_back_to_default(self):
        out = nm._build_vm_query_failure_result({}, "默认错误")
        assert out["message"] == "默认错误"


class TestNormalizeStep:
    def test_empty_returns_default(self):
        assert nm._normalize_step(None) == "5m"
        assert nm._normalize_step("") == "5m"

    def test_valid_passthrough(self):
        assert nm._normalize_step("10m") == "10m"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            nm._normalize_step("abc")


class TestNormalizeDimensions:
    def _metric(self):
        return SimpleNamespace(
            instance_id_keys=["instance_id"],
            dimensions=[{"name": "device"}, "mount"],
        )

    def test_empty(self):
        assert nm._normalize_dimensions(self._metric(), None) == {}

    def test_non_dict_raises(self):
        with pytest.raises(ValueError):
            nm._normalize_dimensions(self._metric(), ["x"])

    def test_allowed_keys(self):
        out = nm._normalize_dimensions(self._metric(), {"device": "eth0", "mount": None})
        assert out == {"device": "eth0"}

    def test_invalid_key_raises(self):
        with pytest.raises(ValueError):
            nm._normalize_dimensions(self._metric(), {"bogus": "1"})


class TestPaginateItems:
    def test_slices(self):
        out = nm._paginate_items([1, 2, 3, 4, 5], 2, 2)
        assert out["count"] == 5
        assert out["items"] == [3, 4]
        assert out["page"] == 2


class TestResolveNatsActor:
    def test_non_dict_defaults(self):
        assert nm._resolve_nats_actor(None) == ("api", "domain.com")

    def test_extracts_username_domain(self):
        user = SimpleNamespace(username="bob", domain="corp.com")
        op, dom = nm._resolve_nats_actor({"user": user, "domain": "corp.com"})
        assert op == "bob" and dom == "corp.com"


class TestEnsureMaintainerFields:
    def test_sets_defaults(self):
        out = nm._ensure_maintainer_fields({}, operator="alice", domain="d.com")
        assert out["created_by"] == "alice"
        assert out["updated_by"] == "alice"
        assert out["domain"] == "d.com"

    def test_does_not_override(self):
        out = nm._ensure_maintainer_fields({"created_by": "x"}, operator="alice")
        assert out["created_by"] == "x"


class TestFlattenAndValidationMessage:
    def test_flatten_dict_and_list(self):
        msgs = nm._flatten_error_message({"name": ["required"], "age": "bad"})
        assert "name: required" in msgs
        assert "age: bad" in msgs

    def test_build_validation_message_dedups(self):
        exc = SimpleNamespace(detail={"a": ["x"], "b": ["x"]})
        msg = nm._build_validation_message(exc)
        # x 去重后只出现一次的拼接（字段前缀不同）
        assert "a: x" in msg and "b: x" in msg


class TestNormalizePermissionUser:
    def test_object_with_attrs(self):
        u = SimpleNamespace(username="a", domain="d")
        assert nm._normalize_permission_user(u) is u

    def test_string_becomes_namespace(self):
        u = nm._normalize_permission_user("bob")
        assert u.username == "bob" and u.domain == "domain.com"

    def test_empty_returns_input(self):
        assert nm._normalize_permission_user("") == ""


class TestEscapeAndLabelQuery:
    def test_escape(self):
        assert nm._escape_label_value('a"b\\c') == 'a\\"b\\\\c'

    def test_no_conditions_returns_query(self):
        assert nm._build_metric_label_query("up", None, None) == "up"

    def test_instance_ids_regex(self):
        q = nm._build_metric_label_query("up", instance_ids=["h1", "h2"])
        assert 'instance_id=~"h1|h2"' in q

    def test_replaces_labels_placeholder(self):
        q = nm._build_metric_label_query("cpu{__$labels__}", dimensions={"d": "x"})
        assert q == 'cpu{d="x"}'

    def test_merges_existing_labels(self):
        q = nm._build_metric_label_query('cpu{job="a"}', dimensions={"d": "x"})
        assert 'job="a"' in q and 'd="x"' in q

    def test_appends_labels_when_bare(self):
        q = nm._build_metric_label_query("cpu", dimensions={"d": "x"})
        assert q == 'cpu{d="x"}'


class TestGetInstancePermissionMap:
    def test_non_dict(self):
        assert nm._get_instance_permission_map(None) == {}

    def test_builds_map(self):
        perm = {"instance": [
            {"id": "i1", "permission": ["View"]},
            {"id": "i2", "permission": ["Operate"]},
            {"no_id": True},
        ]}
        assert nm._get_instance_permission_map(perm) == {
            "i1": ["View"], "i2": ["Operate"],
        }


class TestRequireAuthenticatedActor:
    def test_missing_user_returns_error(self):
        out = nm._require_authenticated_actor(None)
        assert out["result"] is False

    def test_valid_returns_none(self):
        user = SimpleNamespace(username="a", domain="d")
        assert nm._require_authenticated_actor({"user": user}) is None


@pytest.mark.django_db
class TestExecuteNatsCreate:
    def test_identity_gate_blocks_anonymous(self):
        out = nm._execute_nats_create(nm._create_metric_group_payload, {"name": "g"}, user_info=None)
        assert out["result"] is False
        assert "缺少用户" in out["message"]

    def test_create_monitor_object_type(self):
        out = nm.create_monitor_object_type(
            {"id": "natstype", "name": "NATS类型"},
            user_info={"user": SimpleNamespace(username="a", domain="domain.com")},
        )
        assert out["result"] is True
        from apps.monitor.models.monitor_object import MonitorObjectType
        assert MonitorObjectType.objects.filter(id="natstype").exists()

    def test_create_monitor_object_with_validation_error(self):
        # 缺 name → 序列化器校验失败 → result False
        out = nm.create_monitor_object(
            {"level": "base"},
            user_info={"user": SimpleNamespace(username="a", domain="domain.com")},
        )
        assert out["result"] is False
        assert out["message"]
