"""Playbook 视图测试（批量删除 / 模板下载 / 下载&预览的无文件分支 / 列表&详情）

create / upgrade 的归档解析逻辑在 serializers/playbook 的专项测试中覆盖。
"""

import pytest

from apps.job_mgmt.models import Playbook

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/api/playbook/"


def _make(**over):
    defaults = {"name": "pb", "version": "v1.0.0", "team": [1]}
    defaults.update(over)
    return Playbook.objects.create(**defaults)


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
