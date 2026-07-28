"""补丁库元数据写路径测试。"""

import hashlib
import json
from datetime import timedelta
from unittest.mock import patch as mock_patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from apps.patch_mgmt.constants import OSType, PackageStatus
from apps.patch_mgmt.models import (
    BaselineRequirement,
    LinuxPatchDetail,
    Patch,
    PatchBaseline,
    WindowsPatchDetail,
)
from apps.patch_mgmt.services.windows_package import expire_stale_windows_package_uploads

_BASE = "/api/v1/patch_mgmt"
PATCH_URL = f"{_BASE}/api/patch/"


@pytest.mark.django_db
class TestPatchWriteViewApi:
    def test_update_synced_linux_patch_accepts_legacy_repo_source_type(self, su_client):
        patch = Patch.objects.create(
            title="RLSA-2023:6661",
            os_type=OSType.LINUX,
            severity="low",
            team=[1],
        )
        LinuxPatchDetail.objects.create(
            patch=patch,
            pkg_name="gmp",
            pkg_version="6.2.0-13.el9",
            distro_name="Rocky",
            architectures=["i686"],
            repo_type="yum_repo",
        )

        resp = su_client.put(
            f"{PATCH_URL}{patch.id}/",
            {
                "title": "只修改描述",
                "os_type": OSType.LINUX,
                "severity": "low",
                "team": [1],
                "linux_detail": {
                    "pkg_name": "gmp",
                    "pkg_version": "6.2.0-13.el9",
                    "distro_name": "Rocky",
                    "os_version_range": "",
                    "architectures": ["i686"],
                    "repo_type": "yum_repo",
                },
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        patch.refresh_from_db()
        assert patch.title == "只修改描述"
        assert patch.linux_detail.repo_type == "yum"

    def test_update_manual_windows_patch_keeps_its_kb(self, su_client):
        patch = Patch.objects.create(
            title="KB5072653",
            os_type=OSType.WINDOWS,
            severity="important",
            team=[1],
        )
        WindowsPatchDetail.objects.create(
            patch=patch,
            kb_number="KB5072653",
            product_list=["Windows 10", "Windows 11"],
        )

        resp = su_client.put(
            f"{PATCH_URL}{patch.id}/",
            {
                "title": "KB5072653",
                "os_type": OSType.WINDOWS,
                "severity": "important",
                "team": [1],
                "windows_detail": {
                    "kb_number": "KB5072653",
                    "product_list": ["Windows 10", "Windows 11"],
                    "architectures": [],
                    "ms_bulletin": "",
                },
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["windows_detail"]["kb_number"] == "KB5072653"

    def test_update_api_persists_new_title(self, su_client):
        patch = Patch.objects.create(title="旧标题", os_type=OSType.WINDOWS, team=[1])
        resp = su_client.put(
            f"{PATCH_URL}{patch.id}/",
            {"title": "新标题", "os_type": OSType.WINDOWS, "team": [1]},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        patch.refresh_from_db()
        assert patch.title == "新标题"

    def test_destroy_api_removes_patch(self, su_client):
        patch = Patch.objects.create(title="待删除", os_type=OSType.LINUX, team=[1])
        resp = su_client.delete(f"{PATCH_URL}{patch.id}/")
        assert resp.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
        assert not Patch.objects.filter(pk=patch.id).exists()

    def test_destroy_api_rejects_patch_referenced_by_baseline(self, su_client):
        patch = Patch.objects.create(title="基线引用补丁", os_type=OSType.LINUX, team=[1])
        baseline = PatchBaseline.objects.create(name="测试基线", os_type=OSType.LINUX, team=[1])
        BaselineRequirement.objects.create(baseline=baseline, patch=patch)

        resp = su_client.delete(f"{PATCH_URL}{patch.id}/")

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert Patch.objects.filter(pk=patch.id).exists()
        assert resp.data["detail"]

    def test_destroy_api_deletes_manual_package_object_before_record(self, su_client):
        patch = Patch.objects.create(title="手工补丁", os_type=OSType.WINDOWS, team=[1])
        detail = WindowsPatchDetail.objects.create(
            patch=patch,
            kb_number="KB6000098",
            package_file="windows/1/manual.msu",
        )

        with mock_patch.object(detail.package_file.storage, "delete") as delete_object:
            resp = su_client.delete(f"{PATCH_URL}{patch.id}/")

        assert resp.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
        delete_object.assert_called_once_with("windows/1/manual.msu")
        assert not Patch.objects.filter(pk=patch.id).exists()

    def test_destroy_api_keeps_record_when_manual_package_object_delete_fails(self, su_client):
        patch = Patch.objects.create(title="手工补丁", os_type=OSType.WINDOWS, team=[1])
        detail = WindowsPatchDetail.objects.create(
            patch=patch,
            kb_number="KB6000099",
            package_file="windows/1/manual.msu",
        )

        with mock_patch.object(
            detail.package_file.storage,
            "delete",
            side_effect=OSError("storage unavailable"),
        ):
            resp = su_client.delete(f"{PATCH_URL}{patch.id}/")

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert Patch.objects.filter(pk=patch.id).exists()
        assert resp.data["detail"]


@pytest.mark.django_db
class TestPatchMetadataOnlyViewApi:
    def test_create_manual_windows_patch_in_one_multipart_request(self, su_client):
        content = b"MSCF" + b"single-create-request"
        upload = SimpleUploadedFile("windows-kb6000010.msu", content)
        metadata = {
            "title": "单请求新增补丁",
            "os_type": OSType.WINDOWS,
            "severity": "important",
            "team": [1],
            "windows_detail": {
                "kb_number": "KB6000010",
                "product_list": ["Windows Server 2022"],
                "architectures": ["x64"],
                "ms_bulletin": "",
            },
        }

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/windows-kb6000010.msu",
        ):
            resp = su_client.post(
                PATCH_URL,
                {"metadata": json.dumps(metadata), "file": upload},
                format="multipart",
            )

        assert resp.status_code == status.HTTP_201_CREATED
        patch = Patch.objects.get(pk=resp.data["id"])
        assert patch.pkg_status == PackageStatus.READY
        assert resp.data["package_info"]["file_name"] == "windows-kb6000010.msu"

    def test_update_failed_manual_windows_patch_in_one_multipart_request(self, su_client):
        patch = Patch.objects.create(
            title="替换前",
            os_type=OSType.WINDOWS,
            pkg_status=PackageStatus.DOWNLOAD_FAILED,
            severity="important",
            team=[1],
        )
        WindowsPatchDetail.objects.create(
            patch=patch,
            kb_number="KB6000011",
            package_error="上次失败",
        )
        upload = SimpleUploadedFile("windows-kb6000011.cab", b"MSCF" + b"single-update-request")
        metadata = {
            "title": "替换后",
            "os_type": OSType.WINDOWS,
            "severity": "critical",
            "team": [1],
            "windows_detail": {
                "kb_number": "KB6000011",
                "product_list": ["Windows 11"],
                "architectures": ["x64"],
                "ms_bulletin": "",
            },
        }

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/windows-kb6000011.cab",
        ):
            resp = su_client.put(
                f"{PATCH_URL}{patch.id}/",
                {"metadata": json.dumps(metadata), "file": upload},
                format="multipart",
            )

        assert resp.status_code == status.HTTP_200_OK
        patch.refresh_from_db()
        assert patch.title == "替换后"
        assert patch.pkg_status == PackageStatus.READY
        assert patch.windows_detail.package_original_name == "windows-kb6000011.cab"

    def test_invalid_package_does_not_create_manual_windows_patch(self, su_client):
        metadata = {
            "title": "无效文件",
            "os_type": OSType.WINDOWS,
            "severity": "important",
            "team": [1],
            "windows_detail": {"kb_number": "KB6000012"},
        }
        resp = su_client.post(
            PATCH_URL,
            {
                "metadata": json.dumps(metadata),
                "file": SimpleUploadedFile("windows-kb6000012.msu", b"not-a-package"),
            },
            format="multipart",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert not WindowsPatchDetail.objects.filter(kb_number="KB6000012").exists()

    def test_create_storage_failure_returns_failed_patch(self, su_client):
        metadata = {
            "title": "存储不可用",
            "os_type": OSType.WINDOWS,
            "severity": "important",
            "team": [1],
            "windows_detail": {"kb_number": "KB6000013"},
        }
        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            side_effect=RuntimeError("存储不可用"),
        ):
            resp = su_client.post(
                PATCH_URL,
                {
                    "metadata": json.dumps(metadata),
                    "file": SimpleUploadedFile(
                        "windows-kb6000013.msu",
                        b"MSCF" + b"storage-failure",
                    ),
                },
                format="multipart",
            )

        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        patch = Patch.objects.get(windows_detail__kb_number="KB6000013")
        assert patch.pkg_status == PackageStatus.DOWNLOAD_FAILED
        assert resp.data["patch"]["id"] == patch.id

    def test_create_manual_windows_patch_with_optional_metadata(self, su_client):
        resp = su_client.post(
            PATCH_URL,
            {
                "title": "2024-01 Security Update 测试",
                "os_type": OSType.WINDOWS,
                "severity": "critical",
                "patch_type": "security",
                "windows_detail": {
                    "kb_number": "KB2203112",
                    "product_list": ["Windows Server 2019"],
                    "architectures": ["x64"],
                    "ms_bulletin": "",
                },
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["windows_detail"]["kb_number"] == "KB2203112"

    def test_create_api_marks_manual_windows_patch_as_downloading(self, su_client):
        resp = su_client.post(
            PATCH_URL,
            {
                "title": "KB6000001",
                "os_type": OSType.WINDOWS,
                "pkg_status": PackageStatus.PENDING,
                "team": [1],
                "windows_detail": {
                    "kb_number": "KB6000001",
                    "product_list": ["Windows Server 2022"],
                    "architectures": ["x64"],
                    "ms_bulletin": "",
                },
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        patch = Patch.objects.get(pk=resp.data["id"])
        assert patch.pkg_status == PackageStatus.DOWNLOADING
        assert resp.data["package_info"] is None

    def test_create_api_rejects_duplicate_normalized_kb(self, su_client):
        payload = {
            "title": "手工补丁 A",
            "os_type": OSType.WINDOWS,
            "team": [1],
            "windows_detail": {
                "kb_number": "kb6000002",
                "product_list": ["Windows Server 2022"],
                "architectures": ["x64"],
                "ms_bulletin": "",
            },
        }
        first = su_client.post(PATCH_URL, payload, format="json")
        assert first.status_code == status.HTTP_201_CREATED

        payload["title"] = "手工补丁 B"
        duplicate = su_client.post(PATCH_URL, payload, format="json")

        assert duplicate.status_code == status.HTTP_400_BAD_REQUEST
        assert Patch.objects.filter(os_type=OSType.WINDOWS).count() == 1
        assert Patch.objects.get().windows_detail.kb_number == "KB6000002"

    def test_patch_package_route_is_removed(self, su_client):
        resp = su_client.get(f"{_BASE}/api/patch_package/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_upload_valid_msu_marks_patch_ready_and_returns_safe_metadata(self, su_client):
        created = su_client.post(
            PATCH_URL,
            {
                "title": "手工 KB6000003",
                "os_type": OSType.WINDOWS,
                "team": [1],
                "windows_detail": {
                    "kb_number": "KB6000003",
                    "product_list": ["Windows Server 2022"],
                    "architectures": ["x64"],
                    "ms_bulletin": "",
                },
            },
            format="json",
        )
        content = b"PK\x03\x04" + b"windows-update-package"
        upload = SimpleUploadedFile(
            "windows-kb6000003.msu",
            content,
            content_type="application/octet-stream",
        )

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/windows-kb6000003.msu",
        ):
            resp = su_client.post(
                f"{PATCH_URL}{created.data['id']}/upload_package/",
                {"file": upload},
                format="multipart",
            )

        assert resp.status_code == status.HTTP_200_OK
        patch = Patch.objects.get(pk=created.data["id"])
        assert patch.pkg_status == PackageStatus.READY
        assert resp.data["package_info"] == {
            "file_name": "windows-kb6000003.msu",
            "file_size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "extension": ".msu",
        }
        assert "url" not in resp.data["package_info"]

    def test_upload_valid_cabinet_container_msu_marks_patch_ready(self, su_client):
        """真实 MSU 可能使用 Cabinet 容器头，不能按普通 ZIP 误拒。"""
        created = su_client.post(
            PATCH_URL,
            {
                "title": "手工 KB6000005",
                "os_type": OSType.WINDOWS,
                "team": [1],
                "windows_detail": {
                    "kb_number": "KB6000005",
                    "product_list": ["Windows Server 2022"],
                    "architectures": ["x64"],
                    "ms_bulletin": "",
                },
            },
            format="json",
        )
        upload = SimpleUploadedFile(
            "windows-kb6000005.msu",
            b"MSCF" + b"windows-update-cabinet",
            content_type="application/octet-stream",
        )

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/windows-kb6000005.msu",
        ):
            resp = su_client.post(
                f"{PATCH_URL}{created.data['id']}/upload_package/",
                {"file": upload},
                format="multipart",
            )

        assert resp.status_code == status.HTTP_200_OK
        assert Patch.objects.get(pk=created.data["id"]).pkg_status == PackageStatus.READY

    def test_storage_failure_marks_manual_windows_patch_failed(self, su_client):
        created = su_client.post(
            PATCH_URL,
            {
                "title": "存储失败补丁",
                "os_type": OSType.WINDOWS,
                "team": [1],
                "windows_detail": {
                    "kb_number": "KB6000006",
                    "product_list": [],
                    "architectures": [],
                    "ms_bulletin": "",
                },
            },
            format="json",
        )
        upload = SimpleUploadedFile(
            "windows-kb6000006.msu",
            b"PK\x03\x04" + b"windows-update-package",
            content_type="application/octet-stream",
        )

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            side_effect=RuntimeError("存储不可用"),
        ):
            resp = su_client.post(
                f"{PATCH_URL}{created.data['id']}/upload_package/",
                {"file": upload},
                format="multipart",
            )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        patch = Patch.objects.get(pk=created.data["id"])
        assert patch.pkg_status == PackageStatus.DOWNLOAD_FAILED
        assert "补丁包存储失败" in patch.windows_detail.package_error

    def test_failed_package_can_be_replaced_from_edit_flow(self, su_client):
        patch = Patch.objects.create(
            title="失败待编辑补丁",
            os_type=OSType.WINDOWS,
            pkg_status=PackageStatus.DOWNLOAD_FAILED,
            team=[1],
        )
        WindowsPatchDetail.objects.create(
            patch=patch,
            kb_number="KB6000004",
            product_list=["Windows Server 2022"],
            architectures=["x64"],
            package_error="上次上传中断",
        )
        content = b"MSCF" + b"cab-package"
        upload = SimpleUploadedFile("kb6000004.cab", content)

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            return_value="windows/1/hash/kb6000004.cab",
        ):
            resp = su_client.post(
                f"{PATCH_URL}{patch.id}/replace_package/",
                {"file": upload},
                format="multipart",
            )

        assert resp.status_code == status.HTTP_200_OK
        patch.refresh_from_db()
        assert patch.pkg_status == PackageStatus.READY
        assert patch.windows_detail.package_original_name == "kb6000004.cab"
        assert patch.windows_detail.package_error == ""

    def test_replacement_storage_failure_keeps_patch_failed(self, su_client):
        patch = Patch.objects.create(
            title="替换存储失败补丁",
            os_type=OSType.WINDOWS,
            pkg_status=PackageStatus.DOWNLOAD_FAILED,
            team=[1],
        )
        WindowsPatchDetail.objects.create(
            patch=patch,
            kb_number="KB6000007",
            package_error="上次上传失败",
        )
        upload = SimpleUploadedFile(
            "windows-kb6000007.msu",
            b"PK\x03\x04" + b"windows-update-package",
            content_type="application/octet-stream",
        )

        with mock_patch(
            "django_minio_backend.MinioBackend.save",
            side_effect=RuntimeError("存储不可用"),
        ):
            resp = su_client.post(
                f"{PATCH_URL}{patch.id}/replace_package/",
                {"file": upload},
                format="multipart",
            )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        patch.refresh_from_db()
        assert patch.pkg_status == PackageStatus.DOWNLOAD_FAILED
        assert "补丁包存储失败" in patch.windows_detail.package_error

    def test_stale_downloading_package_is_marked_failed(self):
        patch = Patch.objects.create(
            title="上传中断补丁",
            os_type=OSType.WINDOWS,
            pkg_status=PackageStatus.DOWNLOADING,
            team=[1],
        )
        WindowsPatchDetail.objects.create(patch=patch, kb_number="KB6000005")
        Patch.objects.filter(pk=patch.pk).update(
            updated_at=patch.updated_at - timedelta(hours=25),
        )

        result = expire_stale_windows_package_uploads(timeout_seconds=24 * 60 * 60)

        patch.refresh_from_db()
        assert result == 1
        assert patch.pkg_status == PackageStatus.DOWNLOAD_FAILED
        assert "上传超时" in patch.windows_detail.package_error
