"""安装包发布原子性：最终对象键只在 pending 行落库后写入。

仅 mock JetStream put/delete。覆盖 DB 失败、latest 替换、重复删除、ready 才可下载。
不导入 package 视图，避免 collector_release → monitor 的 app 依赖。
"""

from threading import Thread
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.db import IntegrityError, connection
from nats.js.errors import ObjectNotFoundError

from apps.node_mgmt.constants.package import PackageConstants
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.services.package import PackageService

pytestmark = pytest.mark.django_db

FINAL_KEY = "linux/x86_64/fusion-collectors/1.0.0/fusion-collectors.tar.gz"
LATEST_FINAL_KEY = "linux/x86_64/fusion-collectors/latest/fusion-collectors.tar.gz"


def _package_data(**over):
    data = {
        "os": "linux",
        "cpu_architecture": "x86_64",
        "type": PackageConstants.TYPE_CONTROLLER,
        "object": "fusion-collectors",
        "version": "1.0.0",
        "name": "fusion-collectors.tar.gz",
        "description": "desc",
        "created_by": "tester",
        "updated_by": "tester",
    }
    data.update(over)
    return data


def _is_staging_key(path: str) -> bool:
    return ".staging-" in path


def _is_final_key(path: str) -> bool:
    return not _is_staging_key(path)


class _ObjectStore:
    def __init__(self):
        self.puts: list[str] = []
        self.deletes: list[str] = []
        self.fail_on_put = None
        self.fail_on_delete = None

    async def put(self, file, path):
        if self.fail_on_put and self.fail_on_put(path):
            raise RuntimeError("jetstream put failed")
        self.puts.append(path)

    async def delete(self, path):
        if self.fail_on_delete and self.fail_on_delete(path):
            raise RuntimeError("jetstream delete failed")
        self.deletes.append(path)


@pytest.fixture
def object_store():
    store = _ObjectStore()
    with (
        patch("apps.node_mgmt.services.package.upload_file_to_s3", store.put),
        patch("apps.node_mgmt.services.package.delete_s3_file", store.delete),
    ):
        yield store


def test_create_db_failure_does_not_put_final_object_key(object_store):
    """复现：create 在落库失败后不得留下最终对象键。"""
    with patch.object(PackageVersion, "save", side_effect=RuntimeError("db boom")):
        with pytest.raises(RuntimeError, match="db boom"):
            PackageService.upload_file(ContentFile(b"content", name="fusion-collectors.tar.gz"), _package_data())

    assert FINAL_KEY not in object_store.puts
    assert not PackageVersion.objects.filter(object="fusion-collectors", version="1.0.0").exists()


def test_pending_insert_failure_cleans_staging_and_skips_final_key(object_store):
    with patch.object(PackageVersion.objects, "create", side_effect=RuntimeError("db boom")):
        with pytest.raises(RuntimeError, match="db boom"):
            PackageService.upload_file(ContentFile(b"content", name="fusion-collectors.tar.gz"), _package_data())

    assert not any(_is_final_key(path) for path in object_store.puts)
    assert any(_is_staging_key(path) for path in object_store.puts)
    assert any(_is_staging_key(path) for path in object_store.deletes)
    assert not PackageVersion.objects.filter(object="fusion-collectors", version="1.0.0").exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_validate_then_only_one_publish_wins(object_store):
    """无锁 validate 都看不到 existing，但第二次 publish 不得再写最终键。"""
    data = _package_data()
    first_ok, _first_msg, first_info = PackageService.validate_package(
        "fusion-collectors-1.0.0.tar.gz",
        PackageConstants.TYPE_CONTROLLER,
        "linux",
        "fusion-collectors",
        "x86_64",
    )
    second_ok, _second_msg, second_info = PackageService.validate_package(
        "fusion-collectors-1.0.0.tar.gz",
        PackageConstants.TYPE_CONTROLLER,
        "linux",
        "fusion-collectors",
        "x86_64",
    )
    assert first_ok is True
    assert second_ok is True
    assert first_info["version"] == "1.0.0"
    assert second_info["version"] == "1.0.0"

    outcomes: list[str] = []

    def _worker():
        try:
            PackageService.upload_file(ContentFile(b"content", name="fusion-collectors.tar.gz"), data)
            outcomes.append("ok")
        except Exception as error:
            outcomes.append(type(error).__name__)
        finally:
            connection.close()

    threads = [Thread(target=_worker), Thread(target=_worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count("ok") == 1
    assert (
        PackageVersion.objects.filter(
            object="fusion-collectors",
            version="1.0.0",
            status=PackageVersion.STATUS_READY,
        ).count()
        == 1
    )
    assert object_store.puts.count(FINAL_KEY) == 1


def test_duplicate_publish_raises_integrity_error_without_second_final_put(object_store):
    PackageService.upload_file(ContentFile(b"first", name="fusion-collectors.tar.gz"), _package_data())
    object_store.puts.clear()
    object_store.deletes.clear()

    with pytest.raises(IntegrityError):
        PackageService.upload_file(ContentFile(b"second", name="fusion-collectors.tar.gz"), _package_data())

    assert FINAL_KEY not in object_store.puts
    assert PackageVersion.objects.filter(object="fusion-collectors", version="1.0.0").count() == 1


def test_publish_puts_staging_then_final_and_marks_ready(object_store):
    package = PackageService.upload_file(ContentFile(b"content", name="fusion-collectors.tar.gz"), _package_data())

    assert package.status == PackageVersion.STATUS_READY
    assert any(_is_staging_key(path) for path in object_store.puts)
    assert FINAL_KEY in object_store.puts
    staging_puts = [path for path in object_store.puts if _is_staging_key(path)]
    assert object_store.puts.index(staging_puts[0]) < object_store.puts.index(FINAL_KEY)
    assert any(_is_staging_key(path) for path in object_store.deletes)
    assert PackageVersion.objects.get(pk=package.pk).status == PackageVersion.STATUS_READY


def test_final_put_failure_rolls_back_pending_and_cleans_staging(object_store):
    object_store.fail_on_put = _is_final_key

    with pytest.raises(RuntimeError, match="jetstream put failed"):
        PackageService.upload_file(ContentFile(b"content", name="fusion-collectors.tar.gz"), _package_data())

    assert FINAL_KEY not in object_store.puts
    assert any(_is_staging_key(path) for path in object_store.deletes)
    assert not PackageVersion.objects.filter(object="fusion-collectors", version="1.0.0").exists()


def test_latest_replace_locks_existing_and_returns_ready(object_store):
    existing = PackageVersion.objects.create(
        type=PackageConstants.TYPE_CONTROLLER,
        os="linux",
        cpu_architecture="x86_64",
        object="fusion-collectors",
        version=PackageConstants.VERSION_LATEST,
        name="fusion-collectors.tar.gz",
        description="old",
        status=PackageVersion.STATUS_READY,
    )
    data = _package_data(version=PackageConstants.VERSION_LATEST, description="new")

    package = PackageService.upload_file(
        ContentFile(b"new-content", name="fusion-collectors.tar.gz"),
        data,
        existing_package=existing,
    )

    existing.refresh_from_db()
    assert package.pk == existing.pk
    assert existing.status == PackageVersion.STATUS_READY
    assert existing.description == "new"
    assert LATEST_FINAL_KEY in object_store.puts
    assert PackageVersion.objects.filter(object="fusion-collectors", version="latest").count() == 1


def test_latest_final_put_failure_restores_ready(object_store):
    existing = PackageVersion.objects.create(
        type=PackageConstants.TYPE_CONTROLLER,
        os="linux",
        cpu_architecture="x86_64",
        object="fusion-collectors",
        version=PackageConstants.VERSION_LATEST,
        name="fusion-collectors.tar.gz",
        description="old",
        status=PackageVersion.STATUS_READY,
    )
    object_store.fail_on_put = _is_final_key
    data = _package_data(version=PackageConstants.VERSION_LATEST, description="new")

    with pytest.raises(RuntimeError, match="jetstream put failed"):
        PackageService.upload_file(
            ContentFile(b"new-content", name="fusion-collectors.tar.gz"),
            data,
            existing_package=existing,
        )

    existing.refresh_from_db()
    assert existing.status == PackageVersion.STATUS_READY
    assert existing.description == "old"
    assert LATEST_FINAL_KEY not in object_store.puts


def test_list_queryset_only_returns_ready():
    ready = PackageVersion.objects.create(
        type="collector",
        os="linux",
        cpu_architecture="x86_64",
        object="telegraf",
        version="1.0.0",
        name="telegraf.tar.gz",
        status=PackageVersion.STATUS_READY,
    )
    PackageVersion.objects.create(
        type="collector",
        os="linux",
        cpu_architecture="x86_64",
        object="telegraf",
        version="1.0.1",
        name="telegraf.tar.gz",
        status=PackageVersion.STATUS_PENDING,
    )
    PackageVersion.objects.create(
        type="collector",
        os="linux",
        cpu_architecture="x86_64",
        object="telegraf",
        version="1.0.2",
        name="telegraf.tar.gz",
        status=PackageVersion.STATUS_DELETING,
    )

    ids = list(PackageService.ready_queryset().order_by("-id").values_list("id", flat=True))
    assert ids == [ready.id]


def test_download_and_stream_only_allow_ready():
    pending = PackageVersion.objects.create(
        type="collector",
        os="linux",
        cpu_architecture="x86_64",
        object="telegraf",
        version="9.0.0",
        name="telegraf.tar.gz",
        status=PackageVersion.STATUS_PENDING,
    )
    with pytest.raises(ObjectNotFoundError):
        PackageService.download_file(pending)
    with pytest.raises(ObjectNotFoundError):
        PackageService.download_file_streaming(pending)


def test_destroy_keeps_row_when_object_delete_fails(object_store):
    pkg = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="x86_64",
        object="fusion-collectors",
        version="2.0.0",
        name="fusion-collectors.tar.gz",
        status=PackageVersion.STATUS_READY,
    )
    object_store.fail_on_delete = lambda path: True

    with pytest.raises(RuntimeError, match="jetstream delete failed"):
        PackageService.delete_file(pkg)

    pkg.refresh_from_db()
    assert pkg.status == PackageVersion.STATUS_DELETING
    assert PackageVersion.objects.filter(id=pkg.id).exists()


def test_destroy_missing_object_is_success_then_row_can_be_removed():
    pkg = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="x86_64",
        object="fusion-collectors",
        version="3.0.0",
        name="fusion-collectors.tar.gz",
        status=PackageVersion.STATUS_READY,
    )

    async def missing(_path):
        raise ObjectNotFoundError()

    with patch("apps.node_mgmt.services.package.delete_s3_file", missing):
        assert PackageService.delete_file(pkg) is True

    pkg.refresh_from_db()
    assert pkg.status == PackageVersion.STATUS_DELETING
    pkg.delete()
    assert not PackageVersion.objects.filter(id=pkg.id).exists()


def test_repeated_delete_is_idempotent(object_store):
    pkg = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="x86_64",
        object="fusion-collectors",
        version="4.0.0",
        name="fusion-collectors.tar.gz",
        status=PackageVersion.STATUS_READY,
    )

    assert PackageService.delete_file(pkg) is True
    assert PackageService.delete_file(pkg) is True
    pkg.delete()
    assert PackageService.delete_file(pkg) is True
