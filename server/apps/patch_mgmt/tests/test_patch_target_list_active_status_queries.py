"""目标列表活动治理状态：批量投影，查询不随页内目标数线性增长。"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status

from apps.monitor.models import MonitorPlugin  # noqa: F401  INSTALL_APPS 需含 monitor（node_mgmt.urls → collector_release）
from apps.node_mgmt.models import Node  # noqa: F401  列表 URL 加载依赖 node_mgmt
from apps.patch_mgmt.constants import (
    ComplianceStatus,
    GovernanceTaskStatus,
    GovernanceTaskType,
    OSType,
)
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    Patch,
    PatchBaseline,
    PatchTarget,
)

TARGET_URL = "/api/v1/patch_mgmt/api/patch_target/"
SMALL_BOUND_COUNT = 8
GROWN_BOUND_COUNT = 16
PAGE_SIZE = 100
HOST_QUERY_GROWTH_BUDGET = 2
REQUIREMENT_TABLE = "patch_baseline_requirement"


def _view_client(api_client, authenticated_user, mocker):
    authenticated_user.is_superuser = False
    authenticated_user.roles = []
    authenticated_user.permission = {"patch": {"patch_target-View"}}
    api_client.cookies["current_team"] = "1"
    mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    return api_client


def _list_items(response):
    payload = response.data
    if isinstance(payload, dict) and "items" in payload:
        return payload["items"]
    return list(payload)


def _host_query_count(captured) -> int:
    return sum(
        1
        for query in captured.captured_queries
        if "patch_governance_task_host" in query["sql"].lower()
    )


def _per_row_requirement_counts(queries):
    """RelatedManager.count() 产生的逐行 COUNT，不含批量 GROUP BY。"""
    matched = []
    for query in queries:
        normalized = " ".join(query["sql"].lower().split())
        if REQUIREMENT_TABLE not in normalized or "count(" not in normalized:
            continue
        if "where" in normalized and "baseline_id" in normalized and "group by" not in normalized:
            matched.append(query["sql"])
    return matched


def _baseline_with_requirements():
    baseline = PatchBaseline.objects.create(
        name="list-active-status",
        os_type=OSType.LINUX,
        team=[1],
    )
    for index in range(2):
        patch = Patch.objects.create(
            title=f"req-patch-{index}",
            os_type=OSType.LINUX,
            team=[1],
        )
        BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    return baseline


def _bound_target(name, ip, baseline, *, missing_count=0, compliance_status=None, last_evaluated_at=None):
    target = PatchTarget.objects.create(name=name, ip=ip, os_type=OSType.LINUX, team=[1])
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    update_fields = ["updated_at"]
    if missing_count is not None:
        binding.missing_count = missing_count
        update_fields.append("missing_count")
    if compliance_status is not None:
        binding.compliance_status = compliance_status
        update_fields.append("compliance_status")
    if last_evaluated_at is not None:
        binding.last_evaluated_at = last_evaluated_at
        update_fields.append("last_evaluated_at")
    binding.save(update_fields=update_fields)
    return target


def _active_assess(target, *, stage, deadline=None, created_at=None, reason=""):
    task = GovernanceTask.objects.create(
        name=f"assess-{target.name}",
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
        team=list(target.team),
    )
    host = GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage=stage,
        stage_deadline_at=deadline,
        reason=reason,
    )
    if created_at is not None:
        GovernanceTaskHost.objects.filter(pk=host.pk).update(created_at=created_at)
        host.refresh_from_db()
    return host


def _seed_bound_active_hosts(baseline, count, *, ip_prefix, name_prefix):
    now = timezone.now()
    targets = []
    for index in range(count):
        target = _bound_target(
            f"{name_prefix}-{index}",
            f"{ip_prefix}.{index + 1}",
            baseline,
            missing_count=1,
            compliance_status=ComplianceStatus.COMPLIANT,
            last_evaluated_at=now,
        )
        _active_assess(target, stage="scanning", deadline=now + timedelta(hours=1))
        targets.append(target)
    return targets


@pytest.mark.django_db
def test_patch_target_list_host_queries_do_not_scale_with_bound_hosts(
    api_client, authenticated_user, mocker
):
    client = _view_client(api_client, authenticated_user, mocker)
    baseline = _baseline_with_requirements()
    _seed_bound_active_hosts(
        baseline,
        SMALL_BOUND_COUNT,
        ip_prefix="10.1.0",
        name_prefix="bound-active",
    )

    with CaptureQueriesContext(connection) as small_ctx:
        small_response = client.get(TARGET_URL, {"page_size": PAGE_SIZE})

    assert small_response.status_code == status.HTTP_200_OK
    small_items = _list_items(small_response)
    assert len(small_items) == SMALL_BOUND_COUNT
    by_name = {item["name"]: item for item in small_items}
    for index in range(SMALL_BOUND_COUNT):
        item = by_name[f"bound-active-{index}"]
        assert item["has_active_task"] is True
        assert item["compliance_status"] == ComplianceStatus.EVALUATING
        assert item["missing_count"] == 1
    small_host_queries = _host_query_count(small_ctx)
    small_row_counts = _per_row_requirement_counts(small_ctx.captured_queries)
    assert len(small_row_counts) == 0

    extra = GROWN_BOUND_COUNT - SMALL_BOUND_COUNT
    _seed_bound_active_hosts(
        baseline,
        extra,
        ip_prefix="10.2.0",
        name_prefix="bound-active-extra",
    )

    with CaptureQueriesContext(connection) as large_ctx:
        large_response = client.get(TARGET_URL, {"page_size": PAGE_SIZE})

    assert large_response.status_code == status.HTTP_200_OK
    large_items = _list_items(large_response)
    assert len(large_items) == GROWN_BOUND_COUNT
    large_by_name = {item["name"]: item for item in large_items}
    for item in large_items:
        assert item["has_active_task"] is True
        assert item["compliance_status"] == ComplianceStatus.EVALUATING
        assert item["missing_count"] == 1
    assert f"bound-active-extra-{extra - 1}" in large_by_name
    large_host_queries = _host_query_count(large_ctx)
    large_row_counts = _per_row_requirement_counts(large_ctx.captured_queries)
    assert len(large_row_counts) == 0
    assert large_host_queries - small_host_queries <= HOST_QUERY_GROWTH_BUDGET


@pytest.mark.django_db
def test_patch_target_list_preserves_active_status_and_missing_count_semantics(
    api_client, authenticated_user, mocker
):
    client = _view_client(api_client, authenticated_user, mocker)
    baseline = _baseline_with_requirements()
    now = timezone.now()

    unconfigured = PatchTarget.objects.create(
        name="unconfigured-host",
        ip="10.8.0.1",
        os_type=OSType.LINUX,
        team=[1],
    )

    pending = _bound_target(
        "pending-host",
        "10.8.0.2",
        baseline,
        missing_count=0,
        compliance_status=ComplianceStatus.PENDING,
    )

    evaluating = _bound_target(
        "evaluating-host",
        "10.8.0.3",
        baseline,
        missing_count=0,
        compliance_status=ComplianceStatus.COMPLIANT,
        last_evaluated_at=now,
    )
    _active_assess(evaluating, stage="scanning", deadline=now + timedelta(hours=1))

    failed = _bound_target(
        "failed-host",
        "10.8.0.4",
        baseline,
        missing_count=0,
        compliance_status=ComplianceStatus.COMPLIANT,
        last_evaluated_at=now,
    )
    _active_assess(failed, stage="scanning", deadline=now - timedelta(seconds=1))

    compliant_zero = _bound_target(
        "compliant-zero-missing",
        "10.8.0.5",
        baseline,
        missing_count=0,
        compliance_status=ComplianceStatus.COMPLIANT,
        last_evaluated_at=now,
    )

    missing_three = _bound_target(
        "noncompliant-three-missing",
        "10.8.0.6",
        baseline,
        missing_count=3,
        compliance_status=ComplianceStatus.NON_COMPLIANT,
        last_evaluated_at=now,
    )

    stale_waiting = _bound_target(
        "stale-waiting-host",
        "10.8.0.7",
        baseline,
        missing_count=0,
        compliance_status=ComplianceStatus.COMPLIANT,
        last_evaluated_at=now,
    )
    _active_assess(
        stale_waiting,
        stage="waiting",
        created_at=now - timedelta(minutes=6),
    )

    persisted_failed = _bound_target(
        "persisted-failed-host",
        "10.8.0.8",
        baseline,
        missing_count=1,
        compliance_status=ComplianceStatus.FAILED,
        last_evaluated_at=now,
    )
    _active_assess(
        persisted_failed,
        stage="failed",
        reason="Assessment exploded",
    )
    GovernanceTask.objects.filter(name=f"assess-{persisted_failed.name}").update(
        status=GovernanceTaskStatus.FAILED,
    )

    with CaptureQueriesContext(connection) as captured:
        response = client.get(TARGET_URL, {"page_size": PAGE_SIZE})
    assert response.status_code == status.HTTP_200_OK
    by_name = {item["name"]: item for item in _list_items(response)}
    assert _per_row_requirement_counts(captured.captured_queries) == []

    assert by_name[unconfigured.name]["compliance_status"] == ComplianceStatus.UNCONFIGURED
    assert by_name[unconfigured.name]["has_active_task"] is False
    assert by_name[unconfigured.name]["missing_count"] == 0

    assert by_name[pending.name]["compliance_status"] == ComplianceStatus.PENDING
    assert by_name[pending.name]["has_active_task"] is False
    assert by_name[pending.name]["missing_count"] == 0

    assert by_name[evaluating.name]["compliance_status"] == ComplianceStatus.EVALUATING
    assert by_name[evaluating.name]["has_active_task"] is True
    assert by_name[evaluating.name]["missing_count"] == 0

    assert by_name[failed.name]["compliance_status"] == ComplianceStatus.FAILED
    assert by_name[failed.name]["has_active_task"] is False

    assert by_name[compliant_zero.name]["compliance_status"] == ComplianceStatus.COMPLIANT
    assert by_name[compliant_zero.name]["has_active_task"] is False
    assert by_name[compliant_zero.name]["missing_count"] == 0

    assert by_name[missing_three.name]["compliance_status"] == ComplianceStatus.NON_COMPLIANT
    assert by_name[missing_three.name]["missing_count"] == 3

    assert by_name[stale_waiting.name]["has_active_task"] is False
    assert by_name[stale_waiting.name]["compliance_status"] == ComplianceStatus.FAILED

    assert by_name[persisted_failed.name]["compliance_status"] == ComplianceStatus.FAILED
    assert by_name[persisted_failed.name]["compliance_failure_reason"] == "Assessment exploded"
    assert by_name[persisted_failed.name]["has_active_task"] is False
    assert by_name[persisted_failed.name]["missing_count"] == 1

    retrieve = client.get(f"{TARGET_URL}{evaluating.id}/")
    assert retrieve.status_code == status.HTTP_200_OK
    assert retrieve.data["has_active_task"] is True
    assert retrieve.data["compliance_status"] == ComplianceStatus.EVALUATING
    assert retrieve.data["missing_count"] == 0
