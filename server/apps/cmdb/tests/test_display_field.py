"""CMDB 显示字段转换器覆盖测试。

对照 specs/capabilities/legacy-prd-cmdb-资产.md：organization/user/enum/tag/table 字段值转为可检索显示名。
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
# convert_file（附件/图片 → 文件名词干，去路径去扩展名）纯函数
# --------------------------------------------------------------------------


def test_convert_file_single_strips_extension():
    val = [{"name": "report.pdf", "url": "http://x/minio/abc", "id": 1, "size": 1024}]
    out = DisplayFieldConverter.convert_file(val)
    assert out == "report"
    assert "pdf" not in out and "minio" not in out


def test_convert_file_multiple_joined():
    val = [{"name": "logo.png"}, {"name": "banner.jpg"}]
    assert DisplayFieldConverter.convert_file(val) == "logo, banner"


def test_convert_file_strips_directory_path():
    assert DisplayFieldConverter.convert_file([{"name": "reports/2026/年度报表.xlsx"}]) == "年度报表"


def test_convert_file_strips_windows_path():
    assert DisplayFieldConverter.convert_file([{"name": "C:\\dir\\sub\\file.txt"}]) == "file"


def test_convert_file_compound_extension_strips_last_only():
    assert DisplayFieldConverter.convert_file([{"name": "archive.tar.gz"}]) == "archive.tar"


def test_convert_file_no_extension_kept():
    assert DisplayFieldConverter.convert_file([{"name": "README"}]) == "README"


def test_convert_file_empty_inputs():
    assert DisplayFieldConverter.convert_file(None) == ""
    assert DisplayFieldConverter.convert_file("") == ""
    assert DisplayFieldConverter.convert_file([]) == ""


def test_convert_file_json_string_input():
    assert DisplayFieldConverter.convert_file('[{"name": "x.pdf"}]') == "x"


def test_convert_file_unparseable_returns_empty_not_raw():
    # 解析失败必须返回 ""，不能把原始 JSON/URL 灌进可搜索索引
    assert DisplayFieldConverter.convert_file("{bad json") == ""


def test_convert_file_item_without_name_skipped():
    val = [{"url": "http://x"}, {"name": "real.doc"}]
    assert DisplayFieldConverter.convert_file(val) == "real"


# --------------------------------------------------------------------------
# build_display_fields 识别文件类型（attachment/image）
# --------------------------------------------------------------------------


@pytest.fixture
def fake_file_ext():
    """注册一个把 attachment/image 视为文件型的假企业扩展，测试后还原。"""
    from apps.cmdb.extensions import registry

    prev = registry.get("model_ops")

    class _Ext:
        def file_attr_types(self):
            return {"attachment", "image"}

    registry.register("model_ops", _Ext())
    try:
        yield
    finally:
        if prev is None:
            registry._registry.pop("model_ops", None)
        else:
            registry.register("model_ops", prev)


def test_build_display_fields_file_type(fake_file_ext):
    attrs = [{"attr_id": "doc", "attr_type": "attachment"}]
    data = {"inst_name": "h1", "doc": [{"name": "report.pdf", "url": "http://x/minio/abc"}]}
    out = DisplayFieldHandler.build_display_fields("host", data, attrs)
    assert out["doc_display"] == "report"


def test_build_display_fields_file_parse_failure_empty(fake_file_ext):
    attrs = [{"attr_id": "doc", "attr_type": "attachment"}]
    data = {"inst_name": "h1", "doc": "{bad json"}
    out = DisplayFieldHandler.build_display_fields("host", data, attrs)
    # 降级为 "" 而非原始 JSON，避免污染全文索引
    assert out["doc_display"] == ""


def test_build_display_fields_image_type(fake_file_ext):
    attrs = [{"attr_id": "pic", "attr_type": "image"}]
    data = {"inst_name": "h1", "pic": [{"name": "topo.png"}]}
    out = DisplayFieldHandler.build_display_fields("host", data, attrs)
    assert out["pic_display"] == "topo"


def test_build_display_fields_no_file_ext_community():
    # 社区无企业版：is_file_attr_type 恒 False → 不产出文件类 _display
    # 本环境装有 cmdb_enterprise，需显式摘除 model_ops 槽位以模拟社区部署
    from apps.cmdb.extensions import registry

    prev = registry.get("model_ops")
    registry._registry.pop("model_ops", None)
    try:
        attrs = [{"attr_id": "doc", "attr_type": "attachment"}]
        data = {"inst_name": "h1", "doc": [{"name": "report.pdf"}]}
        out = DisplayFieldHandler.build_display_fields("host", data, attrs)
        assert "doc_display" not in out
    finally:
        if prev is not None:
            registry.register("model_ops", prev)


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


# --------------------------------------------------------------------------
# 全文检索排除链路 + 全字段类型完整性
# （本环境装有 cmdb_enterprise，is_file_attr_type('attachment') 为真）
# --------------------------------------------------------------------------


def test_exclude_fields_excludes_raw_file_but_not_display():
    """展示型字段排除原值但保留 _display；附件型仅在装有企业版时才排除。

    社区 worktree 无 attachment 文件类型（file_attr_types() 为空集），故附件断言
    需按当前部署能力分支，避免在社区误判。
    """
    import json

    from apps.cmdb.display_field.cache import ExcludeFieldsCache
    from apps.cmdb.model_ops.extensions import file_attr_types

    models = [
        {
            "model_id": "host",
            "attrs": json.dumps(
                [
                    {"attr_id": "inst_name", "attr_type": "str"},
                    {"attr_id": "doc", "attr_type": "attachment"},
                    {"attr_id": "status", "attr_type": "enum"},
                ]
            ),
        }
    ]
    exclude = ExcludeFieldsCache._build_exclude_fields(models)

    # 展示型字段（enum）被排除，普通 str 字段不排除
    assert "status" in exclude
    assert "inst_name" not in exclude
    # 冗余 _display 字段绝不能被排除 —— 否则展示名词干仍搜不到
    assert "status_display" not in exclude

    # 附件型：仅当部署支持 attachment（企业版）时原值才排除，且 _display 绝不排除
    if "attachment" in file_attr_types():
        assert "doc" in exclude
        assert "doc_display" not in exclude
    else:
        # 社区版无 attachment 文件类型，doc 不被识别为文件字段 → 不排除
        assert "doc" not in exclude


def test_every_excluded_type_has_display_generator():
    """完整性不变量：凡被全文检索「排除」的字段类型，build_display_fields 必为其产出 `_display`。

    否则该类型会「被排除却无可搜索冗余兜底」—— 正是 attachment/image 曾经的缺陷。
    排除集 = DISPLAY_FIELD_TYPES ∪ file_attr_types()，二者必须被 build_display_fields 全覆盖。
    用空值触发各转换器早返回，避免 organization/user 走 DB。
    """
    from apps.cmdb.display_field.constants import DISPLAY_FIELD_TYPES
    from apps.cmdb.model_ops.extensions import file_attr_types

    file_types = set(file_attr_types())
    excluded_types = set(DISPLAY_FIELD_TYPES) | file_types
    # 装有 enterprise 时文件型必含 attachment/image；社区版 file_attr_types() 为空集。
    if file_types:
        assert {"attachment", "image"} <= excluded_types
    # 不变量对「当前部署实际排除的全部类型」都必须成立（社区/企业均覆盖）。

    for attr_type in sorted(excluded_types):
        attrs = [{"attr_id": "f", "attr_type": attr_type, "option": []}]
        out = DisplayFieldHandler.build_display_fields("m", {"f": []}, attrs)
        assert "f_display" in out, f"被排除类型 {attr_type!r} 未生成 _display → 全文检索盲区"


def test_exclude_fields_excludes_pwd_type_without_display():
    """密码(pwd)类型：值为密文，应排除出全文检索，且不产出可搜索 _display。"""
    import json

    from apps.cmdb.display_field.cache import ExcludeFieldsCache

    models = [
        {
            "model_id": "host",
            "attrs": json.dumps(
                [
                    {"attr_id": "name", "attr_type": "str"},
                    {"attr_id": "secret", "attr_type": "pwd"},
                ]
            ),
        }
    ]
    exclude = ExcludeFieldsCache._build_exclude_fields(models)
    assert "secret" in exclude  # 密文原值排除出索引
    assert "name" not in exclude
    assert "secret_display" not in exclude  # pwd 无可搜索冗余（刻意不可搜索）


def test_build_display_fields_skips_pwd():
    """pwd 不属展示型/文件型，build_display_fields 不应为其产出 _display。"""
    attrs = [{"attr_id": "secret", "attr_type": "pwd"}]
    out = DisplayFieldHandler.build_display_fields("host", {"secret": "ciphertext=="}, attrs)
    assert "secret_display" not in out


def test_readable_types_not_excluded_searchable_directly():
    """可读原值类型（str/int/bool/time）不应被排除：其原始值本就可被全文检索命中。"""
    import json

    from apps.cmdb.display_field.cache import ExcludeFieldsCache

    models = [
        {
            "model_id": "host",
            "attrs": json.dumps(
                [
                    {"attr_id": "name", "attr_type": "str"},
                    {"attr_id": "cpu", "attr_type": "int"},
                    {"attr_id": "enabled", "attr_type": "bool"},
                    {"attr_id": "created_at", "attr_type": "time"},
                ]
            ),
        }
    ]
    exclude = ExcludeFieldsCache._build_exclude_fields(models)
    for fid in ("name", "cpu", "enabled", "created_at"):
        assert fid not in exclude
