# -*- coding: utf-8 -*-
"""ConfigFileService.process_collect_result DB 端到端测试。

真实 CollectModels / ConfigFileVersion DB 副作用；仅在 MinIO 边界打桩
（save_content -> 设置 content.name 为对象键，不写真实对象存储）。
覆盖：成功+变更（新建版本 + 任务生命周期汇总）、内容未变（去重早返）、
失败状态（不建版本、任务标记 error）、过期回调忽略、实例不属于任务报错、
处理异常闭环。
"""
import pydantic.root_model  # noqa: F401  预热
import base64

import pytest
from django.utils.timezone import now, timedelta

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.config_file_version import ConfigFileVersion, ConfigFileVersionStatus
from apps.cmdb.services.config_file_service import ConfigFileService as S
from apps.core.exceptions.base_app_exception import BaseAppException


@pytest.fixture(autouse=True)
def _stub_minio(monkeypatch):
    """save_content 不写 MinIO，仅把对象键记到 content.name 让 content/content_key 真实可用。"""

    def fake_save_content(self, text, object_key):
        # 真实 FieldFile.name 赋值即可让 bool(content) 为真、content_key 返回键
        self.content.name = object_key
        self._fake_text = text

    monkeypatch.setattr(ConfigFileVersion, "save_content", fake_save_content)


def _make_task(**kw):
    defaults = dict(
        name="cfg-task",
        task_type="host",
        model_id="host",
        cycle_value_type="close",
        instances=[{"_id": "inst-1", "ip_addr": "10.0.0.1", "inst_name": "10.0.0.1"}],
        params={"config_file_path": "/etc/app.conf", "config_file_name": "app.conf"},
        exec_time=now() - timedelta(hours=1),
        exec_status=CollectRunStatusType.RUNNING,
        task_id="execution-current",
    )
    defaults.update(kw)
    return CollectModels.objects.create(**defaults)


def _payload(task, **kw):
    base = dict(
        collect_task_id=task.id,
        execution_id=task.task_id,
        instance_id="inst-1",
        status="success",
        version=str(int(now().timestamp() * 1000)),
        content_base64=base64.b64encode(b"server { listen 80; }").decode(),
        file_path="/etc/app.conf",
        file_name="app.conf",
    )
    base.update(kw)
    return base


@pytest.mark.django_db
def test_success_creates_version_and_updates_task():
    task = _make_task()
    result = S.process_collect_result(_payload(task))

    assert result["changed"] is True
    assert result["task_updated"] is True
    version_obj = result["version_obj"]
    assert version_obj is not None
    assert version_obj.status == ConfigFileVersionStatus.SUCCESS
    assert version_obj.content_hash  # 已计算哈希
    assert version_obj.content_key.endswith(".txt")  # 对象键已落到 content

    # DB 真实落库
    assert ConfigFileVersion.objects.filter(collect_task=task, instance_id="inst-1").count() == 1

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.SUCCESS
    cf = task.collect_data["config_file"]
    assert cf["success_count"] == 1
    assert cf["changed_count"] == 1
    assert cf["items"]["inst-1"]["status"] == ConfigFileVersionStatus.SUCCESS
    assert task.format_data["add"][0]["_status"] == "success"


@pytest.mark.django_db
def test_unchanged_content_does_not_create_new_version():
    task = _make_task()
    content = base64.b64encode(b"same content").decode()
    first = S.process_collect_result(_payload(task, content_base64=content, version="1700000000000"))
    assert first["changed"] is True

    # 相同内容、更新版本号 -> content_hash 相同 -> 不新建
    second = S.process_collect_result(_payload(task, content_base64=content, version="1700000001000"))
    assert second["changed"] is False
    assert second["version_obj"].id == first["version_obj"].id
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 1


@pytest.mark.django_db
def test_failed_status_marks_task_error_no_version():
    task = _make_task()
    result = S.process_collect_result(
        _payload(task, status="file_not_found", content_base64="", error="文件不存在")
    )
    assert result["version_obj"] is None
    assert result["changed"] is False
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 0

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR
    item = task.collect_data["config_file"]["items"]["inst-1"]
    assert item["status"] == ConfigFileVersionStatus.FILE_NOT_FOUND
    assert item["error_message"] == "文件不存在"


@pytest.mark.django_db
def test_stale_callback_is_ignored():
    # exec_time 在未来 -> 回调版本时间早于 exec_time -> 视为过期，task_updated False
    task = _make_task(exec_time=now() + timedelta(days=1))
    result = S.process_collect_result(_payload(task, status="file_not_found", content_base64=""))
    assert result["task_updated"] is False
    task.refresh_from_db()
    # 过期回调不改任务状态
    assert task.exec_status == CollectRunStatusType.RUNNING


@pytest.mark.django_db
def test_missing_execution_id_is_rejected_without_side_effects():
    task = _make_task()
    payload = _payload(task)
    payload.pop("execution_id")

    result = S.process_collect_result(payload)

    assert result["stale"] is True
    assert result["task_updated"] is False
    assert "execution ID" in result["error"]
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 0
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.RUNNING


@pytest.mark.django_db
def test_stale_execution_id_does_not_create_version_or_update_task():
    task = _make_task()

    result = S.process_collect_result(_payload(task, execution_id="execution-old"))

    assert result["stale"] is True
    assert result["task_updated"] is False
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 0
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.RUNNING
    assert task.collect_data == {}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "terminal_status",
    [
        CollectRunStatusType.SUCCESS,
        CollectRunStatusType.ERROR,
        CollectRunStatusType.TIME_OUT,
        CollectRunStatusType.FORCE_STOP,
    ],
)
def test_terminal_task_rejects_late_callback(terminal_status):
    task = _make_task(exec_status=terminal_status)

    result = S.process_collect_result(_payload(task))

    assert result["stale"] is True
    assert result["task_updated"] is False
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 0
    task.refresh_from_db()
    assert task.exec_status == terminal_status


@pytest.mark.django_db
def test_instance_not_in_task_raises_and_closes():
    task = _make_task()
    # 实例标识不在任务 instances 中 -> _get_task_instance_or_raise 抛错 -> 异常闭环
    result = S.process_collect_result(_payload(task, instance_id="not-exist"))
    assert result["version_obj"] is None
    assert "error" in result
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR


@pytest.mark.django_db
def test_missing_instance_identifier_closes_task():
    task = _make_task()
    payload = _payload(task)
    payload.pop("instance_id")
    result = S.process_collect_result(payload)
    assert result["version_obj"] is None
    assert "error" in result


@pytest.mark.django_db
def test_version_reused_updates_fields():
    # 同 task+instance+version 重复回调（内容不同）-> get_or_create 命中后更新字段
    task = _make_task()
    ver = str(int(now().timestamp() * 1000))
    first = S.process_collect_result(_payload(task, version=ver, content_base64=base64.b64encode(b"v1").decode()))
    second = S.process_collect_result(_payload(task, version=ver, content_base64=base64.b64encode(b"v2 longer").decode()))
    # 同 version 复用同一行
    assert second["version_obj"].id == first["version_obj"].id
    assert second["changed"] is True
    second["version_obj"].refresh_from_db()
    assert second["version_obj"].content_hash != ""
    assert ConfigFileVersion.objects.filter(collect_task=task, version=ver).count() == 1
