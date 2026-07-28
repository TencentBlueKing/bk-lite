from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.monitor.models import MonitorInstance, MonitorObject
from apps.monitor.services.auto_discovery_lifecycle import AutoDiscoveryLifecycleService
from apps.monitor.services.monitor_object_cleanup import MonitorObjectCleanupPolicyService

pytestmark = pytest.mark.django_db


def test_configure_resets_base_and_child_auto_instances_only():
    base = MonitorObject.objects.create(name="CleanupBase", level="base")
    child = MonitorObject.objects.create(name="CleanupChild", level="derivative", parent=base)
    auto_base = MonitorInstance.objects.create(
        id="auto-base", monitor_object=base, auto=True, missing_duration_seconds=3600
    )
    auto_child = MonitorInstance.objects.create(
        id="auto-child", monitor_object=child, auto=True, missing_duration_seconds=3600
    )
    manual = MonitorInstance.objects.create(
        id="manual", monitor_object=base, auto=False, missing_duration_seconds=3600
    )

    MonitorObjectCleanupPolicyService.configure(
        base, policy=MonitorObject.CLEANUP_POLICY_TIMEOUT, timeout_days=7
    )

    base.refresh_from_db()
    auto_base.refresh_from_db()
    auto_child.refresh_from_db()
    manual.refresh_from_db()
    assert base.cleanup_policy == MonitorObject.CLEANUP_POLICY_TIMEOUT
    assert base.cleanup_timeout_days == 7
    assert base.cleanup_policy_effective_at is not None
    assert auto_base.missing_duration_seconds == 0
    assert auto_child.missing_duration_seconds == 0
    assert manual.missing_duration_seconds == 3600


def test_derivative_object_cannot_configure_cleanup_policy():
    base = MonitorObject.objects.create(name="CleanupParent", level="base")
    child = MonitorObject.objects.create(name="CleanupDerivative", level="derivative", parent=base)

    with pytest.raises(ValidationAppException, match="一级监控对象"):
        MonitorObjectCleanupPolicyService.configure(
            child, policy=MonitorObject.CLEANUP_POLICY_TIMEOUT, timeout_days=1
        )


def test_child_inherits_parent_policy_and_policy_change_starts_fresh_interval():
    observed_at = timezone.now()
    base = MonitorObject.objects.create(
        name="CleanupInheritedBase",
        level="base",
        cleanup_policy=MonitorObject.CLEANUP_POLICY_TIMEOUT,
        cleanup_timeout_days=1,
        cleanup_policy_effective_at=observed_at - timedelta(minutes=5),
    )
    child = MonitorObject.objects.create(
        name="CleanupInheritedChild",
        level="derivative",
        parent=base,
        last_discovery_success_at=observed_at - timedelta(minutes=10),
    )
    instance = MonitorInstance.objects.create(
        id="inherited-child",
        monitor_object=child,
        auto=True,
        missing_duration_seconds=24 * 60 * 60 - 301,
    )

    AutoDiscoveryLifecycleService.reconcile({}, {child.id}, observed_at)

    instance.refresh_from_db()
    assert instance.is_active is False
    assert instance.missing_duration_seconds == 24 * 60 * 60 - 1
