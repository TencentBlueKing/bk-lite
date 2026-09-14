"""基线列表/详情合规分布的活动评估查询上界与语义。"""

import re
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status

from apps.node_mgmt.models import Node  # noqa: F401  列表 URL 加载依赖 node_mgmt
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


BASE = "/api/v1/patch_mgmt/api/baseline/"
_TASK_HOST_TABLE = "patch_governance_task_host"
_PER_TARGET_LOOKUP = re.compile(r"target_id[\"'`]?\s*=\s*(?:%s|\?|\d+)", re.IGNORECASE)

# 活动评估相关查询的上界：一次分块 IN（测试规模远小于分块）再加一条偶发 count/exists。
_ASSESSMENT_QUERY_BOUND = 3


def _payload(response):
    body = response.json()
    data = body.get("data", body) if isinstance(body, dict) else body
    if isinstance(data, dict):
        if "results" in data:
            return data["results"]
        if "items" in data:
            return data["items"]
    return data


def _list_item(response, baseline_id):
    rows = _payload(response)
    return next(row for row in rows if row["id"] == baseline_id)


def _counts_by_filter(item):
    return {entry["filter"]: entry["count"] for entry in item["compliance_distribution"]}


def _task_host_queries(captured):
    return [query["sql"] for query in captured.captured_queries if _TASK_HOST_TABLE in query["sql"]]


def _per_target_task_host_lookups(sqls):
    return [
        sql
        for sql in sqls
        if _PER_TARGET_LOOKUP.search(sql) and not re.search(r"target_id[\"'`]?\s+IN\s*\(", sql, re.IGNORECASE)
    ]


def _create_bound_host(baseline, *, index, team, **binding_kwargs):
    target = PatchTarget.objects.create(
        name=f"host-{index}",
        ip=f"10.0.{team}.{index}",
        os_type=OSType.LINUX,
        team=[team],
    )
    HostBaselineBinding.objects.create(target=target, baseline=baseline, **binding_kwargs)
    return target


def _active_assess(target, *, stage, deadline=None):
    task = GovernanceTask.objects.create(
        name=f"assess-{target.id}",
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
        team=list(target.team),
    )
    return GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        stage=stage,
        stage_deadline_at=deadline,
    )


def _scoped_client(api_client, user, mocker, permissions):
    user.is_superuser = False
    user.roles = []
    user.permission = {"patch": set(permissions)}
    api_client.cookies["current_team"] = "1"

    def rules(_user, _team, _app, module, _children):
        if module != "patch_target":
            return {"team": [], "instance": []}
        return {"team": [1], "instance": []}

    mocker.patch("apps.core.utils.viewset_utils.get_permission_rules", side_effect=rules)
    return api_client


@pytest.mark.django_db
def test_baseline_list_assessment_queries_stay_bounded_as_hosts_grow(su_client):
    baseline = PatchBaseline.objects.create(name="query-bound", os_type=OSType.LINUX, team=[1])
    for index in range(1, 9):
        _create_bound_host(baseline, index=index, team=1)

    with CaptureQueriesContext(connection) as eight_hosts:
        eight_response = su_client.get(BASE, {"page_size": -1})

    assert eight_response.status_code == status.HTTP_200_OK
    eight_item = _list_item(eight_response, baseline.id)
    assert _counts_by_filter(eight_item) == {ComplianceStatus.PENDING: 8}

    eight_sqls = _task_host_queries(eight_hosts)
    assert len(_per_target_task_host_lookups(eight_sqls)) == 0
    assert len(eight_sqls) <= _ASSESSMENT_QUERY_BOUND

    for index in range(9, 17):
        _create_bound_host(baseline, index=index, team=1)

    with CaptureQueriesContext(connection) as sixteen_hosts:
        sixteen_response = su_client.get(BASE, {"page_size": -1})

    assert sixteen_response.status_code == status.HTTP_200_OK
    sixteen_item = _list_item(sixteen_response, baseline.id)
    assert _counts_by_filter(sixteen_item) == {ComplianceStatus.PENDING: 16}

    sixteen_sqls = _task_host_queries(sixteen_hosts)
    assert len(_per_target_task_host_lookups(sixteen_sqls)) == 0
    assert len(sixteen_sqls) <= _ASSESSMENT_QUERY_BOUND
    assert len(sixteen_sqls) <= len(eight_sqls)


@pytest.mark.django_db
def test_baseline_list_and_detail_project_timeout_evaluating_and_pending_fallback(su_client):
    baseline = PatchBaseline.objects.create(name="mixed-status", os_type=OSType.LINUX, team=[1])
    _create_bound_host(baseline, index=1, team=1)
    evaluating = _create_bound_host(
        baseline,
        index=2,
        team=1,
        compliance_status=ComplianceStatus.COMPLIANT,
        last_evaluated_at=timezone.now(),
    )
    timed_out = _create_bound_host(
        baseline,
        index=3,
        team=1,
        compliance_status=ComplianceStatus.COMPLIANT,
        last_evaluated_at=timezone.now(),
    )
    fallback = _create_bound_host(
        baseline,
        index=4,
        team=1,
        compliance_status=ComplianceStatus.PENDING,
        last_evaluated_at=timezone.now(),
    )
    _active_assess(evaluating, stage="scanning")
    _active_assess(timed_out, stage="scanning", deadline=timezone.now() - timedelta(seconds=1))

    list_response = su_client.get(BASE, {"page_size": -1})
    detail_response = su_client.get(f"{BASE}{baseline.id}/")

    assert list_response.status_code == status.HTTP_200_OK
    assert detail_response.status_code == status.HTTP_200_OK
    expected = {
        ComplianceStatus.PENDING: 1,
        ComplianceStatus.EVALUATING: 1,
        ComplianceStatus.FAILED: 1,
        ComplianceStatus.COMPLIANT: 1,
    }
    assert _counts_by_filter(_list_item(list_response, baseline.id)) == expected
    detail = _payload(detail_response)
    if isinstance(detail, list):
        detail = next(row for row in detail if row["id"] == baseline.id)
    assert _counts_by_filter(detail) == expected
    assert fallback.baseline_binding.compliance_status == ComplianceStatus.PENDING


@pytest.mark.django_db
def test_baseline_compliance_distribution_omits_invisible_bindings(
    api_client, authenticated_user, mocker
):
    baseline = PatchBaseline.objects.create(name="scoped", os_type=OSType.LINUX, team=[2])
    _create_bound_host(
        baseline,
        index=1,
        team=1,
        compliance_status=ComplianceStatus.PENDING,
    )
    _create_bound_host(
        baseline,
        index=2,
        team=2,
        compliance_status=ComplianceStatus.UNKNOWN,
        last_evaluated_at=timezone.now(),
    )
    client = _scoped_client(
        api_client,
        authenticated_user,
        mocker,
        {"patch_baseline-View"},
    )

    response = client.get(BASE, {"page_size": -1})

    assert response.status_code == status.HTTP_200_OK
    assert _counts_by_filter(_list_item(response, baseline.id)) == {ComplianceStatus.PENDING: 1}
