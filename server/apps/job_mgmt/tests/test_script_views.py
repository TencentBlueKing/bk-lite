"""脚本库视图测试（CRUD + 高危命令拦截 + 批量删除）"""

from unittest.mock import patch

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

    def test_create_allows_same_name_in_different_organizations(self, su_client):
        Script.objects.create(name="巡检模板", content="echo team one", script_type="shell", team=[1])

        resp = su_client.post(
            URL,
            {"name": "巡检模板", "content": "echo team two", "script_type": "shell", "team": [2]},
            format="json",
        )

        assert resp.status_code == 201
        assert Script.objects.filter(name="巡检模板").count() == 2

    def test_create_rejects_same_name_in_any_selected_organization(self, su_client):
        Script.objects.create(name="巡检模板", content="echo existing", script_type="shell", team=[2])

        resp = su_client.post(
            URL,
            {"name": "巡检模板", "content": "echo duplicate", "script_type": "shell", "team": [1, 2]},
            format="json",
        )

        assert resp.status_code == 400
        assert "组织内" in str(resp.data["name"])
        assert Script.objects.filter(name="巡检模板").count() == 1

    def test_create_blocked_by_dangerous_command(self, su_client):
        DangerousRule.objects.create(name="no-rm", pattern="rm -rf", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[])
        resp = su_client.post(URL, {"name": "bad", "content": "rm -rf /", "script_type": "shell", "team": [1]}, format="json")
        assert resp.status_code == 400
        assert "高危命令" in resp.data["error"] or "high-risk" in resp.data["error"]

    def test_list_and_retrieve(self, su_client):
        s = Script.objects.create(name="s1", content="echo", script_type="shell", team=[1])
        assert su_client.get(URL).status_code == 200
        resp = su_client.get(f"{URL}{s.id}/")
        assert resp.status_code == 200
        assert resp.data["name"] == "s1"

    def test_normal_user_list_does_not_include_instance_rule_from_other_current_team(self, api_client, authenticated_user):
        current = Script.objects.create(name="巡检模板", content="echo current", script_type="shell", team=[1])
        foreign = Script.objects.create(name="巡检模板", content="echo foreign", script_type="shell", team=[2])
        authenticated_user.is_superuser = False
        authenticated_user.group_list = [{"id": 1, "name": "Current"}, {"id": 2, "name": "Foreign"}]
        authenticated_user.permission = {"job": {"script_library-View"}}
        api_client.cookies["current_team"] = "1"
        rules = {
            "team": [1],
            "instance": [{"id": foreign.id, "permission": ["View"]}],
        }

        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules):
            response = api_client.get(URL)

        assert response.status_code == 200
        assert [item["id"] for item in response.data] == [current.id]

    def test_normal_user_foreign_instance_rule_returns_permission_error_on_retrieve(self, api_client, authenticated_user):
        foreign = Script.objects.create(name="外部模板", content="echo foreign", script_type="shell", team=[2])
        authenticated_user.is_superuser = False
        authenticated_user.group_list = [{"id": 1, "name": "Current"}, {"id": 2, "name": "Foreign"}]
        authenticated_user.permission = {"job": {"script_library-View"}}
        api_client.cookies["current_team"] = "1"
        rules = {
            "team": [],
            "instance": [{"id": foreign.id, "permission": ["View"]}],
        }

        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules):
            response = api_client.get(f"{URL}{foreign.id}/")

        assert response.status_code == 200
        assert response.json()["result"] is False
        assert "id" not in response.json()

    def test_update_script(self, su_client):
        s = Script.objects.create(name="s1", content="echo", script_type="shell", team=[1])
        resp = su_client.put(f"{URL}{s.id}/", {"name": "s1-edit", "content": "echo 2", "script_type": "shell", "team": [1]}, format="json")
        assert resp.status_code == 200
        s.refresh_from_db()
        assert s.name == "s1-edit"

    @pytest.mark.parametrize("next_team", ([2], [1, 2]))
    def test_update_rejects_transfer_or_add_to_organization_with_same_name(self, su_client, next_team):
        moving = Script.objects.create(name="巡检模板", content="echo moving", script_type="shell", team=[1])
        Script.objects.create(name="巡检模板", content="echo existing", script_type="shell", team=[2])

        resp = su_client.put(
            f"{URL}{moving.id}/",
            {"name": "巡检模板", "content": "echo moving", "script_type": "shell", "team": next_team},
            format="json",
        )

        assert resp.status_code == 400
        assert "组织内" in str(resp.data["name"])
        moving.refresh_from_db()
        assert moving.team == [1]

    def test_update_rejects_rename_to_same_name_in_current_organization(self, su_client):
        current = Script.objects.create(name="原脚本", content="echo current", script_type="shell", team=[1])
        Script.objects.create(name="巡检模板", content="echo existing", script_type="shell", team=[1])

        resp = su_client.put(
            f"{URL}{current.id}/",
            {"name": "巡检模板", "content": "echo current", "script_type": "shell", "team": [1]},
            format="json",
        )

        assert resp.status_code == 400
        current.refresh_from_db()
        assert current.name == "原脚本"

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

    def test_export_returns_zip_and_strips_encrypted_defaults(self, su_client):
        from apps.job_mgmt.services.param_crypto import ParamCrypto

        params = [{"name": "pwd", "default": "secret", "is_encrypted": True}]
        ParamCrypto.encrypt_param_defaults(params)
        s = Script.objects.create(name="exp", content="echo hi", script_type="shell", params=params, team=[1])

        resp = su_client.post(f"{URL}export/", {"ids": [s.id]}, format="json")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/zip"

        import io
        import json
        import zipfile

        with zipfile.ZipFile(io.BytesIO(b"".join(resp.streaming_content))) as zf:
            meta = json.loads(zf.read("exp/meta.json"))
            assert meta["params"][0]["default"] == ""
            assert meta["params"][0]["is_encrypted"] is True

    def test_export_rejects_missing_or_inaccessible_ids(self, su_client):
        s = Script.objects.create(name="exp", content="echo", script_type="shell", team=[1])
        resp = su_client.post(f"{URL}export/", {"ids": [s.id, 999999]}, format="json")
        assert resp.status_code == 400
        error_text = str(resp.data)
        assert "无权" in error_text or "不存在" in error_text or "cannot be exported" in error_text or "do not exist" in error_text

    def test_import_creates_skips_and_reports(self, su_client):
        import io
        import json
        import zipfile

        from django.core.files.uploadedfile import SimpleUploadedFile

        Script.objects.create(name="exists", content="echo old", script_type="shell", team=[1])

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"format_version": 1, "script_count": 2}))
            for name, content in (("exists", "echo new"), ("fresh", "echo fresh")):
                zf.writestr(
                    f"{name}/meta.json",
                    json.dumps(
                        {
                            "format_version": 1,
                            "name": name,
                            "description": "",
                            "script_type": "shell",
                            "timeout": 60,
                            "params": [{"name": "pwd", "default": "x", "is_encrypted": True}],
                        }
                    ),
                )
                zf.writestr(f"{name}/script.sh", content)
        upload = SimpleUploadedFile("pack.zip", buf.getvalue(), content_type="application/zip")

        resp = su_client.post(f"{URL}import/", {"file": upload, "team": [1]}, format="multipart")
        assert resp.status_code == 200
        assert len(resp.data["created"]) == 1
        assert resp.data["created"][0]["name"] == "fresh"
        assert len(resp.data["skipped"]) == 1
        assert resp.data["skipped"][0]["name"] == "exists"
        created = Script.objects.get(name="fresh", team=[1])
        assert created.params[0]["default"] == ""

    def test_update_keeps_encrypted_default_when_mask_echoed(self, su_client):
        """二次编辑未改加密默认值时，回传 ****** 不得覆盖库中原密文。"""
        from apps.job_mgmt.services.param_crypto import MASKED_DEFAULT, ParamCrypto

        create_resp = su_client.post(
            URL,
            {
                "name": "enc-script",
                "content": 'Write-Host "你输入的内容是：$InputStr"',
                "script_type": "powershell",
                "team": [1],
                "params": [
                    {
                        "name": "testpassword",
                        "default": "test123456",
                        "is_encrypted": True,
                        "is_required": True,
                    }
                ],
            },
            format="json",
        )
        assert create_resp.status_code == 201
        script_id = create_resp.data["id"]

        detail = su_client.get(f"{URL}{script_id}/")
        assert detail.status_code == 200
        assert detail.data["params"][0]["default"] == MASKED_DEFAULT

        update_resp = su_client.put(
            f"{URL}{script_id}/",
            {
                "name": "enc-script",
                "description": "只改描述",
                "content": 'Write-Host "你输入的内容是：$InputStr"',
                "script_type": "powershell",
                "team": [1],
                "params": [
                    {
                        "name": "testpassword",
                        "default": MASKED_DEFAULT,
                        "is_encrypted": True,
                        "is_required": True,
                    }
                ],
            },
            format="json",
        )
        assert update_resp.status_code == 200
        assert update_resp.data["params"][0]["default"] == MASKED_DEFAULT

        script = Script.objects.get(pk=script_id)
        assert script.description == "只改描述"
        assert script.params[0]["default"] != MASKED_DEFAULT
        assert script.params[0]["default"] != "test123456"

        ready = ParamCrypto.prepare_params_for_execution({}, script.params)
        assert ready["testpassword"] == "test123456"


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
