from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from query_run import enable_log_policy_for_run


class PolicyActivationTest(TestCase):
    def test_disabled_policy_starts_current_window_without_deleting_history(self):
        model = MagicMock()
        old = SimpleNamespace(enable=False, last_run_time=datetime(2026, 11, 15, tzinfo=timezone.utc))
        model.objects.filter.return_value.first.return_value = old
        now = datetime(2026, 11, 16, tzinfo=timezone.utc)
        defaults = {"enable": True, "notice": True}
        enable_log_policy_for_run(model, defaults, now)
        model.objects.filter.assert_called_once_with(name="C/D 日志错误验证")
        self.assertEqual(model.objects.update_or_create.call_args.kwargs["defaults"]["last_run_time"], now)
        self.assertNotIn("last_run_time", defaults)
        model.objects.delete.assert_not_called()

    def test_repeating_enable_keeps_active_policy_cursor(self):
        model = MagicMock()
        old = SimpleNamespace(enable=False)
        model.objects.filter.return_value.first.return_value = old
        now = datetime(2026, 11, 16, tzinfo=timezone.utc)
        enable_log_policy_for_run(model, {"enable": True}, now)
        old.enable = True
        enable_log_policy_for_run(model, {"enable": True}, now.replace(hour=1))
        self.assertNotIn("last_run_time", model.objects.update_or_create.call_args.kwargs["defaults"])

    def test_new_policy_uses_current_window(self):
        model = MagicMock()
        model.objects.filter.return_value.first.return_value = None
        now = datetime(2026, 11, 16, tzinfo=timezone.utc)
        enable_log_policy_for_run(model, {"enable": True}, now)
        self.assertEqual(model.objects.update_or_create.call_args.kwargs["defaults"]["last_run_time"], now)
