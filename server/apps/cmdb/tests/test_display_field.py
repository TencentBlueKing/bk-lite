"""CMDB 显示字段转换器覆盖测试。

对照 spec/prd/CMDB·资产：organization/user/enum/tag/table 字段值转为可检索显示名。
"""

import pytest

from apps.cmdb.display_field.handler import DisplayFieldConverter, DisplayFieldHandler


# --------------------------------------------------------------------------
# convert_enum / convert_tag / convert_table（纯函数）
# --------------------------------------------------------------------------


def test_convert_enum_empty():
    assert DisplayFieldConverter.convert_enum("", []) == ""


def test_convert_enum_no_options():
    assert DisplayFieldConverter.convert_enum("1", None) == "1"
    assert DisplayFieldConverter.convert_enum(["1", "2"], None) == "1, 2"


def test_convert_enum_single():
    opts = [{"id": "1", "name": "运行中"}, {"id": "2", "name": "已停止"}]
    assert DisplayFieldConverter.convert_enum("1", opts) == "运行中"


def test_convert_enum_multi():
    opts = [{"id": "1", "name": "运行中"}, {"id": "2", "name": "已停止"}]
    assert DisplayFieldConverter.convert_enum(["1", "2"], opts) == "运行中, 已停止"


def test_convert_enum_unknown_id():
    opts = [{"id": "1", "name": "A"}]
    assert DisplayFieldConverter.convert_enum("99", opts) == "99"


def test_convert_tag_empty():
    assert DisplayFieldConverter.convert_tag([]) == ""


def test_convert_tag_list():
    assert DisplayFieldConverter.convert_tag(["env:prod", " app:web "]) == "env:prod, app:web"


def test_convert_tag_non_list():
    assert DisplayFieldConverter.convert_tag("single") == "single"


def test_convert_table_empty():
    assert DisplayFieldConverter.convert_table([]) == ""


def test_convert_table_list():
    out = DisplayFieldConverter.convert_table([{"name": "disk-a", "size": 100}])
    assert "disk-a" in out and "100" in out


def test_convert_table_json_string():
    out = DisplayFieldConverter.convert_table('[{"name": "a"}]')
    assert "a" in out


def test_convert_table_bad_string():
    assert DisplayFieldConverter.convert_table("{bad") == "{bad"


# --------------------------------------------------------------------------
# convert_organization / convert_user（DB）
# --------------------------------------------------------------------------


def test_convert_organization_empty():
    assert DisplayFieldConverter.convert_organization([]) == ""


@pytest.mark.django_db
def test_convert_organization_with_groups():
    from apps.system_mgmt.models.user import Group

    g = Group.objects.create(name="技术部")
    assert "技术部" in DisplayFieldConverter.convert_organization([g.id])


def test_convert_user_empty():
    assert DisplayFieldConverter.convert_user([]) == ""


@pytest.mark.django_db
def test_convert_user_with_display():
    from apps.system_mgmt.models.user import User

    u = User.objects.create(username="u1", display_name="用户1", domain="domain.com")
    assert DisplayFieldConverter.convert_user([u.id]) == "用户1(u1)"


# --------------------------------------------------------------------------
# DisplayFieldHandler
# --------------------------------------------------------------------------


def test_remove_display_fields():
    data = {"name": "h1", "organization": [1], "organization_display": "技术部"}
    out = DisplayFieldHandler.remove_display_fields(data)
    assert "organization_display" not in out
    assert "organization" in out


def test_get_exclude_fields_from_attrs():
    attrs = [
        {"attr_id": "inst_name", "attr_type": "str"},
        {"attr_id": "organization", "attr_type": "organization"},
        {"attr_id": "status", "attr_type": "enum"},
    ]
    out = DisplayFieldHandler.get_exclude_fields_from_attrs(attrs)
    assert "organization" in out
    assert "status" in out
    assert "inst_name" not in out
