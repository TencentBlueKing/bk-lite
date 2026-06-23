"""target 视图补充单测：_get_executor_node 纯助手 / 非超管 query_nodes 注入 permission_data /
test_connection 密钥分支与失败文案分支。

只 mock 外部边界（NodeMgmt / SystemMgmt / Executor RPC），断言真实分支与契约。
"""

import pydantic.root_model  # noqa
import io
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.job_mgmt.views import target as target_views

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/api/target/"


class TestGetExecutorNode:
    """覆盖 39-54。"""

    def test_returns_first_node_id(self):
        with patch.object(target_views, "NodeMgmt") as MNode:
            MNode.return_value.node_list.return_value = {"nodes": [{"id": "node-7"}]}
            assert target_views._get_executor_node(3) == "node-7"
        # 契约：以 container 节点 + skip_permission 查询
        passed = MNode.return_value.node_list.call_args[0][0]
        assert passed["cloud_region_id"] == 3
        assert passed["is_container"] is True
        assert passed["skip_permission"] is True

    def test_non_dict_result_raises(self):
        with patch.object(target_views, "NodeMgmt") as MNode:
            MNode.return_value.node_list.return_value = None
            with pytest.raises(ValueError, match="未找到可用的执行节点"):
                target_views._get_executor_node(3)

    def test_empty_nodes_raises(self):
        with patch.object(target_views, "NodeMgmt") as MNode:
            MNode.return_value.node_list.return_value = {"nodes": []}
            with pytest.raises(ValueError, match="未找到可用的执行节点"):
                target_views._get_executor_node(3)


class TestQueryNodesNonSuperuser:
    """覆盖 202：非超管时注入 permission_data。"""

    def test_non_superuser_injects_permission_data(self, api_client, authenticated_user):
        authenticated_user.is_superuser = False
        # 授予 target-View 权限以穿过 @HasPermission，专注验证非超管的 permission_data 注入分支
        authenticated_user.permission = {"job": {"target-View"}}
        api_client.cookies["current_team"] = "5"
        with patch.object(target_views, "SystemMgmt") as MSys, patch.object(target_views, "NodeMgmt") as MNode, patch.object(
            target_views, "CloudRegion"
        ) as MCR:
            MSys.return_value.get_authorized_groups_scoped.return_value = {"data": [5]}
            MNode.return_value.node_list.return_value = {"count": 0, "nodes": []}
            MCR.objects.all.return_value.values.return_value = []
            resp = api_client.get(f"{URL}query_nodes/")
        assert resp.status_code == 200
        # 验证给 node_list 的查询里带上了 permission_data（非超管分支）
        query = MNode.return_value.node_list.call_args[0][0]
        assert "permission_data" in query
        assert query["permission_data"]["current_team"] == 5


class TestTestConnectionExtraBranches:
    def test_key_credential_reads_file_and_passes_private_key(self, su_client):
        """覆盖 330-332：密钥方式读取上传文件内容并传 private_key。"""
        key_file = SimpleUploadedFile("id_rsa", b"PRIVATE-KEY-CONTENT", content_type="application/octet-stream")
        with patch.object(target_views, "_get_executor_node", return_value="node-1"), patch.object(
            target_views, "Executor"
        ) as MExec:
            MExec.return_value.execute_ssh.return_value = {"success": True, "result": "success"}
            resp = su_client.post(
                f"{URL}test_connection/",
                {
                    "ip": "10.0.0.1",
                    "os_type": "linux",
                    "cloud_region_id": 1,
                    "ssh_user": "root",
                    "ssh_credential_type": "key",
                    "ssh_key_file": key_file,
                },
                format="multipart",
            )
        assert resp.status_code == 200
        assert resp.data["success"] is True
        # 契约：private_key 取自上传文件内容、password 为 None
        kwargs = MExec.return_value.execute_ssh.call_args.kwargs
        assert kwargs["private_key"] == "PRIVATE-KEY-CONTENT"
        assert kwargs["password"] is None

    def test_failure_result_builds_friendly_message(self, su_client):
        """覆盖 354-357：success=False → 走失败文案构造分支。"""
        with patch.object(target_views, "_get_executor_node", return_value="node-1"), patch.object(
            target_views, "Executor"
        ) as MExec:
            MExec.return_value.execute_ssh.return_value = {
                "success": False,
                "result": "",
                "error": "auth failed",
                "stage": "ssh_dial",
                "category": "auth",
            }
            resp = su_client.post(
                f"{URL}test_connection/",
                {"ip": "10.0.0.1", "os_type": "linux", "cloud_region_id": 1, "ssh_user": "root", "ssh_password": "x"},
                format="json",
            )
        assert resp.status_code == 200
        assert resp.data["success"] is False
        # normalize_executor_error 对 ssh_dial+auth 映射为认证失败文案
        assert "认证失败" in resp.data["message"]
