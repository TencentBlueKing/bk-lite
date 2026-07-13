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
import importlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import IntegrityError, OperationalError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
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


def _version_fields(task=None, **kw):
    defaults = {
        "collect_task": task,
        "instance_id": "inst-1",
        "model_id": "host",
        "version": "1700000000000",
        "file_path": "/etc/app.conf",
        "file_name": "app.conf",
        "content_hash": "hash-v1",
        "file_size": 2,
        "status": ConfigFileVersionStatus.SUCCESS,
    }
    defaults.update(kw)
    return defaults


@pytest.mark.django_db
def test_version_business_key_is_unique_for_collect_task():
    task = _make_task()
    ConfigFileVersion.objects.create(**_version_fields(task))

    with pytest.raises(IntegrityError), transaction.atomic():
        ConfigFileVersion.objects.create(**_version_fields(task))


@pytest.mark.django_db
def test_manual_versions_without_collect_task_do_not_conflict():
    ConfigFileVersion.objects.create(**_version_fields())
    ConfigFileVersion.objects.create(**_version_fields())

    assert ConfigFileVersion.objects.filter(collect_task=None, instance_id="inst-1", version="1700000000000").count() == 2


@pytest.mark.django_db
def test_config_file_content_lifecycle_defaults_to_pending():
    version_obj = ConfigFileVersion.objects.create(**_version_fields())

    assert version_obj.content_status == "pending"
    assert version_obj.temp_content_key == ""
    assert version_obj.content_error == ""
    assert version_obj.content_attempt_count == 0
    assert version_obj.content_updated_at is not None


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
def test_same_business_key_and_content_is_idempotent(monkeypatch):
    task = _make_task()
    ver = str(int(now().timestamp() * 1000))
    saved_objects = []

    def fake_save_content(self, text, object_key):
        saved_objects.append((text, object_key))
        self.content.name = object_key

    monkeypatch.setattr(ConfigFileVersion, "save_content", fake_save_content)
    first = S.process_collect_result(_payload(task, version=ver, content_base64=base64.b64encode(b"v1").decode()))
    second = S.process_collect_result(_payload(task, version=ver, content_base64=base64.b64encode(b"v1").decode()))

    assert second["version_obj"].id == first["version_obj"].id
    assert second["changed"] is False
    assert len(saved_objects) == 1
    assert ConfigFileVersion.objects.filter(collect_task=task, version=ver).count() == 1


@pytest.mark.django_db
def test_idempotent_redelivery_returns_exact_business_key_row():
    task = _make_task()
    ver = str(int(now().timestamp() * 1000))
    first = S.process_collect_result(_payload(task, version=ver, content_base64=base64.b64encode(b"v1").decode()))
    ConfigFileVersion.objects.create(
        **_version_fields(
            task,
            version=str(int(ver) + 1),
            content_hash=first["version_obj"].content_hash,
        ),
        content="host/inst-1/newer.txt",
    )

    repeated = S.process_collect_result(_payload(task, version=ver, content_base64=base64.b64encode(b"v1").decode()))

    assert repeated["version_obj"].id == first["version_obj"].id
    assert repeated["changed"] is False


@pytest.mark.django_db
def test_same_business_key_with_different_content_is_protocol_conflict():
    task = _make_task()
    ver = str(int(now().timestamp() * 1000))
    first = S.process_collect_result(_payload(task, version=ver, content_base64=base64.b64encode(b"v1").decode()))
    original = ConfigFileVersion.objects.get(id=first["version_obj"].id)
    original_fields = (original.content_hash, original.content_key, original.file_size, original.status)

    second = S.process_collect_result(_payload(task, version=ver, content_base64=base64.b64encode(b"v2 longer").decode()))

    assert second["version_obj"] is None
    assert "业务键内容冲突" in second["error"]
    original.refresh_from_db()
    assert (original.content_hash, original.content_key, original.file_size, original.status) == original_fields
    assert ConfigFileVersion.objects.filter(collect_task=task, version=ver).count() == 1
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR


@pytest.mark.django_db
def test_create_or_get_version_reads_concurrent_winner_after_integrity_error(mocker):
    task = _make_task()
    existing = ConfigFileVersion(
        **_version_fields(task, content_hash="same-hash"),
    )
    filter_result = mocker.Mock()
    filter_result.first.return_value = None
    mocker.patch.object(ConfigFileVersion.objects, "filter", return_value=filter_result)
    mocker.patch.object(ConfigFileVersion.objects, "create", side_effect=IntegrityError("duplicate"))
    mocker.patch.object(ConfigFileVersion.objects, "get", return_value=existing)

    version_obj, created = S._create_or_get_version(
        task=task,
        instance_id="inst-1",
        version="1700000000000",
        model_id="host",
        file_path="/etc/app.conf",
        file_name="app.conf",
        status=ConfigFileVersionStatus.SUCCESS,
        file_size=2,
        error_message="",
        content_hash="same-hash",
        text_content="v1",
    )

    assert version_obj is existing
    assert created is False
    ConfigFileVersion.objects.get.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_concurrent_business_key_commits_only_one_row():
    task = _make_task()
    barrier = threading.Barrier(2)

    def create_version():
        close_old_connections()
        barrier.wait()
        try:
            for attempt in range(3):
                try:
                    ConfigFileVersion.objects.create(**_version_fields(task))
                    return "created"
                except IntegrityError:
                    return "duplicate"
                except OperationalError:
                    if attempt == 2:
                        return "locked"
                    time.sleep(0.05)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: create_version(), range(2)))

    assert ConfigFileVersion.objects.filter(
        collect_task=task,
        instance_id="inst-1",
        version="1700000000000",
    ).count() == 1
    assert "created" in outcomes


@pytest.mark.django_db(transaction=True)
def test_dedupe_migration_keeps_earliest_record():
    executor = MigrationExecutor(connection)
    old_target = [("cmdb", "0031_subscriptiondelivery")]
    new_target = [("cmdb", "0033_config_file_content_lifecycle")]
    executor.migrate(old_target)
    try:
        old_apps = executor.loader.project_state(old_target).apps
        historical_task = old_apps.get_model("cmdb", "CollectModels").objects.create(
            name="migration-task",
            task_type="host",
            model_id="host",
            cycle_value_type="close",
        )
        historical_version = old_apps.get_model("cmdb", "ConfigFileVersion")
        first = historical_version.objects.create(**_version_fields(historical_task))
        second = historical_version.objects.create(**_version_fields(historical_task))
        historical_version.objects.filter(id=first.id).update(created_at=now())
        historical_version.objects.filter(id=second.id).update(created_at=now() - timedelta(seconds=1))

        migration_module = importlib.import_module("apps.cmdb.migrations.0032_dedupe_config_file_versions")
        migration_module.dedupe_config_file_versions(old_apps, None)

        assert not historical_version.objects.filter(id=first.id).exists()
        assert historical_version.objects.filter(id=second.id).exists()
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(new_target)


@pytest.mark.django_db(transaction=True)
def test_content_lifecycle_migration_classifies_existing_versions():
    executor = MigrationExecutor(connection)
    old_target = [("cmdb", "0032_dedupe_config_file_versions")]
    new_target = [("cmdb", "0033_config_file_content_lifecycle")]
    executor.migrate(old_target)
    try:
        old_apps = executor.loader.project_state(old_target).apps
        historical_task = old_apps.get_model("cmdb", "CollectModels").objects.create(
            name="content-migration-task",
            task_type="host",
            model_id="host",
            cycle_value_type="close",
        )
        historical_version = old_apps.get_model("cmdb", "ConfigFileVersion")
        ready = historical_version.objects.create(
            **_version_fields(historical_task, version="1700000000001"),
            content="host/inst-1/ready.txt",
        )
        missing = historical_version.objects.create(
            **_version_fields(historical_task, version="1700000000002"),
        )

        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        migrated_version = new_apps.get_model("cmdb", "ConfigFileVersion")

        assert migrated_version.objects.get(id=ready.id).content_status == "ready"
        missing_version = migrated_version.objects.get(id=missing.id)
        assert missing_version.content_status == "error"
        assert missing_version.content_error == "历史配置版本缺少正文对象"
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
