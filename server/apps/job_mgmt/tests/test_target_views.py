"""目标管理视图测试（含纯函数 + RPC mock 的 HTTP 集成）"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.job_mgmt.models import Target
from apps.job_mgmt.views import target as target_views

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/api/target/"


# ----------------------------- 纯函数 ----------------------------- #
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


class TestBuildSshTestFailureMessage:
    def test_merges_fallbacks(self):
        msg = target_views._build_ssh_test_failure_message({}, "err-detail", "stdout-detail")
        assert isinstance(msg, str) and msg


# ----------------------------- HTTP ----------------------------- #
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

    def test_create_missing_ssh_password_returns_400(self, su_client):
        resp = su_client.post(URL, self._payload(ssh_password=""), format="json")
        assert resp.status_code == 400

    def test_batch_delete(self, su_client):
        t1 = Target.objects.create(name="t1", ip="10.0.0.2", ssh_user="r", team=[1])
        t2 = Target.objects.create(name="t2", ip="10.0.0.3", ssh_user="r", team=[1])
        resp = su_client.post(f"{URL}batch_delete/", {"ids": [t1.id, t2.id]}, format="json")
        assert resp.status_code == 200
        assert resp.data["deleted_count"] == 2


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


class TestTestConnection:
    def test_windows_not_supported(self, su_client):
        # windows + manual 需带 winrm 凭据才能过序列化器校验，进而到达视图的"暂不支持"分支
        resp = su_client.post(
            f"{URL}test_connection/",
            {"ip": "10.0.0.1", "os_type": "windows", "cloud_region_id": 1, "winrm_user": "admin", "winrm_password": "pw"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["success"] is False
        assert "Windows" in resp.data["message"]

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
