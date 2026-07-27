"""补丁库元数据写路径测试。"""

import hashlib
from datetime import timedelta
from unittest.mock import patch as mock_patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from apps.patch_mgmt.constants import OSType, PackageStatus
from apps.patch_mgmt.models import (
    BaselineRequirement,
    Patch,
    PatchBaseline,
    WindowsPatchDetail,
)
from apps.patch_mgmt.services.windows_package import expire_stale_windows_package_uploads

_BASE = "/api/v1/patch_mgmt"
PATCH_URL = f"{_BASE}/api/patch/"


@pytest.mark.django_db
class TestPatchWriteViewApi:
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
        assert "基线" in resp.data["detail"]

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
        assert "文件" in resp.data["detail"]


@pytest.mark.django_db
class TestPatchMetadataOnlyViewApi:
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
