"""反射工具测试 —— 从 apps.cmdb.tests.e2e.schemas.<model_id>/04_cmdb_instance.schema.json 反射字段定义。

CMDB 实例字段定义实际存储在 JSON Schema 中(`apps/cmdb/tests/e2e/schemas/<model>/04_cmdb_instance.schema.json`),
不是 Django ORM Model(本项目架构是 graph-backed + 动态 model),因此 model_reflection
从 JSON Schema 反射,而不是从 `django_apps.get_models()`。

本测试用 mysql 真实落盘对象的 schema 验证反射行为:
  - required 字段必须返回 ModelFieldDef(is_required=True)
  - properties 中非 required 字段返回 ModelFieldDef(is_required=False)
  - 未知 model_id 抛 KeyError
"""
import pytest

from apps.cmdb.tests.e2e.utils.model_reflection import (
    get_model_field_def,
    ModelFieldDef,
)


def test_get_model_field_def_returns_required_fields():
    """mysql Model 必填字段(inst_name)必须返回 ModelFieldDef(is_required=True)。"""
    fields = get_model_field_def("mysql")
    assert "inst_name" in fields
    assert isinstance(fields["inst_name"], ModelFieldDef)
    assert fields["inst_name"].name == "inst_name"
    assert fields["inst_name"].is_required is True
    assert fields["inst_name"].field_type == "str"


def test_get_model_field_def_returns_optional_fields():
    """mysql Model 可选字段(version)必须返回 ModelFieldDef(is_required=False)。"""
    fields = get_model_field_def("mysql")
    # version 是 properties 中非 required 字段
    assert "version" in fields
    assert fields["version"].is_required is False


def test_get_model_field_def_returns_all_properties():
    """mysql Model 反射必须返回 schema 中所有 properties(必填 + 可选)。"""
    fields = get_model_field_def("mysql")
    expected = {"inst_name", "ip_addr", "port", "version", "role", "basedir", "datadir"}
    assert expected <= set(fields.keys())


def test_get_model_field_def_returns_choice_fields():
    """反射必须不抛异常(choice 字段检测在 choice schema 时返回 choice 列表)。"""
    fields = get_model_field_def("mysql")
    # mysql schema 没有 enum 约束,所有 choice 应为 None
    for field in fields.values():
        # choice 可以是 None 或 list
        assert field.choice is None or isinstance(field.choice, list)


def test_get_model_field_def_unknown_model_raises():
    """不存在的 model_id 必须抛 KeyError。"""
    with pytest.raises(KeyError):
        get_model_field_def("nonexistent_model_xyz")


def test_get_model_field_def_dataclass_frozen():
    """ModelFieldDef 必须是 frozen dataclass(不可变,保证反射结果稳定)。"""
    from dataclasses import FrozenInstanceError

    fields = get_model_field_def("mysql")
    field = fields["inst_name"]
    with pytest.raises(FrozenInstanceError):
        field.is_required = False  # type: ignore[misc]
