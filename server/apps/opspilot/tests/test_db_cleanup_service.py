"""旁路线程 Django 连接清理（Issue #4710）。"""

from unittest.mock import MagicMock, patch

from apps.opspilot.utils.db_cleanup import run_with_db_cleanup, with_db_cleanup, wrap_langchain_tool


class TestRunWithDbCleanup:
    def test_closes_connections_before_and_after_success(self):
        with patch("apps.opspilot.utils.db_cleanup.close_old_connections") as close:
            result = run_with_db_cleanup(lambda: 42)
        assert result == 42
        assert close.call_count == 2

    def test_closes_connections_after_exception(self):
        with patch("apps.opspilot.utils.db_cleanup.close_old_connections") as close:
            try:
                run_with_db_cleanup(lambda: (_ for _ in ()).throw(ValueError("boom")))
            except ValueError:
                pass
        assert close.call_count == 2

    def test_decorator_wraps_function(self):
        @with_db_cleanup
        def add(a, b):
            return a + b

        with patch("apps.opspilot.utils.db_cleanup.close_old_connections") as close:
            assert add(1, 2) == 3
        assert close.call_count == 2

    def test_wrap_langchain_tool_replaces_func(self):
        calls = []

        def original(*, x):
            calls.append(x)
            return {"ok": True}

        tool = MagicMock()
        tool.func = original

        wrap_langchain_tool(tool)

        with patch("apps.opspilot.utils.db_cleanup.close_old_connections") as close:
            assert tool.func(x=1) == {"ok": True}
        assert calls == [1]
        assert close.call_count == 2
        # 幂等：再次包装不叠多层
        first_wrapped = tool.func
        wrap_langchain_tool(tool)
        assert tool.func is first_wrapped
        assert getattr(tool.func, "_db_cleanup_wrapped", False) is True
