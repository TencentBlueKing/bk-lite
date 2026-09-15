"""目标列表合规状态筛选：批量投影与权限裁剪顺序。"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status

from apps.node_mgmt.models import CloudRegion  # noqa: F401  # INSTALL_APPS 需含 node_mgmt
from apps.patch_mgmt.constants import (
    ComplianceStatus,
    GovernanceTaskStatus,
    GovernanceTaskType,
    OSType,
)
from apps.patch_mgmt.models import (
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    PatchBaseline,
    PatchTarget,
)

TARGET_URL = "/api/v1/patch_mgmt/api/patch_target/"
VISIBLE_BOUND_COUNT = 8
GROWN_BOUND_COUNT = 16
PAGE_SIZE = 10
# 筛选一次批量投影；当前页序列化仍可能按条查询合规投影与活动任务。上界随 page_size，不随绑定主机数 B。
ASSESSMENT_QUERY_BUDGET = PAGE_SIZE * 2 + 4
ASSESSMENT_QUERY_GROWTH_BUDGET = 2


def _non_superuser_client(api_client, authenticated_user, mocker):
    authenticated_user.is_superuser = False
    authenticated_user.roles = []
    authenticated_user.permission = {"patch": {"patch_target-View"}}
    api_client.cookies["current_team"] = "1"
    mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    return api_client


def _baseline():
    return PatchBaseline.objects.create(name="compliance-filter", os_type=OSType.LINUX, team=[1])


def _target(name, ip, team):
    return PatchTarget.objects.create(name=name, ip=ip, os_type=OSType.LINUX, team=team)


def _bind(target, baseline, *, compliance_status, last_evaluated_at=None):
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    binding.compliance_status = compliance_status
    binding.last_evaluated_at = last_evaluated_at
    binding.save(update_fields=["compliance_status", "last_evaluated_at", "updated_at"])
    return binding


def _active_assess(target, *, stage, deadline):
    task = GovernanceTask.objects.create(
        name=f"assess-{target.name}",
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
        team=list(target.team),
    )
    return GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage=stage,
        stage_deadline_at=deadline,
    )


def _compliant_targets(baseline, count, *, team, ip_prefix, name_prefix):
    now = timezone.now()
    targets = []
    for index in range(count):
        target = _target(f"{name_prefix}-{index}", f"{ip_prefix}.{index + 1}", team)
        _bind(
            target,
            baseline,
            compliance_status=ComplianceStatus.COMPLIANT,
            last_evaluated_at=now,
        )
        targets.append(target)
    return targets


def _assessment_query_count(captured) -> int:
    return sum(
        1
        for query in captured.captured_queries
        if "patch_governance_task_host" in query["sql"].lower()
    )


def _item_names(response):
    payload = response.data
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    return [item["name"] for item in items]


def _seed_semantic_targets(baseline):
    now = timezone.now()
    unconfigured = _target("unconfigured-host", "10.8.0.1", [1])

    pending = _target("pending-host", "10.8.0.2", [1])
    _bind(pending, baseline, compliance_status=ComplianceStatus.PENDING)

    evaluating = _target("evaluating-host", "10.8.0.3", [1])
    _bind(
        evaluating,
        baseline,
        compliance_status=ComplianceStatus.COMPLIANT,
        last_evaluated_at=now,
    )
    _active_assess(
        evaluating,
        stage="scanning",
        deadline=now + timedelta(hours=1),
    )

    failed = _target("failed-host", "10.8.0.4", [1])
    _bind(
        failed,
        baseline,
        compliance_status=ComplianceStatus.COMPLIANT,
        last_evaluated_at=now,
    )
    _active_assess(
        failed,
        stage="scanning",
        deadline=now - timedelta(seconds=1),
    )

    named_compliant = _target("compliant-host", "10.8.0.5", [1])
    _bind(
        named_compliant,
        baseline,
        compliance_status=ComplianceStatus.COMPLIANT,
        last_evaluated_at=now,
    )
    return {
        ComplianceStatus.UNCONFIGURED: unconfigured,
        ComplianceStatus.PENDING: pending,
        ComplianceStatus.EVALUATING: evaluating,
        ComplianceStatus.FAILED: failed,
        ComplianceStatus.COMPLIANT: named_compliant,
    }


@pytest.mark.django_db
def test_compliance_filter_query_count_does_not_scale_with_bound_hosts(
    api_client, authenticated_user, mocker
):
    client = _non_superuser_client(api_client, authenticated_user, mocker)
    baseline = _baseline()
    visible = _compliant_targets(
        baseline,
        VISIBLE_BOUND_COUNT,
        team=[1],
        ip_prefix="10.1.0",
        name_prefix="visible-compliant",
    )
    _seed_semantic_targets(baseline)
    hidden = _compliant_targets(
        baseline,
        VISIBLE_BOUND_COUNT,
        team=[99],
        ip_prefix="10.99.0",
        name_prefix="hidden-compliant",
    )
    for target in hidden:
        _active_assess(
            target,
            stage="scanning",
            deadline=timezone.now() + timedelta(hours=1),
        )

    with CaptureQueriesContext(connection) as captured:
        response = client.get(
            TARGET_URL,
            {"compliance_status": ComplianceStatus.COMPLIANT, "page_size": PAGE_SIZE},
        )

    assert response.status_code == status.HTTP_200_OK
    names = set(_item_names(response))
    assert {target.name for target in visible} <= names
    assert "compliant-host" in names
    assert not names.intersection({target.name for target in hidden})
    base_count = _assessment_query_count(captured)
    assert base_count <= ASSESSMENT_QUERY_BUDGET

    extra_count = GROWN_BOUND_COUNT - VISIBLE_BOUND_COUNT
    for index in range(extra_count):
        extra = _target(f"visible-pending-extra-{index}", f"10.2.0.{index + 1}", [1])
        _bind(extra, baseline, compliance_status=ComplianceStatus.PENDING)

    with CaptureQueriesContext(connection) as grown:
        grown_response = client.get(
            TARGET_URL,
            {"compliance_status": ComplianceStatus.COMPLIANT, "page_size": PAGE_SIZE},
        )

    assert grown_response.status_code == status.HTTP_200_OK
    grown_names = set(_item_names(grown_response))
    assert grown_names == names
    grown_count = _assessment_query_count(grown)
    assert grown_count - base_count <= ASSESSMENT_QUERY_GROWTH_BUDGET


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status_value", "expected_name"),
    [
        (ComplianceStatus.UNCONFIGURED, "unconfigured-host"),
        (ComplianceStatus.PENDING, "pending-host"),
        (ComplianceStatus.EVALUATING, "evaluating-host"),
        (ComplianceStatus.FAILED, "failed-host"),
        (ComplianceStatus.COMPLIANT, "compliant-host"),
    ],
)
def test_compliance_filter_projection_semantics(
    api_client, authenticated_user, mocker, status_value, expected_name
):
    client = _non_superuser_client(api_client, authenticated_user, mocker)
    baseline = _baseline()
    _seed_semantic_targets(baseline)
    _compliant_targets(
        baseline,
        1,
        team=[99],
        ip_prefix="10.99.8",
        name_prefix="hidden-other-team",
    )

    response = client.get(
        TARGET_URL,
        {"compliance_status": status_value, "page_size": 10},
    )

    assert response.status_code == status.HTTP_200_OK
    names = _item_names(response)
    assert expected_name in names
    assert "hidden-other-team-0" not in names
    unexpected = {
        ComplianceStatus.UNCONFIGURED: "unconfigured-host",
        ComplianceStatus.PENDING: "pending-host",
        ComplianceStatus.EVALUATING: "evaluating-host",
        ComplianceStatus.FAILED: "failed-host",
        ComplianceStatus.COMPLIANT: "compliant-host",
    }
    unexpected.pop(status_value)
    assert not set(names).intersection(unexpected.values())
