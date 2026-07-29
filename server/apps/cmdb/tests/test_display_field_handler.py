"""CMDB 显示字段处理器覆盖测试（build_display_fields + _to_display 私有方法 + InstanceTaskPermission）。

对照 specs/capabilities/legacy-prd-cmdb-资产.md：实例创建/更新时自动维护 _display 冗余字段、按类型转换、降级路径。
"""

from types import SimpleNamespace

import pytest

from apps.cmdb.display_field.handler import DisplayFieldHandler
from apps.cmdb.permissions.inst_task_permission import InstanceTaskPermission


# --------------------------------------------------------------------------
# build_display_fields
# --------------------------------------------------------------------------


def test_build_display_fields_no_attrs():
    data = {"inst_name": "h"}
    out = DisplayFieldHandler.build_display_fields("host", data, [])
    assert out is data
    assert "inst_name" in out


def test_build_display_fields_skips_non_target_type():
    data = {"inst_name": "h"}
    DisplayFieldHandler.build_display_fields(
        "host", data, [{"attr_id": "inst_name", "attr_type": "str"}]
    )
    # str 不在 DISPLAY_FIELD_TYPES → 不生成 _display
    assert "inst_name_display" not in data


def test_build_display_fields_skips_missing_attr():
    data = {"inst_name": "h"}
    DisplayFieldHandler.build_display_fields(
        "host", data,
        [{"attr_id": "status", "attr_type": "enum", "option": [{"id": "1", "name": "运行"}]}],
    )
    # status 不在 data 中 → 跳过
    assert "status_display" not in data


def test_build_display_fields_enum():
    data = {"status": "1"}
    DisplayFieldHandler.build_display_fields(
        "host", data,
        [{"attr_id": "status", "attr_type": "enum",
          "option": [{"id": "1", "name": "运行中"}, {"id": "2", "name": "已停止"}]}],
    )
    assert data["status_display"] == "运行中"


def test_build_display_fields_tag():
    data = {"tag": ["env:prod"]}
    DisplayFieldHandler.build_display_fields(
        "host", data, [{"attr_id": "tag", "attr_type": "tag"}],
    )
    assert "env:prod" in data["tag_display"]


def test_build_display_fields_table():
    data = {"cfg": [{"k": "v"}]}
    DisplayFieldHandler.build_display_fields(
        "host", data, [{"attr_id": "cfg", "attr_type": "table"}],
    )
    assert "v" in data["cfg_display"]


# --------------------------------------------------------------------------
# 私有 _convert_* 转换器（直接调用）
# --------------------------------------------------------------------------


def test_convert_enum_to_display():
    assert DisplayFieldHandler._convert_enum_to_display(
        "1", [{"id": "1", "name": "运行"}]
    ) == "运行"


def test_convert_tag_to_display():
    assert "a:1" in DisplayFieldHandler._convert_tag_to_display(["a:1", "b:2"])


def test_convert_table_to_display():
    out = DisplayFieldHandler._convert_table_to_display([{"k": "v"}])
    assert "v" in out


# --------------------------------------------------------------------------
# InstanceTaskPermission
# --------------------------------------------------------------------------


def test_inst_task_perm_no_rule_allows(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.permissions.inst_task_permission.get_cmdb_rules",
        lambda request: {},
    )
    perm = InstanceTaskPermission()
    request = SimpleNamespace()
    view = SimpleNamespace(action="list")
    obj = SimpleNamespace(task_type="x", id=1)
    assert perm.has_object_permission(request, view, obj) is True


def test_inst_task_perm_global_view(monkeypatch):
    rules = {"x": [{"id": "0", "permission": ["View"]}]}
    monkeypatch.setattr(
        "apps.cmdb.permissions.inst_task_permission.get_cmdb_rules",
        lambda request: rules,
    )
    perm = InstanceTaskPermission()
    view = SimpleNamespace(action="list")
    obj = SimpleNamespace(task_type="x", id=1)
    assert perm.has_object_permission(SimpleNamespace(), view, obj) is True


def test_inst_task_perm_operate_action_global(monkeypatch):
    rules = {"x": [{"id": "0", "permission": ["Operator"]}]}
    monkeypatch.setattr(
        "apps.cmdb.permissions.inst_task_permission.get_cmdb_rules",
        lambda request: rules,
    )
    perm = InstanceTaskPermission()
    view = SimpleNamespace(action="update")
    obj = SimpleNamespace(task_type="x", id=1)
    assert perm.has_object_permission(SimpleNamespace(), view, obj) is True


def test_inst_task_perm_specific_id_allowed(monkeypatch):
    rules = {"x": [{"id": "5", "permission": ["View"]}]}
    monkeypatch.setattr(
        "apps.cmdb.permissions.inst_task_permission.get_cmdb_rules",
        lambda request: rules,
    )
    perm = InstanceTaskPermission()
    view = SimpleNamespace(action="list")
    obj = SimpleNamespace(task_type="x", id=5)
    assert perm.has_object_permission(SimpleNamespace(), view, obj) is True


def test_inst_task_perm_denied(monkeypatch):
    rules = {"x": [{"id": "5", "permission": ["View"]}]}
    monkeypatch.setattr(
        "apps.cmdb.permissions.inst_task_permission.get_cmdb_rules",
        lambda request: rules,
    )
    perm = InstanceTaskPermission()
    view = SimpleNamespace(action="list")
    obj = SimpleNamespace(task_type="x", id=99)
    assert perm.has_object_permission(SimpleNamespace(), view, obj) is False
