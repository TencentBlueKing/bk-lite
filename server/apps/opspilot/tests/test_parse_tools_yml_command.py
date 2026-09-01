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
