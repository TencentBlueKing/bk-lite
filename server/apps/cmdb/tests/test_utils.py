"""CMDB 工具函数覆盖测试。

对照 spec/prd/CMDB：组织参数格式化、时间解析、配置文件路径校验、订阅展示工具。
"""

from datetime import date, datetime, time
from types import SimpleNamespace

import pytest

from apps.cmdb.utils import base as base_util
from apps.cmdb.utils import config_file_path as cfp
from apps.cmdb.utils import subscription_utils as su
from apps.cmdb.utils import time_util as tu
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# base.py
# --------------------------------------------------------------------------


def test_format_group_params():
    assert base_util.format_group_params("5") == [{"id": 5}]


def test_format_groups_params_dedup():
    out = base_util.format_groups_params([1, 1, 2])
    ids = sorted(g["id"] for g in out)
    assert ids == [1, 2]


def test_get_cmdb_rules_ok():
    request = SimpleNamespace(user=SimpleNamespace(rules={"cmdb": {"normal": {"task": {"r": 1}}}}))
    assert base_util.get_cmdb_rules(request, "task") == {"r": 1}


def test_get_cmdb_rules_exception_returns_empty():
    request = SimpleNamespace(user=SimpleNamespace(rules=None))
    assert base_util.get_cmdb_rules(request) == {}


def test_get_organization_and_children_ids():
    tree = [{"id": 1, "subGroups": [{"id": 2, "subGroups": [{"id": 3}]}, {"id": 4}]}]
    assert set(base_util.get_organization_and_children_ids(tree, 1)) == {1, 2, 3, 4}
    assert base_util.get_organization_and_children_ids(tree, 99) == []


def test_get_current_team_from_request_ok():
    request = SimpleNamespace(COOKIES={"current_team": "7"})
    assert base_util.get_current_team_from_request(request) == 7


def test_get_current_team_missing_required_raises():
    request = SimpleNamespace(COOKIES={})
    with pytest.raises(BaseAppException):
        base_util.get_current_team_from_request(request, required=True)


def test_get_current_team_missing_not_required_zero():
    request = SimpleNamespace(COOKIES={})
    assert base_util.get_current_team_from_request(request, required=False) == 0


def test_get_current_team_invalid_raises():
    request = SimpleNamespace(COOKIES={"current_team": "abc"})
    with pytest.raises(BaseAppException):
        base_util.get_current_team_from_request(request)


# --------------------------------------------------------------------------
# time_util.py
# --------------------------------------------------------------------------


def test_excel_serial_to_datetime():
    dt = tu.excel_serial_to_datetime(0)
    assert dt.year == 1899


def test_parse_cmdb_time_datetime():
    now = datetime(2026, 1, 1, 10, 0, 0)
    assert tu.parse_cmdb_time(now).startswith("2026-01-01T10:00:00")


def test_parse_cmdb_time_date():
    assert tu.parse_cmdb_time(date(2026, 1, 1)).startswith("2026-01-01")


def test_parse_cmdb_time_iso_string():
    assert tu.parse_cmdb_time("2026-01-01 10:00:00").startswith("2026-01-01T10:00:00")


def test_parse_cmdb_time_common_format():
    assert tu.parse_cmdb_time("2026/01/01").startswith("2026-01-01")


def test_parse_cmdb_time_empty_raises():
    with pytest.raises(ValueError):
        tu.parse_cmdb_time("")


def test_parse_cmdb_time_unsupported_type_raises():
    with pytest.raises(ValueError):
        tu.parse_cmdb_time([1, 2])


def test_parse_cmdb_time_numeric_excel():
    assert tu.parse_cmdb_time(40000).startswith("20")


# --------------------------------------------------------------------------
# config_file_path.py
# --------------------------------------------------------------------------


def test_validate_absolute_path_linux():
    assert cfp.validate_absolute_path("/etc/app/config.yaml") is True


def test_validate_absolute_path_windows():
    assert cfp.validate_absolute_path("C:\\app\\config.yaml") is True


def test_validate_absolute_path_rejects_relative():
    assert cfp.validate_absolute_path("config.yaml") is False


def test_validate_absolute_path_rejects_glob():
    assert cfp.validate_absolute_path("/etc/*.yaml") is False


def test_validate_absolute_path_rejects_dir():
    assert cfp.validate_absolute_path("/etc/app/") is False


def test_validate_absolute_path_rejects_empty():
    assert cfp.validate_absolute_path("") is False
    assert cfp.validate_absolute_path(None) is False


def test_extract_file_name_linux():
    assert cfp.extract_file_name("/etc/app/config.yaml") == "config.yaml"


def test_extract_file_name_windows():
    assert cfp.extract_file_name("C:\\app\\config.yaml") == "config.yaml"


def test_extract_file_name_empty():
    assert cfp.extract_file_name("") == ""


# --------------------------------------------------------------------------
# subscription_utils.py
# --------------------------------------------------------------------------


def test_truncate_value_none():
    assert su.truncate_value(None) == "(空)"


def test_truncate_value_short():
    assert su.truncate_value("abc") == "abc"


def test_truncate_value_long():
    out = su.truncate_value("x" * 100, max_length=10)
    assert out.endswith("...")
    assert len(out) == 10


def test_get_inst_display_name_inst_name():
    assert su.get_inst_display_name({"inst_name": "host1"}) == "host1"


def test_get_inst_display_name_ip_fallback():
    assert su.get_inst_display_name({"ip_addr": "10.0.0.1"}) == "10.0.0.1"


def test_get_inst_display_name_fallback_id():
    assert su.get_inst_display_name(None, fallback_id=5) == "5"


def test_get_inst_display_name_unknown():
    assert su.get_inst_display_name(None) == "(未知)"


def test_check_subscription_manage_permission_empty_team():
    assert su.check_subscription_manage_permission(1, None) is False
    assert su.check_subscription_manage_permission(1, "") is False


def test_check_subscription_manage_permission_invalid_team():
    assert su.check_subscription_manage_permission(1, "abc") is False
