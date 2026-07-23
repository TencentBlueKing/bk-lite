"""CMDB 配置文件服务覆盖测试（纯逻辑 helper + DB 读取 + 回调早返分支）。

对照 specs/capabilities/legacy-prd-cmdb-自动发现.md：diff 生成、对象键、版本号归一、内容解码/截断、
实例解析、任务状态汇总、文件清单。MinIO 写入路径(save_content)不在单测范围。
"""

from types import SimpleNamespace

import base64

import pytest

from apps.cmdb.models.config_file_version import ConfigFileVersion, ConfigFileVersionStatus
from apps.cmdb.services.config_file_service import ConfigFileService as S
from apps.core.exceptions.base_app_exception import BaseAppException


def _task(**kw):
    defaults = dict(
        id=1, params={"config_file_path": "/etc/app.conf"}, instances=[],
        collect_data={}, exec_time=None, model_id="host",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


# --------------------------------------------------------------------------
# generate_diff / build_object_key
# --------------------------------------------------------------------------


def test_generate_diff():
    out = S.generate_diff("a\nb\n", "a\nc\n", "v1", "v2")
    assert "v1" in out and "-b" in out and "+c" in out


def test_build_object_key():
    key = S.build_object_key("host", "5", "/etc/app.conf", "1700000000000")
    assert key.startswith("host/5/") and key.endswith("1700000000000.txt")


# --------------------------------------------------------------------------
# _normalize_collect_payload
# --------------------------------------------------------------------------


def test_normalize_payload_not_dict():
    with pytest.raises(BaseAppException):
        S._normalize_collect_payload("x")


def test_normalize_payload_plain():
    out = S._normalize_collect_payload({"a": 1})
    assert out["a"] == 1


def test_normalize_payload_nested():
    out = S._normalize_collect_payload(
        {"config_file_path": "/x/y.conf", "collect_result": {"status": "success", "content_base64": "Zg=="}}
    )
    assert out["status"] == "success"
    assert out["file_path"] == "/x/y.conf"
    assert out["file_name"] == "y.conf"


# --------------------------------------------------------------------------
# _normalize_version / _parse_version_datetime
# --------------------------------------------------------------------------


def test_normalize_version_empty():
    assert S._normalize_version("").isdigit()


def test_normalize_version_seconds_to_millis():
    assert S._normalize_version("1700000000") == "1700000000000"


def test_normalize_version_millis_passthrough():
    assert S._normalize_version("1700000000000") == "1700000000000"


def test_normalize_version_iso():
    out = S._normalize_version("2024-01-01T00:00:00")
    assert out.isdigit()


def test_normalize_version_bad_string():
    assert S._normalize_version("not-a-date").isdigit()


def test_parse_version_datetime_variants():
    assert S._parse_version_datetime("") is None
    assert S._parse_version_datetime("1700000000") is not None
    assert S._parse_version_datetime("1700000000000") is not None
    assert S._parse_version_datetime("2024-01-01T00:00:00") is not None
    assert S._parse_version_datetime("garbage") is None


# --------------------------------------------------------------------------
# _truncate_content_for_storage / _decode_content
# --------------------------------------------------------------------------


def test_truncate_under_limit():
    assert S._truncate_content_for_storage("small", 5, "/a", 1, "5") == "small"


def test_truncate_over_limit():
    big = "x" * (6 * 1024 * 1024)
    out = S._truncate_content_for_storage(big, len(big), "/a", 1, "5")
    assert len(out.encode("utf-8")) <= 5 * 1024 * 1024


def test_decode_content_empty():
    assert S._decode_content("") == ""


def test_decode_content_ok():
    assert S._decode_content(base64.b64encode(b"hello").decode()) == "hello"


def test_decode_content_bad():
    with pytest.raises(BaseAppException):
        S._decode_content("!!!notbase64!!!")


# --------------------------------------------------------------------------
# instance resolution helpers
# --------------------------------------------------------------------------


def test_get_target_instance():
    assert S._get_target_instance(_task(instances=[{"_id": "1"}])) == {"_id": "1"}
    assert S._get_target_instance(_task(instances=[])) == {}
    assert S._get_target_instance(_task(instances=["bad"])) == {}


def test_get_expected_instance_map_and_ids():
    task = _task(instances=[{"_id": "10"}, {"id": "20"}, {"foo": "bar"}, "bad"])
    m = S._get_expected_instance_map(task)
    assert set(m.keys()) == {"10", "20"}
    assert set(S._get_expected_instance_ids(task)) == {"10", "20"}


def test_build_task_instance_name():
    assert S._build_task_instance_name({"ip_addr": "1.2.3.4"}) == "1.2.3.4"
    assert S._build_task_instance_name({"ip_addr": "1.2.3.4", "cloud_id": "c1"}) == "1.2.3.4[c1]"
    assert S._build_task_instance_name({"ip_addr": "1.2.3.4", "inst_name": "1.2.3.4[x]"}) == "1.2.3.4[x]"
    assert S._build_task_instance_name({}) == ""


def test_resolve_task_instance_by_id():
    task = _task(instances=[{"_id": "10", "ip_addr": "1.1.1.1"}])
    rid, inst = S._resolve_task_instance(task, "10")
    assert rid == "10"


def test_resolve_task_instance_by_name():
    task = _task(instances=[{"_id": "10", "ip_addr": "1.1.1.1"}])
    rid, inst = S._resolve_task_instance(task, "1.1.1.1")
    assert rid == "10"


def test_resolve_task_instance_empty():
    assert S._resolve_task_instance(_task(), "") == ("", {})


# --------------------------------------------------------------------------
# _is_stale_callback
# --------------------------------------------------------------------------


def test_is_stale_callback_no_exec_time():
    assert S._is_stale_callback(_task(exec_time=None), "1700000000000") is False


def test_is_stale_callback_true():
    from django.utils.timezone import now, timedelta

    exec_time = now()
    old_version = str(int((exec_time - timedelta(days=1)).timestamp() * 1000))
    assert S._is_stale_callback(_task(exec_time=exec_time), old_version) is True


# --------------------------------------------------------------------------
# _build_summary / build_pending_result
# --------------------------------------------------------------------------


def test_build_summary_pending():
    task = _task(instances=[{"_id": "1"}, {"_id": "2"}])
    summary = S._build_summary(task, items={"1": {"instance_id": "1", "status": ConfigFileVersionStatus.SUCCESS, "changed": True, "version": "100"}})
    assert summary["config_file_data"]["status"] == "pending"
    assert summary["config_file_data"]["pending_count"] == 1


def test_build_summary_success_no_change():
    task = _task(instances=[{"_id": "1"}])
    summary = S._build_summary(task, items={"1": {"instance_id": "1", "status": ConfigFileVersionStatus.SUCCESS, "changed": False, "version": "100"}})
    assert summary["config_file_data"]["status"] == "success"
    assert "无变化" in summary["collect_digest"]["message"]


def test_build_summary_error():
    task = _task(instances=[{"_id": "1"}])
    summary = S._build_summary(task, items={"1": {"instance_id": "1", "status": ConfigFileVersionStatus.ERROR, "changed": False, "version": "100", "error_message": "boom"}})
    assert summary["config_file_data"]["status"] == "error"


def test_build_pending_result():
    task = _task(instances=[{"_id": "1"}])
    config_file, format_data = S.build_pending_result(task)
    assert "config_file" in config_file
    assert format_data["add"] == []


# --------------------------------------------------------------------------
# DB read helpers
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_latest_version_and_file_list():
    ConfigFileVersion.objects.create(
        instance_id="5", model_id="host", version="100", file_path="/a", file_name="a", status="success"
    )
    v2 = ConfigFileVersion.objects.create(
        instance_id="5", model_id="host", version="200", file_path="/a", file_name="a", status="success"
    )
    latest = S.get_latest_version(None, "5", "/a")
    assert latest.id == v2.id

    file_list = S.get_file_list("5")
    assert len(file_list) == 1
    assert file_list[0]["latest_version_id"] == v2.id


@pytest.mark.django_db
def test_get_latest_success_version_none():
    assert S._get_latest_success_version(1, "5", "/a") is None


# --------------------------------------------------------------------------
# process_collect_result 早返分支
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_process_collect_result_missing_task_id():
    with pytest.raises(BaseAppException):
        S.process_collect_result({"status": "success"})


@pytest.mark.django_db
def test_process_collect_result_task_not_found():
    with pytest.raises(BaseAppException):
        S.process_collect_result({"collect_task_id": 999999, "status": "success"})
