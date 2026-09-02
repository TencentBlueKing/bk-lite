# -*- coding: utf-8 -*-
"""ConfigFileService.process_collect_result DB 端到端测试。

真实 CollectModels / ConfigFileVersion DB 副作用；仅在 MinIO 边界打桩
（save_content -> 设置 content.name 为对象键，不写真实对象存储）。
覆盖：成功+变更（新建版本 + 任务生命周期汇总）、内容未变（去重早返）、
    失败状态（不建版本、任务标记 error）、周期回调幂等与过期结果忽略、实例不属于任务报错、
处理异常闭环。
"""
import base64
import importlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pydantic.root_model  # noqa: F401  预热
import pytest
from django.db import IntegrityError, OperationalError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils.timezone import now, timedelta

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.config_file_version import ConfigFileVersion, ConfigFileVersionStatus
from apps.cmdb.services.config_file_content_lifecycle import ConfigFileContentLifecycle
from apps.cmdb.services.config_file_service import ConfigFileService as S


@pytest.fixture(autouse=True)
def _stub_minio(monkeypatch):
    """不写 MinIO；模拟临时上传与提交后发布。"""

    monkeypatch.setattr(
        ConfigFileContentLifecycle,
        "stage_content",
        staticmethod(lambda _text: "tmp/config-file/test.txt"),
    )
    monkeypatch.setattr(ConfigFileContentLifecycle, "discard_temp_content", staticmethod(lambda _key: None))

    def fake_publish(version_id):
        ConfigFileVersion.objects.filter(id=version_id).update(
            content_status="ready",
            temp_content_key="",
            content_error="",
        )
        return True

    monkeypatch.setattr(ConfigFileContentLifecycle, "publish_version", staticmethod(fake_publish))


def _make_task(**kw):
    defaults = dict(
        name="cfg-task",
        task_type="config_file",
        model_id="config_file",
        cycle_value_type="cycle",
        cycle_value="10",
        is_interval=True,
        instances=[
            {
                "_id": "inst-1",
                "inst_uuid": "123e4567-e89b-42d3-a456-426614174000",
                "ip_addr": "10.0.0.1",
                "inst_name": "10.0.0.1",
            }
        ],
        params={"config_file_path": "/etc/app.conf", "config_file_name": "app.conf"},
        exec_time=None,
        exec_status=CollectRunStatusType.NOT_START,
        task_id=None,
    )
    defaults.update(kw)
    return CollectModels.objects.create(**defaults)


def _payload(task, **kw):
    base = dict(
        collect_task_id=task.id,
        protocol_version="2",
        instance_uuid="123e4567-e89b-42d3-a456-426614174000",
        status="success",
        version=str(int(now().timestamp() * 1000)),
        content_base64=base64.b64encode(b"server { listen 80; }").decode(),
        file_path="/etc/app.conf",
        file_name="app.conf",
    )
    base.update(kw)
    return base


def _add_second_target(task):
    task.instances = [
        *task.instances,
        {
            "_id": "inst-2",
            "inst_uuid": "223e4567-e89b-42d3-a456-426614174000",
            "ip_addr": "10.0.0.2",
            "inst_name": "10.0.0.2",
        },
    ]
    task.save(update_fields=["instances"])
    return task


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
def test_success_creates_version_and_updates_task(django_capture_on_commit_callbacks):
    task = _make_task()
    with django_capture_on_commit_callbacks(execute=True):
        result = S.process_collect_result(_payload(task))

    assert result["changed"] is True
    assert result["task_updated"] is True
    version_obj = result["version_obj"]
    assert version_obj is not None
    assert version_obj.status == ConfigFileVersionStatus.SUCCESS
    assert str(version_obj.instance_uuid) == "123e4567-e89b-42d3-a456-426614174000"
    assert version_obj.instance_id == "123e4567-e89b-42d3-a456-426614174000"
    assert version_obj.content_hash  # 已计算哈希
    assert version_obj.content_key.endswith(".txt")  # 对象键已落到 content
    version_obj.refresh_from_db()
    assert version_obj.content_status == "ready"
    assert version_obj.temp_content_key == ""

    # DB 真实落库
    assert ConfigFileVersion.objects.filter(collect_task=task, instance_id="123e4567-e89b-42d3-a456-426614174000").count() == 1

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.SUCCESS
    cf = task.collect_data["config_file"]
    assert cf["success_count"] == 1
    assert cf["changed_count"] == 1
    assert cf["items"]["123e4567-e89b-42d3-a456-426614174000"]["status"] == ConfigFileVersionStatus.SUCCESS
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
    result = S.process_collect_result(_payload(task, status="file_not_found", content_base64="", error="文件不存在"))
    assert result["version_obj"] is None
    assert result["changed"] is False
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 0

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR
    item = task.collect_data["config_file"]["items"]["123e4567-e89b-42d3-a456-426614174000"]
    assert item["status"] == ConfigFileVersionStatus.FILE_NOT_FOUND
    assert item["error_message"] == "文件不存在"


@pytest.mark.django_db
def test_network_failure_keeps_callback_config_identity():
    task = _make_task(model_id="network_config_file", params={"config_name": "running-config"})

    S.process_collect_result(
        _payload(
            task,
            status="error",
            content_base64="",
            error="连接失败",
            file_path="network://running-config",
            file_name="running-config",
        )
    )

    task.refresh_from_db()
    item = task.collect_data["config_file"]["items"]["123e4567-e89b-42d3-a456-426614174000"]
    assert item["file_path"] == "network://running-config"
    assert item["file_name"] == "running-config"


@pytest.mark.django_db
def test_stale_callback_is_ignored():
    task = _make_task(
        collect_data={
            "config_file": {
                "items": {
                    "123e4567-e89b-42d3-a456-426614174000": {
                        "instance_id": "123e4567-e89b-42d3-a456-426614174000",
                        "version": "2000",
                        "status": ConfigFileVersionStatus.SUCCESS,
                    }
                }
            }
        }
    )
    result = S.process_collect_result(_payload(task, version="1000", status="file_not_found", content_base64=""))
    assert result["task_updated"] is False
    assert result["stale"] is True
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.NOT_START


@pytest.mark.django_db
def test_version_order_is_isolated_per_target():
    task = _add_second_target(_make_task())

    first = S.process_collect_result(_payload(task, version="3000"))
    second = S.process_collect_result(
        _payload(
            task,
            instance_uuid="223e4567-e89b-42d3-a456-426614174000",
            version="1000",
            content_base64=base64.b64encode(b"device-two").decode(),
        )
    )

    assert first["task_updated"] is True
    assert second["task_updated"] is True
    assert second.get("stale", False) is False
    task.refresh_from_db()
    state = task.collect_data["config_file"]
    assert state["status"] == "success"
    assert state["pending_count"] == 0
    assert set(state["items"]) == {
        "123e4567-e89b-42d3-a456-426614174000",
        "223e4567-e89b-42d3-a456-426614174000",
    }


@pytest.mark.django_db
def test_multi_target_periodic_state_recovers_after_failed_target_succeeds():
    task = _add_second_target(_make_task())
    S.process_collect_result(_payload(task, version="1700000000000", status="error", content_base64="", error="连接失败"))
    S.process_collect_result(
        _payload(
            task,
            instance_uuid="223e4567-e89b-42d3-a456-426614174000",
            version="1700000000000",
            content_base64=base64.b64encode(b"device-two").decode(),
        )
    )

    task.refresh_from_db()
    assert task.collect_data["config_file"]["status"] == "error"
    assert task.collect_data["config_file"]["error_count"] == 1

    S.process_collect_result(_payload(task, version="1700000001000", content_base64=base64.b64encode(b"recovered").decode()))

    task.refresh_from_db()
    state = task.collect_data["config_file"]
    assert state["status"] == "success"
    assert state["success_count"] == 2
    assert state["error_count"] == 0
    assert task.exec_status == CollectRunStatusType.SUCCESS


@pytest.mark.django_db
def test_periodic_callback_does_not_require_execution_id():
    task = _make_task()
    result = S.process_collect_result(_payload(task))

    assert result["changed"] is True
    assert result["task_updated"] is True
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 1
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.SUCCESS


@pytest.mark.django_db
def test_legacy_execution_id_is_ignored_for_periodic_callback():
    task = _make_task()

    result = S.process_collect_result(_payload(task, execution_id="execution-old"))

    assert result["changed"] is True
    assert result["task_updated"] is True
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 1
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.SUCCESS


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
def test_periodic_callback_updates_task_regardless_of_previous_status(terminal_status):
    task = _make_task(exec_status=terminal_status)

    result = S.process_collect_result(_payload(task))

    assert result["changed"] is True
    assert result["task_updated"] is True
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 1
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.SUCCESS


@pytest.mark.django_db
def test_instance_not_in_task_is_rejected_without_poisoning_valid_target():
    task = _make_task()
    result = S.process_collect_result(_payload(task, instance_uuid="223e4567-e89b-42d3-a456-426614174000"))
    assert result["version_obj"] is None
    assert result["task_updated"] is False
    assert "error" in result
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.NOT_START


@pytest.mark.django_db
def test_missing_instance_identifier_closes_task():
    task = _make_task()
    payload = _payload(task)
    payload.pop("instance_uuid")
    result = S.process_collect_result(payload)
    assert result["version_obj"] is None
    assert "error" in result


@pytest.mark.django_db
def test_legacy_instance_id_callback_is_rejected():
    task = _make_task()
    payload = _payload(task)
    payload["instance_id"] = "inst-1"
    result = S.process_collect_result(payload)
    assert result["version_obj"] is None
    assert "error" in result


@pytest.mark.django_db
def test_hostname_only_callback_is_rejected():
    task = _make_task()
    payload = _payload(task)
    payload.pop("instance_uuid")
    payload["instance_name"] = "10.0.0.1"
    result = S.process_collect_result(payload)
    assert result["version_obj"] is None
    assert "error" in result


@pytest.mark.django_db
def test_same_business_key_and_content_is_idempotent(monkeypatch):
    task = _make_task()
    ver = str(int(now().timestamp() * 1000))
    saved_objects = []

    def fake_stage_content(text):
        saved_objects.append(text)
        return "tmp/config-file/idempotent.txt"

    monkeypatch.setattr(ConfigFileContentLifecycle, "stage_content", staticmethod(fake_stage_content))
    first = S.process_collect_result(_payload(task, version=ver, content_base64=base64.b64encode(b"v1").decode()))
    second = S.process_collect_result(_payload(task, version=ver, content_base64=base64.b64encode(b"v1").decode()))

    assert second["version_obj"].id == first["version_obj"].id
    assert second["changed"] is False
    assert len(saved_objects) == 1
    assert ConfigFileVersion.objects.filter(collect_task=task, version=ver).count() == 1


@pytest.mark.django_db
def test_idempotent_redelivery_repairs_missing_task_summary():
    task = _make_task()
    payload = _payload(task, version="1700000000000")
    first = S.process_collect_result(payload)
    CollectModels.objects.filter(id=task.id).update(
        collect_data={},
        format_data={},
        collect_digest={},
        exec_status=CollectRunStatusType.NOT_START,
    )

    repeated = S.process_collect_result(payload)

    assert repeated["version_obj"].id == first["version_obj"].id
    assert repeated["changed"] is False
    assert repeated["task_updated"] is True
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 1
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.SUCCESS
    assert task.collect_data["config_file"]["success_count"] == 1


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
    filter_result.filter.return_value = filter_result
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
def test_transaction_rollback_does_not_publish_formal_content(monkeypatch):
    task = _make_task()
    formal_writes = []

    def track_formal_write(version_id):
        formal_writes.append(version_id)
        return True

    monkeypatch.setattr(ConfigFileContentLifecycle, "publish_version", staticmethod(track_formal_write))

    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            S._create_or_get_version(
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
            raise RuntimeError("rollback")

    assert formal_writes == []
    assert ConfigFileVersion.objects.filter(collect_task=task).count() == 0


@pytest.mark.django_db(transaction=True)
def test_transaction_rollback_does_not_delete_content_object(monkeypatch):
    version_obj = ConfigFileVersion.objects.create(
        **_version_fields(),
        content="host/inst-1/formal.txt",
        content_status="ready",
    )
    version_id = version_obj.id
    deleted_objects = []
    monkeypatch.setattr(version_obj.content, "delete", lambda save=False: deleted_objects.append(version_obj.content.name))

    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            version_obj.delete()
            raise RuntimeError("rollback")

    assert deleted_objects == []
    assert ConfigFileVersion.objects.filter(id=version_id).exists()


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

    assert (
        ConfigFileVersion.objects.filter(
            collect_task=task,
            instance_id="inst-1",
            version="1700000000000",
        ).count()
        == 1
    )
    assert "created" in outcomes


@pytest.mark.django_db(transaction=True)
def test_dedupe_migration_keeps_earliest_record():
    executor = MigrationExecutor(connection)
    old_target = [("cmdb", "0031_subscriptiondelivery")]
    latest_target = [("cmdb", "0042_collectmodels_system_code_unique")]
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
        executor.migrate(latest_target)


@pytest.mark.django_db(transaction=True)
def test_content_lifecycle_migration_classifies_existing_versions():
    executor = MigrationExecutor(connection)
    old_target = [("cmdb", "0032_dedupe_config_file_versions")]
    new_target = [("cmdb", "0033_config_file_content_lifecycle")]
    latest_target = [("cmdb", "0042_collectmodels_system_code_unique")]
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
        executor.migrate(latest_target)
