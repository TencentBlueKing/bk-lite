"""parse_tools_yml：元数据转换、密码字段映射、内置工具落库。"""
import uuid
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command

from apps.opspilot.management.commands.parse_tools_yml import Command
from apps.opspilot.models import SkillTools

pytestmark = pytest.mark.django_db


def test_convert_to_target_format_maps_password_and_types():
    cmd = Command()
    result = cmd.convert_to_target_format(
        [
            {
                "name": "mysql",
                "description": "MySQL 工具",
                "constructor": "apps.tools.mysql",
                "tools": ["query"],
                "constructor_parameters": [
                    {"name": "host", "type": "string", "required": True, "description": "地址"},
                    {"name": "password", "type": "string", "required": True, "description": "密码"},
                    {"name": "port", "type": "integer", "required": False, "description": "端口"},
                    {"name": "", "type": "string"},
                ],
            }
        ]
    )
    assert result[0]["id"] == "mysql"
    params = result[0]["params"]
    assert params["password"]["type"] == "password"
    assert params["host"]["type"] == "string"
    assert params["port"]["type"] == "integer"
    assert "" not in params


def test_save_to_database_creates_and_updates_builtin_tools():
    cmd = Command()
    toolkit_id = f"redis-kit-{uuid.uuid4().hex[:8]}"
    toolkits = [
        {
            "id": toolkit_id,
            "name": toolkit_id,
            "description": "Redis",
            "tools": ["get", "set"],
            "params": {
                "host": {"type": "string", "required": True, "description": "h"},
                "pwd": {"type": "password", "required": True, "description": "p"},
                "enabled": {"type": "boolean", "required": False, "description": "e"},
            },
        }
    ]
    cmd.save_to_database(toolkits)
    obj = SkillTools.objects.get(name=toolkit_id, is_build_in=True)
    assert obj.team == [1]
    keys = {i["key"]: i for i in obj.params["kwargs"]}
    assert keys["pwd"]["type"] == "password"
    assert keys["host"]["type"] == "text"
    assert keys["enabled"]["type"] == "checkbox"
    assert obj.params["url"] == f"langchain:{toolkit_id}"

    toolkits[0]["description"] = "Redis 更新"
    cmd.save_to_database(toolkits)
    obj.refresh_from_db()
    assert obj.description == "Redis 更新"


def test_sync_sets_system_tags_and_keeps_user_tags():
    cmd = Command()
    SkillTools.objects.create(
        name="cmdb",
        description="old",
        is_build_in=True,
        tags=["other", "search"],
        user_tags=["机房"],
        system_tags=["stale"],
        team=[1],
    )
    cmd.save_to_database(
        [
            {
                "id": name,
                "name": name,
                "description": name,
                "tools": [],
                "params": {},
            }
            for name in (
                "monitor",
                "alerts",
                "log",
                "cmdb",
                "mysql",
                "oracle",
                "mssql",
                "postgres",
                "redis",
                "elasticsearch",
                "kubernetes",
                "kubernetes_data_collection",
                "jenkins",
                "ssh",
                "shell",
                "activedirectory",
                "duckduckgo",
                "fetch",
                "github",
                "browser_use",
                "agent_browser",
                "current_time",
                "python",
                "attachment_file",
                "ops_analysis_dashboard",
            )
        ]
    )
    expected = {
        "monitor": ["monitoring_alert", "platform_app"],
        "alerts": ["monitoring_alert", "platform_app"],
        "log": ["log", "platform_app"],
        "cmdb": ["asset", "platform_app"],
        "mysql": ["database"],
        "oracle": ["database"],
        "mssql": ["database"],
        "postgres": ["database"],
        "redis": ["database"],
        "elasticsearch": ["database"],
        "kubernetes": ["container"],
        "kubernetes_data_collection": ["container"],
        "jenkins": ["release"],
        "ssh": ["host_identity"],
        "shell": ["host_identity"],
        "activedirectory": ["host_identity"],
        "duckduckgo": ["retrieval"],
        "fetch": ["retrieval"],
        "github": ["retrieval"],
        "browser_use": ["retrieval"],
        "agent_browser": ["retrieval"],
        "current_time": ["general"],
        "python": ["general"],
        "attachment_file": ["general"],
        "ops_analysis_dashboard": ["general", "platform_app"],
    }
    for name, system_tags in expected.items():
        obj = SkillTools.objects.get(name=name, is_build_in=True)
        assert obj.system_tags == system_tags
        if name != "cmdb":
            assert obj.user_tags == []
    cmdb = SkillTools.objects.get(name="cmdb", is_build_in=True)
    assert cmdb.user_tags == ["机房"]
    assert "other" not in cmdb.user_tags
    assert "search" not in cmdb.user_tags

    cmdb.system_tags = ["stale"]
    cmdb.save(update_fields=["system_tags"])
    cmd.save_to_database([{"id": "cmdb", "name": "cmdb", "description": "CMDB", "tools": [], "params": {}}])
    cmdb.refresh_from_db()
    assert cmdb.system_tags == ["asset", "platform_app"]
    assert cmdb.user_tags == ["机房"]


def test_handle_writes_tools_and_raises_on_loader_failure():
    toolkit_id = f"k8s-{uuid.uuid4().hex[:8]}"
    metadata = [{"name": toolkit_id, "description": "k", "tools": [], "constructor_parameters": []}]
    with patch("apps.opspilot.management.commands.parse_tools_yml.ToolsLoader.get_all_tools_metadata", return_value=metadata):
        call_command("parse_tools_yml")
    assert SkillTools.objects.filter(name=toolkit_id, is_build_in=True).exists()

    with patch(
        "apps.opspilot.management.commands.parse_tools_yml.ToolsLoader.get_all_tools_metadata",
        side_effect=RuntimeError("discover failed"),
    ):
        with pytest.raises(CommandError, match="同步失败"):
            call_command("parse_tools_yml")
