import pydantic.root_model  # noqa

"""apps/core/management/commands/batch_init.py 的真实行为测试。

被测对象是初始化编排命令 Command。它的核心逻辑是“按 app 分发到对应的
call_command 序列 + 错误处理策略（默认失败即中断，启用 continue_on_error
后继续执行并汇总失败）”。
"""

from types import SimpleNamespace

import pytest

import apps.core.management.commands.batch_init as bi

pytestmark = pytest.mark.unit


class _Style:
    SUCCESS = staticmethod(lambda m: m)
    WARNING = staticmethod(lambda m: f"WARN:{m}")
    ERROR = staticmethod(lambda m: f"ERR:{m}")


def _make_command():
    cmd = bi.Command()
    cmd.stdout = SimpleNamespace(messages=[], write=lambda m: cmd.stdout.messages.append(m))
    cmd.style = _Style()
    return cmd


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    def fake_call_command(name, *args, **kwargs):
        recorded.append((name, args, kwargs))

    monkeypatch.setattr(bi, "call_command", fake_call_command)
    monkeypatch.setattr(
        bi,
        "preload_language_cache",
        lambda *a, **k: {"loaded": [1], "skipped": [], "failed": []},
    )
    return recorded


class TestHandleDispatch:
    def test_single_known_app_runs_its_command_sequence(self, calls):
        cmd = _make_command()
        cmd.handle(apps="node_mgmt", continue_on_error=False)
        names = [c[0] for c in calls]
        assert names == ["node_init"]

    def test_monitor_app_initializes_plugins_and_metrics_stream(self, calls):
        cmd = _make_command()
        cmd.handle(apps="monitor", continue_on_error=False)
        assert [c[0] for c in calls] == [
            "plugin_init",
            "ensure_monitor_metrics_stream",
        ]

    def test_multiple_apps_dispatched_in_order(self, calls):
        cmd = _make_command()
        cmd.handle(apps="log,mlops", continue_on_error=False)
        assert [c[0] for c in calls] == ["log_init", "init_algorithm_config"]

    def test_console_mgmt_dispatches_to_noop_init(self, calls):
        cmd = _make_command()
        cmd.handle(apps="console_mgmt", continue_on_error=False)
        assert calls == []
        assert any("控制台管理资源初始化" in m for m in cmd.stdout.messages)
        assert not any("未知模块" in m for m in cmd.stdout.messages)

    def test_unknown_app_emits_warning_and_no_command(self, calls):
        cmd = _make_command()
        cmd.handle(apps="does_not_exist", continue_on_error=False)
        assert calls == []
        assert any("WARN:" in m and "未知模块" in m for m in cmd.stdout.messages)

    def test_empty_apps_uses_full_default_list(self, calls):
        cmd = _make_command()
        cmd.handle(apps="", continue_on_error=False)
        names = [c[0] for c in calls]
        assert "init_realm_resource" in names
        assert "model_init" in names
        assert "plugin_init" in names
        assert "node_init" in names
        assert "log_init" in names

    def test_system_mgmt_creates_admin_with_resolved_password(self, calls, monkeypatch):
        monkeypatch.delenv("BK_INIT_ADMIN_PASSWORD", raising=False)
        cmd = _make_command()
        cmd.handle(apps="system_mgmt", continue_on_error=False)
        create_user = [c for c in calls if c[0] == "create_user"]
        assert len(create_user) == 1
        _, args, kwargs = create_user[0]
        assert args == ("admin", "password")
        assert kwargs.get("is_superuser") is True

    def test_system_mgmt_runs_opspilot_legacy_menu_cleanup_before_realm_resource(self, calls):
        cmd = _make_command()
        cmd.handle(apps="system_mgmt", continue_on_error=False)
        names = [c[0] for c in calls]
        assert names.index("cleanup_opspilot_legacy_knowledge_menus") < names.index("init_realm_resource")


class TestErrorHandlingPolicy:
    def test_system_mgmt_failure_reraises_and_aborts(self, monkeypatch):
        calls = []

        def fake_call_command(name, *args, **kwargs):
            calls.append(name)
            if name == "init_realm_resource":
                raise RuntimeError("sysmgmt boom")

        monkeypatch.setattr(bi, "call_command", fake_call_command)
        monkeypatch.setattr(bi, "preload_language_cache", lambda *a, **k: {"loaded": [], "skipped": [], "failed": []})
        cmd = _make_command()
        with pytest.raises(RuntimeError, match="sysmgmt boom"):
            cmd.handle(apps="system_mgmt,cmdb", continue_on_error=False)
        assert "model_init" not in calls

    def test_non_system_app_failure_raises_by_default_and_aborts(self, monkeypatch):
        calls = []

        def fake_call_command(name, *args, **kwargs):
            calls.append(name)
            if name == "plugin_init":
                raise RuntimeError("monitor boom")

        monkeypatch.setattr(bi, "call_command", fake_call_command)
        monkeypatch.setattr(bi, "preload_language_cache", lambda *a, **k: {"loaded": [], "skipped": [], "failed": []})
        cmd = _make_command()
        with pytest.raises(RuntimeError, match="monitor boom"):
            cmd.handle(apps="monitor,log", continue_on_error=False)
        assert "log_init" not in calls
        assert any("ERR:" in m and "monitor" in m for m in cmd.stdout.messages)

    def test_metrics_stream_failure_aborts_monitor_initialization(self, monkeypatch):
        calls = []

        def fake_call_command(name, *args, **kwargs):
            calls.append(name)
            if name == "ensure_monitor_metrics_stream":
                raise RuntimeError("JetStream unavailable")

        monkeypatch.setattr(bi, "call_command", fake_call_command)
        monkeypatch.setattr(bi, "preload_language_cache", lambda *a, **k: {"loaded": [], "skipped": [], "failed": []})
        cmd = _make_command()

        with pytest.raises(RuntimeError, match="JetStream unavailable"):
            cmd.handle(apps="monitor,log", continue_on_error=False)

        assert calls == ["plugin_init", "ensure_monitor_metrics_stream"]
        assert any("ERR:" in m and "初始化 monitor 失败: JetStream unavailable" in m for m in cmd.stdout.messages)

    def test_continue_on_error_runs_remaining_apps_and_reports_failures(self, monkeypatch):
        calls = []

        def fake_call_command(name, *args, **kwargs):
            calls.append((name, args, kwargs))
            if name == "plugin_init":
                raise RuntimeError("plugin init failed")

        monkeypatch.setattr(bi, "call_command", fake_call_command)
        monkeypatch.setattr(bi, "preload_language_cache", lambda *a, **k: {"loaded": [], "skipped": [], "failed": []})
        cmd = _make_command()

        cmd.handle(apps="monitor,node_mgmt", continue_on_error=True)

        assert calls == [("plugin_init", (), {}), ("node_init", (), {})]
        assert any("ERR:" in m and "初始化 monitor 失败: plugin init failed" in m for m in cmd.stdout.messages)
        assert any("WARN:" in m and "批量初始化完成，失败模块: monitor: plugin init failed" in m for m in cmd.stdout.messages)


class TestGetAdminPassword:
    def test_env_password_used_when_set(self, monkeypatch):
        monkeypatch.setenv("BK_INIT_ADMIN_PASSWORD", "  s3cret  ")
        assert bi.Command._get_admin_password() == "s3cret"

    def test_blank_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BK_INIT_ADMIN_PASSWORD", "   ")
        assert bi.Command._get_admin_password() == "password"

    def test_missing_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.delenv("BK_INIT_ADMIN_PASSWORD", raising=False)
        assert bi.Command._get_admin_password() == "password"


class TestPreloadLanguageCache:
    def test_preload_failure_is_swallowed_with_warning(self, monkeypatch):
        monkeypatch.setattr(bi, "call_command", lambda *a, **k: None)

        def boom(*a, **k):
            raise RuntimeError("preload boom")

        monkeypatch.setattr(bi, "preload_language_cache", boom)
        cmd = _make_command()
        cmd.handle(apps="node_mgmt", continue_on_error=False)
        assert any("WARN:" in m and "语言缓存预热失败" in m for m in cmd.stdout.messages)

    def test_add_arguments_registers_apps_option(self):
        import argparse

        parser = argparse.ArgumentParser()
        bi.Command().add_arguments(parser)
        ns = parser.parse_args(["--apps", "cmdb,log"])
        assert ns.apps == "cmdb,log"

    def test_add_arguments_registers_continue_on_error_option(self):
        import argparse

        parser = argparse.ArgumentParser()
        bi.Command().add_arguments(parser)
        ns = parser.parse_args(["--continue-on-error"])
        assert ns.continue_on_error is True
