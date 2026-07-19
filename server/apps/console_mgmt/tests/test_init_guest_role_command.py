"""console_mgmt management command init_guest_role 单元测试。

handle 编排：SystemMgmt.create_guest_role -> OpsPilot.get_guest_provider ->
SystemMgmt.create_default_rule。只 mock 两个 RPC 客户端边界，断言调用编排、
参数透传、失败短路分支。
"""
import pydantic.root_model  # noqa

from importlib import import_module
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from apps.console_mgmt.management.commands import init_guest_role as cmd_mod
from apps.system_mgmt.models import GroupDataRule

pytestmark = pytest.mark.unit


def _run():
    cmd = cmd_mod.Command()
    cmd.handle()


def test_全链路成功调用create_default_rule():
    with patch.object(cmd_mod, "SystemMgmt") as MockSys, patch.object(cmd_mod, "OpsPilot") as MockPilot:
        sys_inst = MagicMock()
        sys_inst.create_guest_role.return_value = {"data": {"group_id": 5}}
        sys_inst.create_default_rule.return_value = {"result": True}
        MockSys.return_value = sys_inst

        pilot_inst = MagicMock()
        pilot_inst.get_guest_provider.return_value = {
            "result": True,
            "data": {"llm_model": "llm", "rerank_model": "rr", "embed_model": "emb", "ocr_model": "ocr"},
        }
        MockPilot.return_value = pilot_inst

        _run()

        pilot_inst.get_guest_provider.assert_called_once_with(5)
        sys_inst.create_default_rule.assert_called_once_with("llm", "ocr", "emb", "rr")


@pytest.mark.django_db
def test_真实本地链路首调兼容导出():
    compat_module = import_module("apps.system_mgmt.nats_api")
    assert isinstance(compat_module, ModuleType)

    with patch.object(cmd_mod, "OpsPilot") as MockPilot:
        MockPilot.return_value.get_guest_provider.return_value = {
            "result": True,
            "data": {
                "llm_model": {"id": 1, "name": "llm"},
                "ocr_model": [{"id": 2, "name": "ocr"}],
                "embed_model": [{"id": 3, "name": "embed"}],
                "rerank_model": {"id": 4, "name": "rerank"},
            },
        }

        _run()

    assert GroupDataRule.objects.filter(name="OpsPilot内置规则", app="opspilot").exists()


def test_provider失败时短路不调create_default_rule():
    with patch.object(cmd_mod, "SystemMgmt") as MockSys, patch.object(cmd_mod, "OpsPilot") as MockPilot:
        sys_inst = MagicMock()
        sys_inst.create_guest_role.return_value = {"data": {"group_id": 1}}
        MockSys.return_value = sys_inst

        pilot_inst = MagicMock()
        pilot_inst.get_guest_provider.return_value = {"result": False, "message": "no provider"}
        MockPilot.return_value = pilot_inst

        _run()

        sys_inst.create_default_rule.assert_not_called()


def test_create_default_rule失败走错误日志分支():
    with patch.object(cmd_mod, "SystemMgmt") as MockSys, patch.object(cmd_mod, "OpsPilot") as MockPilot, patch.object(
        cmd_mod, "logger"
    ) as log:
        sys_inst = MagicMock()
        sys_inst.create_guest_role.return_value = {"data": {"group_id": 2}}
        sys_inst.create_default_rule.return_value = {"result": False, "message": "boom"}
        MockSys.return_value = sys_inst

        pilot_inst = MagicMock()
        pilot_inst.get_guest_provider.return_value = {
            "result": True,
            "data": {"llm_model": "a", "rerank_model": "b", "embed_model": "c", "ocr_model": "d"},
        }
        MockPilot.return_value = pilot_inst

        _run()

        # 失败分支应记录 error，而非 info 成功
        assert log.error.called
