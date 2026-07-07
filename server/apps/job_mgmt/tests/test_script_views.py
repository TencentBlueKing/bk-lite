"""脚本库视图测试（CRUD + 高危命令拦截 + 批量删除）"""

import pytest

from apps.job_mgmt.constants import DangerousLevel
from apps.job_mgmt.models import DangerousRule, Script

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/api/script/"


class TestScriptCrud:
    def test_create_script(self, su_client):
        resp = su_client.post(URL, {"name": "s1", "content": "echo hi", "script_type": "shell", "team": [1]}, format="json")
        assert resp.status_code == 201
        assert Script.objects.filter(name="s1").exists()

    def test_create_blocked_by_dangerous_command(self, su_client):
        DangerousRule.objects.create(name="no-rm", pattern="rm -rf", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        resp = su_client.post(URL, {"name": "bad", "content": "rm -rf /", "script_type": "shell", "team": [1]}, format="json")
        assert resp.status_code == 400
        assert "高危命令" in resp.data["error"]

    def test_list_and_retrieve(self, su_client):
        s = Script.objects.create(name="s1", content="echo", script_type="shell", team=[1])
        assert su_client.get(URL).status_code == 200
        resp = su_client.get(f"{URL}{s.id}/")
        assert resp.status_code == 200
        assert resp.data["name"] == "s1"

    def test_update_script(self, su_client):
        s = Script.objects.create(name="s1", content="echo", script_type="shell", team=[1])
        resp = su_client.put(f"{URL}{s.id}/", {"name": "s1-edit", "content": "echo 2", "script_type": "shell", "team": [1]}, format="json")
        assert resp.status_code == 200
        s.refresh_from_db()
        assert s.name == "s1-edit"

    def test_update_blocked_by_dangerous_command(self, su_client):
        DangerousRule.objects.create(name="no-rm", pattern="rm -rf", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        s = Script.objects.create(name="s1", content="echo", script_type="shell", team=[1])
        resp = su_client.put(f"{URL}{s.id}/", {"name": "s1", "content": "rm -rf /", "script_type": "shell", "team": [1]}, format="json")
        assert resp.status_code == 400

    def test_batch_delete(self, su_client):
        s1 = Script.objects.create(name="s1", content="echo", script_type="shell", team=[1])
        s2 = Script.objects.create(name="s2", content="echo", script_type="shell", team=[1])
        resp = su_client.post(f"{URL}batch_delete/", {"ids": [s1.id, s2.id]}, format="json")
        assert resp.status_code == 200
        assert resp.data["deleted_count"] == 2


class TestScriptNormalizeLineEndings:
    """入库前规范化脚本换行符（CRLF/CR → LF；bat/powershell 保留）。"""

    def test_create_normalizes_crlf_to_lf(self, su_client):
        resp = su_client.post(
            URL,
            {"name": "crlf", "content": "echo a\r\necho b\r\n", "script_type": "shell", "team": [1]},
            format="json",
        )
        assert resp.status_code == 201
        s = Script.objects.get(name="crlf")
        assert "\r" not in s.content
        # 末尾 \n 可能在 DB 层被 strip, 断言 startswith
        assert s.content.startswith("echo a\necho b")

    def test_create_bare_cr_to_lf(self, su_client):
        resp = su_client.post(
            URL,
            {"name": "cr", "content": "a\rb\rc", "script_type": "shell", "team": [1]},
            format="json",
        )
        assert resp.status_code == 201
        s = Script.objects.get(name="cr")
        # 不严格断言末尾 \n（SQLite 等后端会自动 strip TextField 末尾空白）
        assert "\r" not in s.content
        assert s.content.startswith("a\nb\nc")

    def test_create_bat_keeps_crlf(self, su_client):
        crlf = "@echo off\r\nset x=1\r\n"
        resp = su_client.post(
            URL,
            {"name": "bat", "content": crlf, "script_type": "bat", "team": [1]},
            format="json",
        )
        assert resp.status_code == 201
        s = Script.objects.get(name="bat")
        # bat 必须保留 CRLF（Windows 原生脚本）
        assert "\r" in s.content

    def test_update_normalizes_crlf_to_lf(self, su_client):
        s = Script.objects.create(name="s1", content="echo", script_type="shell", team=[1])
        resp = su_client.put(
            f"{URL}{s.id}/",
            {"name": "s1", "content": "echo 1\r\necho 2\r\n", "script_type": "shell", "team": [1]},
            format="json",
        )
        assert resp.status_code == 200
        s.refresh_from_db()
        assert "\r" not in s.content
        assert s.content.startswith("echo 1\necho 2")

    def test_update_partial_no_content_keeps_existing(self, su_client):
        """PATCH 不传 content 时 instance 原值不动;避免误规范化。"""
        s = Script.objects.create(name="s1", content="echo", script_type="shell", team=[1])
        resp = su_client.patch(f"{URL}{s.id}/", {"description": "no-content-change"}, format="json")
        assert resp.status_code == 200
        s.refresh_from_db()
        assert s.content == "echo"

    def test_create_lf_unchanged(self, su_client):
        lf = "#!/bin/bash\necho hi\n"
        resp = su_client.post(
            URL,
            {"name": "lf", "content": lf, "script_type": "shell", "team": [1]},
            format="json",
        )
        assert resp.status_code == 201
        s = Script.objects.get(name="lf")
        assert "\r" not in s.content
        assert s.content.startswith("#!/bin/bash\necho hi")
