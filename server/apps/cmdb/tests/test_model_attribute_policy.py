"""ModelManage 枚举字段策略兼容门面契约。"""

from inspect import signature

from apps.cmdb.services.model import ModelManage

ENUM_POLICY_METHODS = (
    "_normalize_default_value",
    "sanitize_attr_default_value",
    "normalize_enum_public_binding",
    "validate_enum_rule_immutable",
    "ensure_enum_select_mode",
    "validate_enum_select_mode_immutable",
    "resolve_runtime_enum_options",
)


def test_model_manage_enum_policy_uses_extracted_implementation():
    from apps.cmdb.services.model_attribute_policy import ModelAttributePolicy

    for method_name in ENUM_POLICY_METHODS:
        compatibility_method = getattr(ModelManage, method_name)
        policy_method = getattr(ModelAttributePolicy, method_name)

        assert compatibility_method is policy_method
        assert signature(compatibility_method) == signature(policy_method)


def test_extracted_policy_keeps_enum_default_value_behavior():
    from apps.cmdb.services.model_attribute_policy import ModelAttributePolicy

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
