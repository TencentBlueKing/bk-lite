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
