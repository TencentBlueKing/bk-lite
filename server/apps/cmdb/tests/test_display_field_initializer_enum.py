"""DisplayFieldInitializer 多选枚举展示名。

历史初始化应与日常转换一样，用预加载映射逐项查表，而不是把整个 ID 列表拼进一个键。
"""

import pytest

from apps.cmdb.display_field.initializer import DisplayFieldInitializer


def _initializer() -> DisplayFieldInitializer:
    init = DisplayFieldInitializer()
    init._enum_map = {
        "audit_model.state.1": "运行中",
        "audit_model.state.2": "已停止",
    }
    return init


@pytest.mark.django_db
def test_convert_enum_single_unknown_and_empty():
    init = _initializer()
    assert init._convert_enum("audit_model", "state", "1") == "运行中"
    assert init._convert_enum("audit_model", "state", "99") == "99"
    assert init._convert_enum("audit_model", "state", "") == ""
    assert init._convert_enum("audit_model", "state", []) == ""


@pytest.mark.django_db
def test_convert_enum_multi_uses_preloaded_option_names():
    init = _initializer()
    display = init._convert_enum("audit_model", "state", ["1", "2"])
    assert display == "运行中, 已停止"
    assert display != "['1', '2']"
    assert init._convert_enum("audit_model", "state", ["1", "99"]) == "运行中, 99"
    assert init._convert_enum("audit_model", "state", ["1", "", "2"]) == "运行中, 已停止"
    assert init._convert_enum("audit_model", "state", ["1", "2"]) == display


@pytest.mark.django_db
def test_build_display_fields_for_multi_enum_instance():
    init = _initializer()
    display_fields = init._build_display_fields_for_instance(
        {"state": ["1", "2"]},
        [{"attr_id": "state", "attr_type": "enum"}],
        "audit_model",
    )
    assert display_fields["state_display"] == "运行中, 已停止"
