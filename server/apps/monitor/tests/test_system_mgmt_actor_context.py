"""Issue #3334：system_mgmt 视图的「当前操作人」上下文此前缺 group_list，与 monitor_instance/
node_mgmt 两处不一致——而用户面 scoped 查询（get_group_users_scoped / search_channel_list_scoped）
依赖 group_list 做组织范围判断。本测验证 system_mgmt 的 _build_actor_context 现包含 group_list。

沿用注入式 harness（pytest 因缺 license_mgmt/MINIO 无法 django.setup）。
"""
import importlib.util
import sys
import types
from pathlib import Path


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_system_mgmt_view(monkeypatch):
    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    _install_module(monkeypatch, "rest_framework.viewsets", ViewSet=ViewSet)
    _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install_module(monkeypatch, "apps.core.utils.web_utils", WebUtils=types.SimpleNamespace(response_success=lambda data=None: data))
    _install_module(
        monkeypatch,
        "apps.core.utils.user_group",
        normalize_user_group_ids=lambda groups: [
            int(group.get("id") if isinstance(group, dict) else group)
            for group in groups
            if (group.get("id") if isinstance(group, dict) else group) is not None
        ],
    )
    _install_module(monkeypatch, "apps.monitor.utils.system_mgmt_api", SystemMgmtUtils=object)

    spec = importlib.util.spec_from_file_location(
        "monitor_system_mgmt_view_test_module",
        Path(__file__).resolve().parents[1] / "views" / "system_mgmt.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _request(group_list, current_team="7"):
    return types.SimpleNamespace(
        COOKIES={"current_team": current_team, "include_children": "1"},
        user=types.SimpleNamespace(username="u", domain="domain.com", is_superuser=False, group_list=group_list),
    )


def test_actor_context_includes_group_list_for_integer_groups(monkeypatch):
    module = _load_system_mgmt_view(monkeypatch)
    ctx = module._build_actor_context(_request([7, 9]))
    # 此前缺失，现与 monitor_instance/node_mgmt 一致填充 group_list
    assert ctx["group_list"] == [7, 9]
    # 其余字段不变
    assert ctx["current_team"] == 7
    assert ctx["username"] == "u"
    assert ctx["is_superuser"] is False


def test_actor_context_normalizes_token_group_dicts(monkeypatch):
    module = _load_system_mgmt_view(monkeypatch)
    ctx = module._build_actor_context(_request([{"id": "8", "name": "team-a"}]))
    assert ctx["group_list"] == [8]


def test_actor_context_defaults_group_list_when_user_has_none(monkeypatch):
    module = _load_system_mgmt_view(monkeypatch)
    request = types.SimpleNamespace(
        COOKIES={"current_team": "7"},
        user=types.SimpleNamespace(username="u", domain="domain.com", is_superuser=False),  # 无 group_list 属性
    )
    ctx = module._build_actor_context(request)
    assert ctx["group_list"] == []
