"""SSH 批量上传/探活：空主机拒绝、成功失败汇总、单机异常隔离。"""
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.tools.ssh import batch as batch_mod

pytestmark = pytest.mark.unit


def test_batch_upload_rejects_empty_and_isolates_host_errors():
    with pytest.raises(ValueError, match="主机列表不能为空"):
        batch_mod.batch_upload_files.func(
            hosts=[],
            username="root",
            local_path="/tmp/a",
            remote_path="/tmp/b",
        )

    def fake_upload(**kwargs):
        if kwargs["host"] == "boom":
            raise RuntimeError("sftp down")
        return {"success": kwargs["host"] == "ok", "error": None if kwargs["host"] == "ok" else "denied"}

    upload_tool = MagicMock()
    upload_tool.invoke.side_effect = lambda payload, config=None: fake_upload(**payload)
    with patch.object(batch_mod, "upload_file", upload_tool):
        out = batch_mod.batch_upload_files.func(
            hosts=["ok", "bad", "boom"],
            username="root",
            local_path="/tmp/a.conf",
            remote_path="/etc/a.conf",
            password="p",
        )
    assert out["total"] == 3
    assert out["success_count"] == 1
    assert out["failed_count"] == 2
    assert out["summary"]["successful_hosts"] == ["ok"]
    assert set(out["summary"]["failed_hosts"]) == {"bad", "boom"}
    assert out["results"]["boom"]["error"] == "sftp down"
    assert out["results"]["ok"]["success"] is True


def test_check_hosts_availability_rejects_empty_and_summarizes():
    with pytest.raises(ValueError, match="主机列表不能为空"):
        batch_mod.check_hosts_availability.func(hosts=[], username="root")

    def fake_conn(**kwargs):
        if kwargs["host"] == "raise":
            raise RuntimeError("timeout")
        return {"success": kwargs["host"] == "up"}

    connection_tool = MagicMock()
    connection_tool.invoke.side_effect = lambda payload, config=None: fake_conn(**payload)
    with patch(
        "apps.opspilot.metis.llm.tools.ssh.connection.test_ssh_connection",
        connection_tool,
    ):
        out = batch_mod.check_hosts_availability.func(
            hosts=["up", "down", "raise"],
            username="root",
            password="p",
        )
    assert out["total"] == 3
    assert out["available_count"] == 1
    assert out["unavailable_count"] == 2
    assert out["available_hosts"] == ["up"]
    assert set(out["unavailable_hosts"]) == {"down", "raise"}
    assert out["details"]["raise"]["error"] == "timeout"


def test_batch_execute_isolates_command_exceptions():
    def fake_exec(**kwargs):
        if kwargs["host"] == "boom":
            raise RuntimeError("ssh reset")
        return {"success": True, "stdout": "ok"}

    command_tool = MagicMock()
    command_tool.invoke.side_effect = lambda payload, config=None: fake_exec(**payload)
    with patch.object(batch_mod, "ssh_execute_command", command_tool):
        out = batch_mod.batch_execute_commands.func(
            hosts=["ok", "boom"],
            username="root",
            command="uptime",
        )
    assert out["success_count"] == 1
    assert out["failed_count"] == 1
    assert out["results"]["boom"]["exit_code"] == -1
    assert out["results"]["boom"]["error"] == "ssh reset"
