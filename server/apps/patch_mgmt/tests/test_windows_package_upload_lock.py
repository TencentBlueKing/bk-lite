"""手工 Windows 补丁包上传与超时清理的行锁契约。"""

from datetime import timedelta
from unittest.mock import patch as mock_patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.transaction import Atomic
from django.utils import timezone

from apps.patch_mgmt.constants import OSType, PackageStatus
from apps.patch_mgmt.models import Patch, WindowsPatchDetail
from apps.patch_mgmt.services.windows_package import (
    WindowsPackageError,
    _mark_failed,
    expire_stale_windows_package_uploads,
    replace_failed_windows_package,
    store_windows_package,
)


def _msu_upload(name: str, payload: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"PK\x03\x04" + payload)


def _create_downloading_patch(*, kb_number: str, title: str) -> Patch:
    patch = Patch.objects.create(
        title=title,
        os_type=OSType.WINDOWS,
        pkg_status=PackageStatus.DOWNLOADING,
        team=[1],
    )
    WindowsPatchDetail.objects.create(patch=patch, kb_number=kb_number)
    return patch


def _age_patch(patch: Patch, *, hours: int = 25) -> None:
    Patch.objects.filter(pk=patch.pk).update(
        updated_at=timezone.now() - timedelta(hours=hours),
    )
    patch.refresh_from_db()


@pytest.mark.django_db
class TestWindowsPackageUploadLock:
    def test_expire_between_file_write_and_ready_cannot_orphan_ready(self):
        """expire 插在文件提交与 READY 之间时，不得留下 READY + 已删文件。"""
        patch = _create_downloading_patch(kb_number="KB5440001", title="交错超时补丁")
        _age_patch(patch)
        upload = _msu_upload("kb5440001.msu", b"upload-vs-expire")
        original_exit = Atomic.__exit__
        expire_after_first_commit = {"fired": False}

        def exit_then_expire(self, exc_type, exc, tb):
            result = original_exit(self, exc_type, exc, tb)
            if not expire_after_first_commit["fired"] and exc_type is None:
                expire_after_first_commit["fired"] = True
                expire_stale_windows_package_uploads(timeout_seconds=60)
            return result

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/kb5440001.msu",
        ), mock_patch.object(Atomic, "__exit__", exit_then_expire):
            store_windows_package(patch, upload)

        patch.refresh_from_db()
        detail = patch.windows_detail
        assert expire_after_first_commit["fired"] is True
        assert patch.pkg_status == PackageStatus.READY
        assert bool(detail.package_file)
        assert "上传超时" not in (detail.package_error or "")

    def test_stale_in_memory_upload_does_not_overwrite_ready(self):
        """锁内复核非 DOWNLOADING 时失败，且不得覆盖已就绪文件。"""
        patch = _create_downloading_patch(kb_number="KB5440002", title="就绪后二次上传")
        first = _msu_upload("kb5440002-first.msu", b"first-package")
        second = _msu_upload("kb5440002-second.msu", b"second-package")

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/kb5440002-first.msu",
        ):
            store_windows_package(patch, first)

        patch.refresh_from_db()
        ready_name = patch.windows_detail.package_original_name
        stale = Patch.objects.get(pk=patch.pk)
        stale.pkg_status = PackageStatus.DOWNLOADING

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/kb5440002-second.msu",
        ):
            with pytest.raises(WindowsPackageError, match="当前补丁状态不允许上传文件"):
                store_windows_package(stale, second)

        patch.refresh_from_db()
        assert patch.pkg_status == PackageStatus.READY
        assert patch.windows_detail.package_original_name == ready_name
        assert patch.windows_detail.package_original_name != "kb5440002-second.msu"

    def test_replace_failed_rejects_stale_in_memory_non_failed(self):
        """replace 必须先锁再复核，不能把 READY 当成失败记录覆盖。"""
        patch = _create_downloading_patch(kb_number="KB5440003", title="替换误覆盖")
        first = _msu_upload("kb5440003-ready.msu", b"ready-package")
        replacement = _msu_upload("kb5440003-replace.msu", b"replace-package")

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/kb5440003-ready.msu",
        ):
            store_windows_package(patch, first)

        patch.refresh_from_db()
        ready_name = patch.windows_detail.package_original_name
        stale = Patch.objects.get(pk=patch.pk)
        stale.pkg_status = PackageStatus.DOWNLOAD_FAILED

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/kb5440003-replace.msu",
        ):
            with pytest.raises(WindowsPackageError, match="仅上传失败的补丁允许替换文件"):
                replace_failed_windows_package(stale, replacement)

        patch.refresh_from_db()
        assert patch.pkg_status == PackageStatus.READY
        assert patch.windows_detail.package_original_name == ready_name

    def test_mark_failed_does_not_overwrite_ready(self):
        patch = _create_downloading_patch(kb_number="KB5440004", title="失败标记不覆盖就绪")
        upload = _msu_upload("kb5440004.msu", b"ready-then-mark-failed")
        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/kb5440004.msu",
        ):
            store_windows_package(patch, upload)

        patch.refresh_from_db()
        _mark_failed(patch, patch.windows_detail, "补丁包上传超时，请编辑后重新选择文件上传")

        patch.refresh_from_db()
        assert patch.pkg_status == PackageStatus.READY
        assert "上传超时" not in (patch.windows_detail.package_error or "")

    def test_successful_upload_still_marks_ready(self):
        patch = _create_downloading_patch(kb_number="KB5440005", title="顺序成功上传")
        content = b"sequential-success"
        upload = _msu_upload("kb5440005.msu", content)

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/kb5440005.msu",
        ):
            result = store_windows_package(patch, upload)

        patch.refresh_from_db()
        assert patch.pkg_status == PackageStatus.READY
        assert result["file_name"] == "kb5440005.msu"
        assert patch.windows_detail.package_error == ""
        assert patch.windows_detail.package_original_name == "kb5440005.msu"

    def test_stale_downloading_expire_still_marks_failed(self):
        patch = _create_downloading_patch(kb_number="KB5440006", title="超时仍应收口")
        _age_patch(patch)

        result = expire_stale_windows_package_uploads(timeout_seconds=60)

        patch.refresh_from_db()
        assert result == 1
        assert patch.pkg_status == PackageStatus.DOWNLOAD_FAILED
        assert "上传超时" in patch.windows_detail.package_error

    def test_invalid_package_still_marks_failed(self):
        patch = _create_downloading_patch(kb_number="KB5440007", title="校验失败仍标记失败")
        upload = SimpleUploadedFile("kb5440007.txt", b"not-a-patch")

        with pytest.raises(WindowsPackageError, match="仅支持 .msu 和 .cab 补丁包"):
            store_windows_package(patch, upload)

        patch.refresh_from_db()
        assert patch.pkg_status == PackageStatus.DOWNLOAD_FAILED
        assert "仅支持 .msu 和 .cab 补丁包" in patch.windows_detail.package_error
