"""目标管理视图测试（含纯函数 + RPC mock 的 HTTP 集成）"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.job_mgmt.models import Target, TargetTeamConcurrentUpdateError
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


@pytest.mark.unit
def test_update_maps_concurrent_team_change_to_client_error():
    view = target_views.TargetViewSet()
    with patch(
        "apps.core.utils.viewset_utils.AuthViewSet.update",
        side_effect=TargetTeamConcurrentUpdateError("Target.team 已被并发修改，请刷新后重试"),
    ):
        response = view.update(SimpleNamespace(user=SimpleNamespace(is_superuser=True)))

    assert response.status_code == 400
    assert "刷新后重试" in response.data["detail"]


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

    def test_view_only_user_cannot_update_or_delete_target(self, api_client, authenticated_user):
        target = Target.objects.create(name="view-only", ip="10.0.0.8", team=[1])
        authenticated_user.is_superuser = False
        authenticated_user.permission = {"job": {"target-View"}}
        authenticated_user.group_list = [{"id": 1, "name": "Default"}]
        api_client.cookies["current_team"] = "1"
        rules = {"team": [1], "instance": []}

        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules):
            update_resp = api_client.put(f"{URL}{target.id}/", {"name": "hacked"}, format="json")
            delete_resp = api_client.delete(f"{URL}{target.id}/")

        assert update_resp.status_code == 403
        assert delete_resp.status_code == 403
        target.refresh_from_db()
        assert target.name == "view-only"

    def test_api_key_integer_group_list_can_list_targets(self, api_client, authenticated_user):
        Target.objects.create(name="api-key-host", ip="10.0.0.9", team=[1])
        authenticated_user.is_superuser = False
        authenticated_user.permission = {"job": {"target-View"}}
        authenticated_user.group_list = [1]
        api_client.cookies["current_team"] = "1"
        rules = {"team": [1], "instance": []}

        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules):
            resp = api_client.get(URL)

        assert resp.status_code == 200
        assert "api-key-host" in str(resp.data)

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
    def test_query_nodes_forwards_keyword_for_name_or_ip_fuzzy_search(self, su_client):
        with patch("apps.job_mgmt.views.target.SystemMgmt") as MSys, patch("apps.job_mgmt.views.target.NodeMgmt") as MNode, patch(
            "apps.job_mgmt.views.target.CloudRegion"
        ) as MCR:
            MSys.return_value.get_authorized_groups_scoped.return_value = {"data": [1]}
            MNode.return_value.node_list.return_value = {"count": 0, "nodes": []}
            MCR.objects.all.return_value.values.return_value = []

            resp = su_client.get(f"{URL}query_nodes/?page=1&page_size=20&keyword=10.93.160.2")

        assert resp.status_code == 200
        query_data = MNode.return_value.node_list.call_args.args[0]
        assert query_data["keyword"] == "10.93.160.2"

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


@pytest.mark.integration
def test_job_vault_refs_count_only_direct_bindings():
    from apps.job_mgmt.nats_api import job_count_credential_refs

    for name, source in (("a", "credential"), ("b", "credential"), ("c", "manual")):
        Target.objects.create(name=name, ip="10.0.0.1", credential_id="crd-a", credential_source=source)
    assert job_count_credential_refs(["crd-a", "crd-a", "crd-b"]) == {"result": True, "data": {"counts": {"crd-a": 2, "crd-b": 0}}}
    assert job_count_credential_refs([]) == {"result": True, "data": {"counts": {}}}
    assert job_count_credential_refs(["x"] * 101)["result"] is False


@pytest.mark.integration
def test_vault_bind_clears_local_credentials_and_requires_new_secret_on_switch_back(su_client):
    target = Target.objects.create(
        name="manual",
        ip="10.0.0.1",
        cloud_region_id=1,
        ssh_user="root",
        ssh_password="old-cipher",
        ssh_key_passphrase="old-passphrase",
        winrm_password="old-winrm",
        team=[1],
    )
    with patch("apps.job_mgmt.serializers.target.describe_target_credential", return_value={"type": "ssh", "name": "主机账号", "disabled": False}):
        response = su_client.patch(f"{URL}{target.pk}/", {"credential_source": "credential", "credential_id": "crd-ssh-1"}, format="json")
    assert response.status_code == 200
    assert response.data["credential_name"] == "主机账号"
    assert response.data["credential_available"] is True
    target.refresh_from_db()
    assert target.credential_id == "crd-ssh-1"
    assert not any((target.ssh_user, target.ssh_password, target.ssh_key_passphrase, target.ssh_key_file, target.winrm_password, target.winrm_user))
    response = su_client.patch(f"{URL}{target.pk}/", {"credential_source": "manual", "ssh_user": "root"}, format="json")
    assert response.status_code == 400
    response = su_client.patch(
        f"{URL}{target.pk}/", {"credential_source": "manual", "ssh_user": "root", "ssh_password": "replacement"}, format="json"
    )
    assert response.status_code == 200
    target.refresh_from_db()
    assert target.credential_id == ""
    assert target.ssh_password and target.ssh_password != "replacement"


@pytest.mark.integration
@pytest.mark.parametrize("os_type", ["linux", "windows"])
def test_saved_vault_probe_uses_new_draft_without_saving(su_client, os_type):
    target = Target.objects.create(
        name="old", ip="10.0.0.1", os_type=os_type, cloud_region_id=1, credential_source="credential", credential_id="old", team=[1]
    )
    host_credential = {"user": "vault-user", "password": "secret"}
    with patch.object(ExecutionTaskBaseService, "_build_host_credentials", return_value=[host_credential]) as build, patch(
        "apps.job_mgmt.views.target._get_executor_node", return_value="node"
    ), patch.object(ExecutionTaskBaseService, "_get_ansible_node", return_value="ansible"), patch.object(
        target_views, "Executor"
    ) as ssh, patch.object(
        target_views, "AnsibleExecutor"
    ) as win:
        ssh.return_value.execute_ssh.return_value = "success"
        win.return_value.task_query.return_value = {"status": "success"}
        result = su_client.post(
            f"{URL}{target.pk}/test_connection/",
            {"ip": "10.0.0.2", "credential_id": "new", "ssh_password": "ignored", "winrm_password": "ignored", "winrm_user": "ignored"},
            format="json",
        )
    assert result.data["success"] is True
    draft = build.call_args.args[0][0]
    assert draft.ip == "10.0.0.2" and draft.credential_id == "new"
    assert build.call_args.kwargs["actor"]["current_team"] == 1
    credential = (
        ssh.return_value.execute_ssh.call_args.kwargs if os_type == "linux" else win.return_value.adhoc.call_args.kwargs["host_credentials"][0]
    )
    assert credential["password"] == "secret"
    assert credential.get("username", credential.get("user")) == "vault-user"
    target.refresh_from_db()
    assert target.ip == "10.0.0.1" and target.credential_id == "old"
    assert "secret" not in str(result.data)


@pytest.mark.integration
def test_saved_connection_viewer_can_only_probe_unchanged_authorized_target(api_client, authenticated_user):
    target = Target.objects.create(name="saved", ip="10.0.0.1", cloud_region_id=1, ssh_user="host", ssh_password="cipher", team=[1])
    authenticated_user.is_superuser = False
    authenticated_user.group_list = [1]
    authenticated_user.permission = {"job": {"target-View"}}
    api_client.cookies["current_team"] = "1"
    url = f"{URL}{target.pk}/test_connection/"
    with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value={"team": [1], "instance": []}), patch.object(
        ExecutionTaskBaseService, "_build_host_credentials", return_value=[{"password": "saved"}]
    ), patch.object(target_views, "_get_executor_node", return_value="node"), patch.object(target_views, "Executor") as executor:
        executor.return_value.execute_ssh.return_value = "success"
        assert api_client.post(url, {}, format="json").data["success"] is True
        for changes in ({"ip": "10.0.0.2"}, {"ssh_password": "alternate"}, {"credential_source": "credential", "credential_id": "crd-ssh-a"}):
            assert api_client.post(url, changes, format="json").status_code == 403
        assert api_client.post(f"{URL}test_connection/", {"ip": "10.0.0.2"}, format="json").status_code == 403
        target.team = [2]
        target.save()
        assert api_client.post(url, {}, format="json").status_code == 403
        assert executor.return_value.execute_ssh.call_count == 1


@pytest.mark.integration
def test_list_fetches_vault_names_once_and_omits_hidden_names():
    from rest_framework.test import APIRequestFactory

    from apps.job_mgmt.serializers.target import TargetSerializer

    rows = [
        Target(name=key, ip="10.0.0.1", credential_source="credential", credential_id=key, team=[1])
        for key in ["active", "active", "disabled", "invisible"]
    ]
    request = APIRequestFactory().get(URL)
    request.user = SimpleNamespace(username="op", domain="test", group_list=[])
    request.COOKIES["current_team"] = "1"
    descriptions = {"active": {"name": "active ssh", "type": "ssh", "disabled": False}, "disabled": {"name": "old", "type": "ssh", "disabled": True}}
    with patch("apps.job_mgmt.serializers.target.describe_target_credentials", return_value=descriptions) as describe:
        data = TargetSerializer(rows, many=True, context={"request": request}).data
    assert [(row["credential_name"], row["credential_available"]) for row in data] == [
        ("active ssh", True),
        ("active ssh", True),
        ("old", False),
        ("", False),
    ]
    describe.assert_called_once()
    assert set(describe.call_args.args[0]) == {"active", "disabled", "invisible"}


@pytest.mark.integration
def test_vault_binding_rejects_disabled_and_invisible_credentials(su_client):
    payload = TestTargetCrud()._payload(credential_source="credential", credential_id="unusable")
    with patch("apps.job_mgmt.serializers.target.describe_target_credential", return_value={"name": "old", "disabled": True}):
        assert su_client.post(URL, payload, format="json").status_code == 400
    with patch("apps.job_mgmt.serializers.target.describe_target_credential", side_effect=ValueError("credential unavailable")):
        assert su_client.post(URL, payload, format="json").status_code == 400
    assert not Target.objects.exists()


@pytest.mark.integration
@pytest.mark.parametrize("os_type,stage", [("linux", "ssh"), ("windows", "winrm")])
def test_probe_upstream_exception_omits_secret_from_logs_and_response(su_client, caplog, os_type, stage):
    sentinel = "sensitive-error-password"
    with patch.object(target_views, "_get_executor_node", return_value="node"), patch.object(
        ExecutionTaskBaseService, "_get_ansible_node", return_value="ansible"
    ), patch.object(target_views, "Executor") as ssh, patch.object(target_views, "AnsibleExecutor") as win:
        ssh.return_value.execute_ssh.side_effect = RuntimeError(sentinel)
        win.return_value.adhoc.side_effect = RuntimeError(sentinel)
        result = su_client.post(
            f"{URL}test_connection/", TestTargetCrud()._payload(os_type=os_type, winrm_user="usr", winrm_password="pw"), format="json"
        )
    assert result.status_code == 200 and result.data["success"] is False
    assert sentinel not in str(result.data) and sentinel not in caplog.text
    records = [r for r in caplog.records if "job_connection_test_failed" in r.getMessage()]
    assert len(records) == 1
    record = records[0]
    assert record.msg == f"event=job_connection_test_failed region_id=%s failed_stage={stage} error_type=%s"
    assert record.args == (1, "RuntimeError")
    assert record.getMessage() == f"event=job_connection_test_failed region_id=1 failed_stage={stage} error_type=RuntimeError"
    assert record.exc_info is not None and record.exc_info[2] is not None
    assert sum(bool(r.exc_info) for r in caplog.records) == 1
    assert str(record.exc_info[1]) == "RuntimeError"


@pytest.mark.integration
def test_real_vault_rotation_reaches_http_probe_and_disable_prevents_dispatch(su_client, authenticated_user):
    from apps.system_mgmt.models import Group, User
    from apps.system_mgmt.services.credential_service import create_credential, seed_builtin_types, set_disabled, update_credential

    team = Group.objects.create(name="probe-team")
    su_client.cookies["current_team"] = str(team.pk)
    User.objects.create(username=authenticated_user.username, domain=authenticated_user.domain, group_list=[team.pk])
    owner = {"username": authenticated_user.username, "domain": authenticated_user.domain, "current_team": team.pk, "group_list": [team.pk]}
    seed_builtin_types()
    credential = create_credential(
        {"type": "ssh", "name": "Linux 登录", "fields": {"auth_method": "password", "username": "ssh-user", "password": "first"}, "group_id": team.pk},
        actor=owner,
    )
    created = su_client.post(
        URL, TestTargetCrud()._payload(team=[team.pk], credential_source="credential", credential_id=credential.credential_id), format="json"
    )
    assert created.status_code == 201
    target = Target.objects.get(pk=created.data["id"])
    assert target.credential_id == credential.credential_id and not target.ssh_password
    assert created.data["credential_name"] == "Linux 登录"
    update_credential(credential.credential_id, {"fields": {"password": "second"}}, actor=owner)
    url = f"{URL}{target.pk}/test_connection/"
    with patch.object(target_views, "_get_executor_node", return_value="node"), patch.object(target_views, "Executor") as executor:
        executor.return_value.execute_ssh.return_value = "success"
        checked = su_client.post(url, {}, format="json")
        assert checked.data["success"] is True
        assert executor.return_value.execute_ssh.call_args.kwargs["password"] == "second"
        assert "second" not in str(checked.data)
        update_credential(
            credential.credential_id,
            {"fields": {"auth_method": "key", "private_key": "private-key-content", "passphrase": "key-passphrase"}},
            actor=owner,
        )
        assert su_client.post(url, {}, format="json").data["success"] is True
        call = executor.return_value.execute_ssh.call_args.kwargs
        assert call["private_key"] == "private-key-content" and call["passphrase"] == "key-passphrase" and call["password"] is None
        set_disabled(credential.credential_id, True, actor=owner)
        assert su_client.post(url, {}, format="json").data["success"] is False
        assert executor.return_value.execute_ssh.call_count == 2
    assert su_client.get(f"{URL}{target.pk}/").data["credential_available"] is False


@pytest.mark.integration
def test_vault_winrm_requires_ansible_for_save_and_test(su_client):
    payload = TestTargetCrud()._payload(os_type="windows", credential_source="credential", credential_id="winrm-id", driver="sidecar")
    for url in (URL, f"{URL}test_connection/"):
        response = su_client.post(url, payload, format="json")
        assert response.status_code == 400
        assert "driver" in response.data


@pytest.mark.integration
def test_switch_to_vault_removes_key_after_last_committed_reference(su_client, django_capture_on_commit_callbacks):
    storage = Target._meta.get_field("ssh_key_file").storage
    key_name = "ssh_keys/legacy-shared.pem"
    rows = [Target.objects.create(name=name, ip="10.0.0.1", cloud_region_id=1, ssh_key_file=key_name, team=[1]) for name in ("a", "b")]
    with patch.object(storage, "delete") as delete, patch(
        "apps.job_mgmt.serializers.target.describe_target_credential", return_value={"type": "ssh", "name": "host", "disabled": False}
    ):
        for target in rows:
            with django_capture_on_commit_callbacks(execute=True):
                response = su_client.patch(f"{URL}{target.pk}/", {"credential_source": "credential", "credential_id": "host-login"}, format="json")
                assert response.status_code == 200
                assert not Target.objects.get(pk=target.pk).ssh_key_file
                delete.assert_not_called()
        delete.assert_called_once_with(key_name)
