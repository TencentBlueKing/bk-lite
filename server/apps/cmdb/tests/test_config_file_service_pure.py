"""CMDB 配置文件服务与公共枚举库纯逻辑覆盖测试。

对照 spec/prd/CMDB·资产：配置文件版本归一/差异、采集回调解码；枚举库选项校验。
"""

import base64
import datetime

import pytest

from apps.cmdb.services.config_file_service import ConfigFileService
from apps.cmdb.services.public_enum_library import _generate_library_id, _validate_options
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# ConfigFileService 纯方法
# --------------------------------------------------------------------------


def test_generate_diff():
    diff = ConfigFileService.generate_diff("a\nb\n", "a\nc\n", "v1", "v2")
    assert "v1" in diff and "v2" in diff
    assert "-b" in diff and "+c" in diff


def test_build_object_key():
    key = ConfigFileService.build_object_key("host", "10", "/etc/app.conf", "1700000000")
    assert key.startswith("host/10/")
    assert key.endswith("1700000000.txt")


def test_decode_content_ok():
    encoded = base64.b64encode("hello".encode("utf-8")).decode()
    assert ConfigFileService._decode_content(encoded) == "hello"


def test_decode_content_empty():
    assert ConfigFileService._decode_content("") == ""


def test_decode_content_bad():
    with pytest.raises(BaseAppException):
        ConfigFileService._decode_content("not!!base64!!")


def test_normalize_version_empty_returns_timestamp():
    out = ConfigFileService._normalize_version("")
    assert out.isdigit()


def test_normalize_version_seconds_to_millis():
    assert ConfigFileService._normalize_version("1700000000") == "1700000000000"


def test_normalize_version_millis_kept():
    assert ConfigFileService._normalize_version("1700000000000") == "1700000000000"


def test_parse_version_datetime_millis():
    dt = ConfigFileService._parse_version_datetime("1700000000000")
    assert isinstance(dt, datetime.datetime)


def test_parse_version_datetime_empty():
    assert ConfigFileService._parse_version_datetime("") is None


def test_parse_version_datetime_invalid():
    assert ConfigFileService._parse_version_datetime("not-a-version") is None


def test_truncate_content_small_unchanged():
    out = ConfigFileService._truncate_content_for_storage("small", 5, "/etc/x", 1, "i1")
    assert out == "small"


def test_normalize_collect_payload_nested():
    data = {"collect_result": {"content": "x"}, "config_file_path": "/etc/app.conf"}
    out = ConfigFileService._normalize_collect_payload(data)
    assert out["content"] == "x"
    assert out["file_path"] == "/etc/app.conf"


def test_normalize_collect_payload_bad_type():
    with pytest.raises(BaseAppException):
        ConfigFileService._normalize_collect_payload("notadict")


def test_get_target_instance_empty():
    from types import SimpleNamespace

    assert ConfigFileService._get_target_instance(SimpleNamespace(instances=None)) == {}
    assert ConfigFileService._get_target_instance(SimpleNamespace(instances=[{"a": 1}])) == {"a": 1}


# --------------------------------------------------------------------------
# public_enum_library 纯函数
# --------------------------------------------------------------------------


def test_generate_library_id():
    lib_id = _generate_library_id()
    assert lib_id.startswith("lib_")


def test_validate_options_ok():
    _validate_options([{"id": "a", "name": "A"}, {"id": "b", "name": "B"}])


def test_validate_options_not_list():
    with pytest.raises(BaseAppException):
        _validate_options("x")


def test_validate_options_bad_item():
    with pytest.raises(BaseAppException):
        _validate_options(["notadict"])


def test_validate_options_missing_id():
    with pytest.raises(BaseAppException):
        _validate_options([{"name": "A"}])


def test_validate_options_duplicate_id():
    with pytest.raises(BaseAppException):
        _validate_options([{"id": "a", "name": "A"}, {"id": "a", "name": "B"}])
