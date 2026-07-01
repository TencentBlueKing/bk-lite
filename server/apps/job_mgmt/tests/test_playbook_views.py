"""Playbook 视图测试（批量删除 / 模板下载 / 下载&预览的无文件分支 / 列表&详情）

create / upgrade 的归档解析逻辑在 serializers/playbook 的专项测试中覆盖。
"""

import io
import zipfile
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.job_mgmt.models import Playbook
from apps.job_mgmt.views import playbook as playbook_views

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/api/playbook/"


def _make(**over):
    defaults = {"name": "pb", "version": "v1.0.0", "team": [1]}
    defaults.update(over)
    return Playbook.objects.create(**defaults)


def _zip(files: dict, name="pb.zip") -> SimpleUploadedFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for path, content in files.items():
            z.writestr(path, content)
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="application/zip")


def _patch_storage_save():
    storage = Playbook._meta.get_field("file").storage
    return patch.object(storage, "save", return_value="playbooks/pb.zip")


class TestPlaybookSimpleActions:
    def test_list_and_retrieve(self, su_client):
        pb = _make()
        assert su_client.get(URL).status_code == 200
        assert su_client.get(f"{URL}{pb.id}/").status_code == 200

    def test_batch_delete(self, su_client):
        p1 = _make(name="p1")
        p2 = _make(name="p2")
        resp = su_client.post(f"{URL}batch_delete/", {"ids": [p1.id, p2.id]}, format="json")
        assert resp.status_code == 200
        assert resp.data["deleted_count"] == 2
        assert not Playbook.objects.filter(id__in=[p1.id, p2.id]).exists()

    def test_download_template_returns_zip(self, su_client):
        resp = su_client.get(f"{URL}download_template/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/zip"

    def test_download_without_file_returns_404(self, su_client):
        pb = _make()
        resp = su_client.get(f"{URL}{pb.id}/download/")
        assert resp.status_code == 404

    def test_preview_file_missing_param_returns_400(self, su_client):
        pb = _make()
        resp = su_client.get(f"{URL}{pb.id}/preview_file/")
        assert resp.status_code == 400

    def test_preview_file_without_file_returns_404(self, su_client):
        pb = _make()
        resp = su_client.get(f"{URL}{pb.id}/preview_file/?file_path=main.yml")
        assert resp.status_code == 404


class TestPlaybookViewHelpers:
    """直接覆盖 get_serializer_class 各分支与 pre_batch_delete 的清理逻辑。"""

    def test_get_serializer_class_branches(self):
        from apps.job_mgmt.serializers.playbook import (
            PlaybookBatchDeleteSerializer,
            PlaybookCreateSerializer,
            PlaybookDetailSerializer,
            PlaybookListSerializer,
            PlaybookUpdateSerializer,
            PlaybookUpgradeSerializer,
        )

        vs = playbook_views.PlaybookViewSet()
        mapping = {
            "list": PlaybookListSerializer,
            "retrieve": PlaybookDetailSerializer,
            "create": PlaybookCreateSerializer,
            "update": PlaybookUpdateSerializer,
            "partial_update": PlaybookUpdateSerializer,
            "upgrade": PlaybookUpgradeSerializer,
            "batch_delete": PlaybookBatchDeleteSerializer,
            "destroy": PlaybookDetailSerializer,  # 默认分支
        }
        for action, expected in mapping.items():
            vs.action = action
            assert vs.get_serializer_class() is expected

    def test_pre_batch_delete_cleans_minio_file(self):
        pb_with = _make(name="has-file")
        pb_with.file = "playbooks/2026/06/16/a.zip"
        pb_with.save()
        pb_without = _make(name="no-file")

        vs = playbook_views.PlaybookViewSet()
        with patch.object(type(pb_with.file), "delete") as mock_delete:
            vs.pre_batch_delete([pb_with, pb_without])
        # 仅对有文件的实例触发存储删除，且不落库（save=False）
        mock_delete.assert_called_once_with(save=False)


class TestPlaybookCreate:
    """覆盖 create 视图：校验 -> 保存 -> 返回 201 与解析后的对象信息。"""

    def test_create_returns_201_and_parsed_object(self, su_client):
        f = _zip({"demo/README.md": "RM-CONTENT", "demo/vars/main.yml": "k: v\n"}, name="demo.zip")
        with _patch_storage_save():
            resp = su_client.post(URL, {"file": f, "version": "v2.0.0", "team": [1]}, format="multipart")
        assert resp.status_code == 201
        # 名称从文件名自动提取、README 落库、版本透传
        assert resp.data["name"] == "demo"
        assert resp.data["version"] == "v2.0.0"
        # DB 副作用：记录真实写入
        created = Playbook.objects.get(id=resp.data["id"])
        assert created.readme == "RM-CONTENT"

    def test_create_invalid_extension_returns_400(self, su_client):
        bad = SimpleUploadedFile("bad.txt", b"not a zip", content_type="text/plain")
        resp = su_client.post(URL, {"file": bad, "team": [1]}, format="multipart")
        assert resp.status_code == 400


class TestPlaybookUpgrade:
    """覆盖 upgrade 视图：上传新包 -> 自动 +0.0.1 -> 返回 200。"""

    def test_upgrade_auto_increments_version(self, su_client):
        pb = _make(version="v1.0.0")
        f = _zip({"pb/README.md": "RM-NEW"})
        with _patch_storage_save():
            resp = su_client.post(f"{URL}{pb.id}/upgrade/", {"file": f}, format="multipart")
        assert resp.status_code == 200
        assert resp.data["version"] == "v1.0.1"
        pb.refresh_from_db()
        assert pb.readme == "RM-NEW"


class TestPlaybookDownloadWithFile:
    """覆盖 158-160：有文件时返回 FileResponse 文件流。"""

    def test_download_with_file_returns_stream(self, su_client):
        # 落库一个真实存储 key，使 instance.file 为真；mock file.open 返回字节流避免真连 MinIO
        pb = _make()
        pb.file = "playbooks/2026/06/16/pb.zip"
        pb.save()
        with patch.object(type(pb.file), "open", return_value=io.BytesIO(b"ZIP-BYTES")):
            resp = su_client.get(f"{URL}{pb.id}/download/")
        assert resp.status_code == 200
        # 契约：以附件形式下载，文件名取自 file_name
        assert "attachment" in resp.get("Content-Disposition", "")


class TestPlaybookPreviewFileBranches:
    """覆盖 236-253：preview_file 在不同 extract 结果下的状态码映射。

    通过落库真实存储 key 使 instance.file 为真，越过前置 404；只 mock
    extract_file_from_archive（归档/存储读取边界），断言视图自身的错误码映射分支。
    """

    def _pb_with_file(self):
        pb = _make()
        pb.file = "playbooks/2026/06/16/pb.zip"
        pb.save()
        return pb

    def test_preview_success_returns_200(self, su_client):
        pb = self._pb_with_file()
        result = {"file_name": "main.yml", "content": "k: v", "file_type": "yaml", "file_size": 4}
        with patch.object(playbook_views, "extract_file_from_archive", return_value=result):
            resp = su_client.get(f"{URL}{pb.id}/preview_file/?file_path=main.yml")
        assert resp.status_code == 200
        assert resp.data["file_name"] == "main.yml"

    def test_preview_too_large_returns_413(self, su_client):
        pb = self._pb_with_file()
        with patch.object(playbook_views, "extract_file_from_archive", side_effect=ValueError("文件过大|2048")):
            resp = su_client.get(f"{URL}{pb.id}/preview_file/?file_path=big.yml")
        assert resp.status_code == 413
        assert resp.data["file_size"] == 2048

    def test_preview_not_found_returns_404(self, su_client):
        pb = self._pb_with_file()
        with patch.object(playbook_views, "extract_file_from_archive", side_effect=ValueError("文件不存在")):
            resp = su_client.get(f"{URL}{pb.id}/preview_file/?file_path=ghost.yml")
        assert resp.status_code == 404

    def test_preview_bad_request_returns_400(self, su_client):
        pb = self._pb_with_file()
        with patch.object(playbook_views, "extract_file_from_archive", side_effect=ValueError("二进制文件无法预览")):
            resp = su_client.get(f"{URL}{pb.id}/preview_file/?file_path=bin")
        assert resp.status_code == 400

    def test_preview_unexpected_error_goes_through_exception_handler(self, su_client):
        pb = self._pb_with_file()
        with patch.object(playbook_views, "extract_file_from_archive", side_effect=RuntimeError("boom")):
            resp = su_client.get(f"{URL}{pb.id}/preview_file/?file_path=x.yml")
        # exception_to_response 统一封装为非 2xx
        assert resp.status_code >= 400
