from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.tasks.monitor_policy import scan_policy_task


def test_scan_policy_task_singleton_lock_expires():
    assert scan_policy_task.raise_on_duplicate is False
    assert scan_policy_task.lock_expiry == AlertConstants.SCAN_POLICY_LOCK_EXPIRY_SECONDS
    assert scan_policy_task.lock_expiry == 3 * 60
    assert scan_policy_task.lock_expiry > AlertConstants.BACKFILL_SOFT_TIME_LIMIT_SECONDS
