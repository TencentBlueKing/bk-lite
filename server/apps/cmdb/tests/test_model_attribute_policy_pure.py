"""ModelManage 枚举字段策略兼容门面契约。"""

import types
from importlib import import_module
from inspect import signature
from unittest.mock import Mock

import pytest

from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.model_attribute_policy import ModelAttributePolicy
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit

ENUM_POLICY_METHODS = (
    "_normalize_default_value",
    "sanitize_attr_default_value",
    "normalize_enum_public_binding",
    "validate_enum_rule_immutable",
    "ensure_enum_select_mode",
    "validate_enum_select_mode_immutable",
    "resolve_runtime_enum_options",
)

TAG_POLICY_METHODS = (
    "_is_tag_attr",
    "validate_tag_attr_definition",
    "normalize_tag_field_option",
)


def test_model_manage_enum_policy_keeps_signatures_and_runtime_behaviour(monkeypatch):
    policy_module = import_module("apps.cmdb.services.model_attribute_policy")
    assert isinstance(policy_module, types.ModuleType)

    for method_name in ENUM_POLICY_METHODS:
        assert signature(getattr(ModelManage, method_name)) == signature(getattr(ModelAttributePolicy, method_name))

    assert ModelManage._normalize_default_value(["a", " a ", "b"]) == ["a", "b"]
    assert ModelManage.normalize_enum_public_binding({"attr_type": "str"}) == {"attr_type": "str"}
    ModelManage.validate_enum_rule_immutable(
        {"attr_type": "enum", "enum_rule_type": "custom"},
        {"attr_type": "enum", "enum_rule_type": "custom"},
    )
    with pytest.raises(BaseAppException, match="规则类型不可切换"):
        ModelManage.validate_enum_rule_immutable(
            {"attr_type": "enum", "enum_rule_type": "custom"},
            {"attr_type": "enum", "enum_rule_type": "public_library"},
        )
    assert ModelManage.ensure_enum_select_mode({"attr_type": "enum"})["enum_select_mode"] == "single"
    ModelManage.validate_enum_select_mode_immutable(
        {"attr_type": "enum", "enum_select_mode": "single"},
        {"attr_type": "enum", "enum_select_mode": "single"},
    )
    with pytest.raises(BaseAppException, match="选择模式不可切换"):
        ModelManage.validate_enum_select_mode_immutable(
            {"attr_type": "enum", "enum_select_mode": "single"},
            {"attr_type": "enum", "enum_select_mode": "multiple"},
        )
    assert ModelManage.resolve_runtime_enum_options({"attr_type": "enum", "enum_rule_type": "custom", "option": [{"id": "a"}]}) == [{"id": "a"}]

    monkeypatch.setattr(
        "apps.cmdb.services.public_enum_library.get_library_or_raise",
        lambda _library_id: (_ for _ in ()).throw(RuntimeError("library unavailable")),
    )
    assert ModelManage.resolve_runtime_enum_options(
        {
            "attr_type": "enum",
            "enum_rule_type": "public_library",
            "public_library_id": "missing",
            "option": [{"id": "snapshot"}],
        }
    ) == [{"id": "snapshot"}]


def test_model_manage_old_path_monkeypatch_reaches_extracted_execution(monkeypatch):
    monkeypatch.setattr(ModelManage, "_normalize_default_value", staticmethod(lambda _value: ["patched"]))
    monkeypatch.setattr(
        ModelManage,
        "resolve_runtime_enum_options",
        staticmethod(lambda _attr: [{"id": "patched"}]),
    )

    result = ModelManage.sanitize_attr_default_value({"attr_type": "enum", "default_value": ["ignored"], "enum_select_mode": "single"})

    assert result["default_value"] == ["patched"]


def test_model_manage_old_logger_patch_keeps_failure_fallback_observable(monkeypatch):
    model_module = import_module("apps.cmdb.services.model")
    patched_logger = Mock()
    monkeypatch.setattr(model_module, "logger", patched_logger)
    monkeypatch.setattr(
        "apps.cmdb.services.public_enum_library.get_library_or_raise",
        lambda _library_id: (_ for _ in ()).throw(RuntimeError("library unavailable")),
    )

    result = ModelManage.resolve_runtime_enum_options(
        {
            "attr_type": "enum",
            "enum_rule_type": "public_library",
            "public_library_id": "missing",
            "option": [{"id": "snapshot"}],
        }
    )

    assert result == [{"id": "snapshot"}]
    patched_logger.warning.assert_called_once()
    assert patched_logger.warning.call_args.args == (
        "[EnumPublicBinding] resolve_runtime_enum_options fallback to snapshot, " "public_library_id=missing, error=library unavailable",
    )


def test_legacy_caller_reaches_model_manage_compatibility_facade(monkeypatch):
    options = [{"id": "linux", "name": "Linux"}]
    resolver = Mock(return_value=options)
    monkeypatch.setattr(ModelManage, "resolve_runtime_enum_options", resolver)

    result = NodeMgmtSyncService._host_os_type_options({"os_type": {"attr_type": "enum"}})

    assert result == options
    resolver.assert_called_once_with({"attr_type": "enum"})


def test_model_manage_facade_delegates_to_current_policy(monkeypatch):
    target = {"attr_type": "enum"}
    policy_method = Mock(return_value={**target, "enum_select_mode": "patched"})
    monkeypatch.setattr(ModelAttributePolicy, "ensure_enum_select_mode", policy_method)

    assert ModelManage.ensure_enum_select_mode(target)["enum_select_mode"] == "patched"
    policy_method.assert_called_once_with(target)


def test_extracted_policy_keeps_enum_default_value_behavior():
    attr = {
        "attr_type": "enum",
        "enum_rule_type": "custom",
        "option": [{"id": "a"}, {"id": "b"}],
        "enum_select_mode": "single",
        "default_value": ["a", "b", "missing"],
    }

    result = ModelAttributePolicy.sanitize_attr_default_value(attr)

    assert result["default_value"] == ["a"]
    assert attr["default_value"] == ["a", "b", "missing"]


def test_model_manage_tag_policy_keeps_signatures_and_runtime_behaviour():
    for method_name in TAG_POLICY_METHODS:
        assert signature(getattr(ModelManage, method_name)) == signature(getattr(ModelAttributePolicy, method_name))

    assert ModelAttributePolicy._is_tag_attr({"attr_type": "tag"}) is True
    assert ModelAttributePolicy._is_tag_attr({"attr_id": "tag"}) is True
    assert ModelAttributePolicy._is_tag_attr({"attr_type": "str", "attr_id": "name"}) is False

    ModelAttributePolicy.validate_tag_attr_definition([], {"attr_type": "tag", "attr_id": "tag"})
    with pytest.raises(BaseAppException, match="attr_id 必须固定为 tag"):
        ModelAttributePolicy.validate_tag_attr_definition([], {"attr_type": "tag", "attr_id": "labels"})
    with pytest.raises(BaseAppException, match="单模型最多允许一个 tag 字段"):
        ModelAttributePolicy.validate_tag_attr_definition(
            [{"attr_type": "tag", "attr_id": "tag"}],
            {"attr_type": "tag", "attr_id": "tag"},
        )

    assert ModelAttributePolicy.normalize_tag_field_option([{"key": "env", "value": "prod"}]) == {
        "mode": "free",
        "options": [{"key": "env", "value": "prod"}],
    }


def test_model_manage_tag_facade_delegates_to_current_policy(monkeypatch):
    policy_method = Mock(return_value={"mode": "patched", "options": []})
    monkeypatch.setattr(ModelAttributePolicy, "normalize_tag_field_option", policy_method)

    assert ModelManage.normalize_tag_field_option([]) == {"mode": "patched", "options": []}
    policy_method.assert_called_once_with([])
