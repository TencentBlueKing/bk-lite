"""目标管理视图测试（含纯函数 + RPC mock 的 HTTP 集成）"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.job_mgmt.models import Target
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService
from apps.job_mgmt.views import target as target_views

pytestmark = pytest.mark.django_db

URL = "/api/v1/job_mgmt/api/target/"


# ----------------------------- 纯函数 ----------------------------- #
@pytest.mark.unit
class TestParseSshTestResult:
    def test_string_success(self):
        ok, out, err, detail = target_views._parse_ssh_test_result("success")
        assert ok is True and out == "success" and err == "" and detail == {}

    def test_string_failure(self):
        ok, out, err, detail = target_views._parse_ssh_test_result("boom")
        assert ok is False and out == "boom"

    def test_dict_result(self):
        ok, out, err, detail = target_views._parse_ssh_test_result({"success": True, "result": "ok", "error": ""})
        assert ok is True and out == "ok"

    def test_unknown_type(self):
        ok, out, err, detail = target_views._parse_ssh_test_result(123)
        assert ok is False and "未知返回类型" in err


@pytest.mark.unit
class TestBuildActorContext:
    def _req(self, current_team="1", include_children="0", superuser=False):
        user = SimpleNamespace(username="u", domain="domain.com", is_superuser=superuser)
        cookies = {}
        if current_team is not None:
            cookies["current_team"] = current_team
        cookies["include_children"] = include_children
        return SimpleNamespace(user=user, COOKIES=cookies)

    def test_valid(self):
        ctx = target_views._build_actor_context(self._req(current_team="2", include_children="1"))
        assert ctx["current_team"] == 2
        assert ctx["include_children"] is True
        assert ctx["username"] == "u"

    def test_missing_current_team_raises(self):
        with pytest.raises(BaseAppException):
            target_views._build_actor_context(self._req(current_team=None))

    def test_invalid_current_team_raises(self):
        with pytest.raises(BaseAppException):
            target_views._build_actor_context(self._req(current_team="abc"))


@pytest.mark.unit
class TestBuildSshTestFailureMessage:
    def test_merges_fallbacks(self):
        msg = target_views._build_ssh_test_failure_message({}, "err-detail", "stdout-detail")
        assert isinstance(msg, str) and msg


# ----------------------------- HTTP ----------------------------- #
@pytest.mark.integration
class TestTargetCrud:
    def _payload(self, **over):
        p = {
            "name": "host1",
            "ip": "10.0.0.1",
            "os_type": "linux",
            "cloud_region_id": 1,
            "driver": "ansible",
            "credential_source": "manual",
            "ssh_user": "root",
            "ssh_credential_type": "password",
            "ssh_password": "secret",
            "team": [1],
        }
        p.update(over)
        return p

    def test_create_target(self, su_client):
        resp = su_client.post(URL, self._payload(), format="json")
        assert resp.status_code == 201
        assert Target.objects.filter(name="host1").exists()

    @pytest.mark.parametrize(
        ("submitted_value", "expected_value"),
        [
            (True, True),
            (False, False),
        ],
    )
    def test_create_windows_target_respects_explicit_cert_validation(self, su_client, submitted_value, expected_value):
        resp = su_client.post(
            URL,
            self._payload(
                os_type="windows",
                winrm_user="administrator",
                winrm_password="secret",
                winrm_cert_validation=submitted_value,
            ),
            format="json",
        )

        assert resp.status_code == 201
        assert Target.objects.get(name="host1").winrm_cert_validation is expected_value

    def test_create_windows_target_keeps_legacy_default_without_cert_validation(self, su_client):
        resp = su_client.post(
            URL,
            self._payload(os_type="windows", winrm_user="administrator", winrm_password="secret"),
            format="json",
        )

        assert resp.status_code == 201
        assert Target.objects.get(name="host1").winrm_cert_validation is False

    def test_update_windows_target_keeps_stored_false_without_cert_validation(self, su_client):
        target = Target.objects.create(
            name="windows-host",
            ip="10.0.0.2",
            os_type="windows",
            winrm_cert_validation=False,
            team=[1],
        )

        resp = su_client.put(
            f"{URL}{target.id}/",
            self._payload(
                name="windows-host-renamed",
                ip=target.ip,
                os_type="windows",
                winrm_user="administrator",
                winrm_password="secret",
            ),
            format="json",
        )

        assert resp.status_code == 200
        target.refresh_from_db()
        assert target.name == "windows-host-renamed"
        assert target.winrm_cert_validation is False

    @pytest.mark.parametrize("submitted_password", [None, ""])
    def test_update_keeps_saved_ssh_password_when_not_replaced(self, su_client, submitted_password):
        create_resp = su_client.post(URL, self._payload(), format="json")
        target = Target.objects.get(pk=create_resp.data["id"])
        saved_ciphertext = target.ssh_password
        payload = self._payload(name="host1-renamed")
        if submitted_password is None:
            payload.pop("ssh_password")
        else:
            payload["ssh_password"] = submitted_password

        resp = su_client.put(f"{URL}{target.id}/", payload, format="json")

        assert resp.status_code == 200
        target.refresh_from_db()
        assert target.ssh_password == saved_ciphertext
        assert resp.data["has_ssh_password"] is True
        assert "ssh_password" not in resp.data

    def test_target_response_exposes_key_metadata_without_key_content(self, su_client, monkeypatch):
        storage = Target._meta.get_field("ssh_key_file").storage
        monkeypatch.setattr(storage, "save", lambda name, content, max_length=None: name)
        key_file = SimpleUploadedFile("lab-key.pem", b"private-key-content")
        resp = su_client.post(
            URL,
            self._payload(ssh_credential_type="key", ssh_password="", ssh_key_file=key_file),
            format="multipart",
        )

        assert resp.status_code == 201
        assert resp.data["has_ssh_key"] is True
        assert resp.data["ssh_key_file_name"] == "lab-key.pem"
        assert "ssh_key_file" not in resp.data

    def test_update_rejects_credential_type_change_without_replacement(self, su_client):
        create_resp = su_client.post(URL, self._payload(), format="json")

        resp = su_client.put(
            f"{URL}{create_resp.data['id']}/",
            self._payload(ssh_credential_type="key", ssh_password=""),
            format="json",
        )

        assert resp.status_code == 400
        assert "ssh_key_file" in resp.data

    def test_create_missing_ssh_password_returns_400(self, su_client):
        resp = su_client.post(URL, self._payload(ssh_password=""), format="json")
        assert resp.status_code == 400

    def test_batch_delete(self, su_client):
        t1 = Target.objects.create(name="t1", ip="10.0.0.2", ssh_user="r", team=[1])
        t2 = Target.objects.create(name="t2", ip="10.0.0.3", ssh_user="r", team=[1])
        resp = su_client.post(f"{URL}batch_delete/", {"ids": [t1.id, t2.id]}, format="json")
        assert resp.status_code == 200
        assert resp.data["deleted_count"] == 2


@pytest.mark.integration
class TestQueryNodes:
    def test_query_nodes_success(self, su_client):
        with patch("apps.job_mgmt.views.target.SystemMgmt") as MSys, patch("apps.job_mgmt.views.target.NodeMgmt") as MNode, patch(
            "apps.job_mgmt.views.target.CloudRegion"
        ) as MCR:
            MSys.return_value.get_authorized_groups_scoped.return_value = {"data": [1]}
            MNode.return_value.node_list.return_value = {
                "count": 1,
                "nodes": [{"id": "n1", "name": "node1", "ip": "1.2.3.4", "operating_system": "linux", "cloud_region": 1}],
            }
            MCR.objects.all.return_value.values.return_value = [{"id": 1, "name": "region-1"}]
            resp = su_client.get(f"{URL}query_nodes/?page=1&page_size=20&cloud_region_id=1&name=n&ip=1&os=linux")
        assert resp.status_code == 200
        items = resp.data["data"]["items"]
        assert items[0]["cloud_region_name"] == "region-1"
        assert items[0]["source"] == "node_mgmt"

    def test_query_nodes_missing_team_cookie_returns_400(self, api_client, authenticated_user):
        authenticated_user.is_superuser = True
        # 不带 current_team cookie → _build_actor_context 抛 BaseAppException → 400
        resp = api_client.get(f"{URL}query_nodes/")
        assert resp.status_code == 400

    def test_query_nodes_unexpected_error_returns_500(self, su_client):
        with patch("apps.job_mgmt.views.target.SystemMgmt", side_effect=RuntimeError("boom")):
            resp = su_client.get(f"{URL}query_nodes/")
        assert resp.status_code == 500


@pytest.mark.integration
class TestCloudRegions:
    def test_cloud_regions_success(self, su_client):
        with patch("apps.job_mgmt.views.target.NodeMgmt") as MNode:
            MNode.return_value.cloud_region_list.return_value = [{"id": 1, "name": "r1"}]
            resp = su_client.get(f"{URL}cloud_regions/")
        assert resp.status_code == 200
        assert resp.data["data"] == [{"id": 1, "name": "r1"}]

    def test_cloud_regions_error_returns_500(self, su_client):
        with patch("apps.job_mgmt.views.target.NodeMgmt") as MNode:
            MNode.return_value.cloud_region_list.side_effect = RuntimeError("down")
            resp = su_client.get(f"{URL}cloud_regions/")
        assert resp.status_code == 500


@pytest.mark.integration
class TestTestConnection:
    def test_saved_target_connection_uses_stored_password(self, su_client):
        create_resp = su_client.post(URL, TestTargetCrud()._payload(), format="json")
        target_id = create_resp.data["id"]

        with patch("apps.job_mgmt.views.target._get_executor_node", return_value="node-1"), patch(
            "apps.job_mgmt.views.target.Executor"
        ) as executor_cls:
            executor_cls.return_value.execute_ssh.return_value = "success"
            resp = su_client.post(
                f"{URL}{target_id}/test_connection/",
                {
                    "ip": "10.0.0.1",
                    "os_type": "linux",
                    "cloud_region_id": 1,
                    "driver": "ansible",
                    "ssh_port": 22,
                    "ssh_user": "root",
                    "ssh_credential_type": "password",
                },
                format="json",
            )

        assert resp.status_code == 200
        assert resp.data["success"] is True
        assert executor_cls.return_value.execute_ssh.call_args.kwargs["password"] == "secret"

    def test_saved_target_connection_uses_stored_private_key(self, su_client):
        target = Target.objects.create(
            name="key-host",
            ip="10.0.0.2",
            os_type="linux",
            cloud_region_id=1,
            ssh_user="root",
            ssh_credential_type="key",
            ssh_key_file="ssh_keys/lab.pem",
            team=[1],
        )
        with patch("apps.job_mgmt.views.target._get_executor_node", return_value="node-1"), patch(
            "apps.job_mgmt.views.target.ExecutionTaskBaseService._build_host_credentials",
            return_value=[{"private_key_content": "private-key-content"}],
        ), patch("apps.job_mgmt.views.target.Executor") as executor_cls:
            executor_cls.return_value.execute_ssh.return_value = "success"
            resp = su_client.post(
                f"{URL}{target.id}/test_connection/",
                {
                    "ip": target.ip,
                    "os_type": "linux",
                    "cloud_region_id": 1,
                    "driver": "ansible",
                    "ssh_port": 22,
                    "ssh_user": "root",
                    "ssh_credential_type": "key",
                },
                format="json",
            )

        assert resp.status_code == 200
        assert resp.data["success"] is True
        assert executor_cls.return_value.execute_ssh.call_args.kwargs["private_key"] == "private-key-content"

    def test_saved_windows_connection_accepts_false_cert_validation(self, su_client):
        create_resp = su_client.post(
            URL,
            TestTargetCrud()._payload(
                os_type="windows",
                winrm_user="administrator",
                winrm_password="secret",
                winrm_scheme="http",
                winrm_port=5985,
                winrm_cert_validation=False,
            ),
            format="json",
        )
        with patch.object(ExecutionTaskBaseService, "_get_ansible_node", return_value="ansible-node"), patch(
            "apps.job_mgmt.views.target.AnsibleExecutor"
        ) as executor_cls:
            executor_cls.return_value.adhoc.return_value = {"accepted": True, "task_id": "connectivity-task"}
            executor_cls.return_value.task_query.return_value = {"status": "success", "result": {"success": True}}
            resp = su_client.post(
                f"{URL}{create_resp.data['id']}/test_connection/",
                {
                    "ip": "10.0.0.1",
                    "os_type": "windows",
                    "cloud_region_id": 1,
                    "winrm_port": 5985,
                    "winrm_scheme": "http",
                    "winrm_user": "administrator",
                    "winrm_cert_validation": "false",
                },
                format="multipart",
            )

        assert resp.status_code == 200
        assert resp.data["success"] is True
        credential = executor_cls.return_value.adhoc.call_args.kwargs["host_credentials"][0]
        assert credential["password"] == "secret"
        assert credential["winrm_cert_validation"] is False
        assert executor_cls.return_value.adhoc.call_args.kwargs["module"] == "ansible.windows.win_ping"

    def test_node_not_found_returns_success_false(self, su_client):
        with patch("apps.job_mgmt.views.target._get_executor_node", side_effect=ValueError("无可用节点")):
            resp = su_client.post(
                f"{URL}test_connection/",
                {"ip": "10.0.0.1", "os_type": "linux", "cloud_region_id": 1, "ssh_user": "root", "ssh_password": "x"},
                format="json",
            )
        assert resp.status_code == 200
        assert resp.data["success"] is False

    def test_connection_success(self, su_client):
        with patch("apps.job_mgmt.views.target._get_executor_node", return_value="node-1"), patch("apps.job_mgmt.views.target.Executor") as MExec:
            MExec.return_value.execute_ssh.return_value = {"success": True, "result": "success"}
            resp = su_client.post(
                f"{URL}test_connection/",
                {"ip": "10.0.0.1", "os_type": "linux", "cloud_region_id": 1, "ssh_user": "root", "ssh_password": "x"},
                format="json",
            )
        assert resp.status_code == 200
        assert resp.data["success"] is True

    def test_connection_exception_returns_success_false(self, su_client):
        with patch("apps.job_mgmt.views.target._get_executor_node", return_value="node-1"), patch("apps.job_mgmt.views.target.Executor") as MExec:
            MExec.return_value.execute_ssh.side_effect = RuntimeError("ssh boom")
            resp = su_client.post(
                f"{URL}test_connection/",
                {"ip": "10.0.0.1", "os_type": "linux", "cloud_region_id": 1, "ssh_user": "root", "ssh_password": "x"},
                format="json",
            )
        assert resp.status_code == 200
        assert resp.data["success"] is False
