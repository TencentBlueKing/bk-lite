"""执行记录详情主机要求投影：查询上界与安装语义。"""

import re
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status

from apps.monitor.models import MonitorPlugin  # noqa: F401  INSTALL_APPS 需含 monitor（node_mgmt.urls → collector_release）
from apps.node_mgmt.models import Node  # noqa: F401  详情 URL 加载依赖 node_mgmt
from apps.patch_mgmt.constants import (
    GovernanceTaskType,
    OSType,
    RequirementAssessmentStatus,
)
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    HostComplianceSnapshot,
    Patch,
    PatchBaseline,
    PatchTarget,
)


GOVERNANCE_URL = "/api/v1/patch_mgmt/api/governance/"
_BINDING_TABLE = "patch_host_baseline_binding"
_REQUIREMENT_TABLE = "patch_baseline_requirement"
_SNAPSHOT_TABLE = "patch_host_compliance_snapshot"
_PROJECTION_TABLES = (_BINDING_TABLE, _REQUIREMENT_TABLE, _SNAPSHOT_TABLE)
_PER_ROW_LOOKUP = re.compile(
    r"(?:target_id|baseline_id|binding_id)[\"'`]?\s*=\s*(?:%s|\?|\d+)",
    re.IGNORECASE,
)
_IN_LOOKUP = re.compile(
    r"(?:target_id|baseline_id|binding_id)[\"'`]?\s+IN\s*\(",
    re.IGNORECASE,
)
# 三张表各一次 IN 投影，另留一条偶发 count/exists。
_PROJECTION_QUERY_BOUND = 4


def _payload(response):
    body = response.json() if hasattr(response, "json") else response.data
    if isinstance(body, dict) and "data" in body and isinstance(body["data"], dict):
        return body["data"]
    return body if isinstance(body, dict) else response.data


def _projection_sqls(captured):
    return [
        query["sql"]
        for query in captured.captured_queries
        if any(table in query["sql"] for table in _PROJECTION_TABLES)
    ]


def _per_host_projection_lookups(sqls):
    return [sql for sql in sqls if _PER_ROW_LOOKUP.search(sql) and not _IN_LOOKUP.search(sql)]


def _create_bound_host(*, index, team, baseline, patches, snapshot_offset_minutes=0):
    target = PatchTarget.objects.create(
        name=f"host-{index}",
        ip=f"10.0.{team}.{index}",
        os_type=OSType.LINUX,
        team=[team],
    )
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    evaluated_at = timezone.now() - timedelta(minutes=snapshot_offset_minutes)
    for patch in patches:
        requirement = BaselineRequirement.objects.get(baseline=baseline, patch=patch)
        HostComplianceSnapshot.objects.create(
            binding=binding,
            requirement=requirement,
            satisfied=index % 2 == 0,
            status=(
                RequirementAssessmentStatus.SATISFIED
                if index % 2 == 0
                else RequirementAssessmentStatus.MISSING
            ),
            reason=f"host-{index}-{patch.id}",
            evidence={"host": index, "patch": patch.id},
            evaluated_at=evaluated_at,
        )
    return target


def _create_install_task(targets, patches):
    task = GovernanceTask.objects.create(
        name="install-multi-host",
        task_type=GovernanceTaskType.INSTALL,
        target_list=[target.id for target in targets],
        patch_list=[patch.id for patch in patches],
        team=[1],
    )
    for target in targets:
        GovernanceTaskHost.objects.create(
            task=task,
            target_id=target.id,
            target_name=target.name,
            target_ip=target.ip,
            stage="completed",
        )
    return task


def _scoped_client(api_client, user, mocker, permissions, *, visible_team=1):
    user.is_superuser = False
    user.roles = []
    user.permission = {"patch": set(permissions)}
    api_client.cookies["current_team"] = "1"

    def rules(_user, _team, _app, module, _children):
        if module != "patch_target":
            return {"team": [], "instance": []}
        return {"team": [visible_team], "instance": []}

    mocker.patch("apps.core.utils.viewset_utils.get_permission_rules", side_effect=rules)
    return api_client


@pytest.mark.django_db
def test_install_detail_requirement_queries_stay_bounded_as_hosts_grow(su_client):
    baseline = PatchBaseline.objects.create(name="query-bound", os_type=OSType.LINUX, team=[1])
    selected = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    extra = Patch.objects.create(title="curl", os_type=OSType.LINUX, team=[1])
    BaselineRequirement.objects.create(baseline=baseline, patch=selected, condition="openssl >= 1")
    BaselineRequirement.objects.create(baseline=baseline, patch=extra, condition="curl >= 1")

    small_hosts = [
        _create_bound_host(index=index, team=1, baseline=baseline, patches=[selected, extra])
        for index in range(1, 4)
    ]
    small_task = _create_install_task(small_hosts, [selected])

    with CaptureQueriesContext(connection) as small_captured:
        small_response = su_client.get(f"{GOVERNANCE_URL}{small_task.id}/")

    assert small_response.status_code == status.HTTP_200_OK
    small_data = _payload(small_response)
    assert len(small_data["host_results"]) == 3
    for row in small_data["host_results"]:
        assert [item["patch_id"] for item in row["requirements"]] == [selected.id]

    small_sqls = _projection_sqls(small_captured)
    assert _per_host_projection_lookups(small_sqls) == []
    assert len(small_sqls) <= _PROJECTION_QUERY_BOUND

    large_hosts = small_hosts + [
        _create_bound_host(index=index, team=1, baseline=baseline, patches=[selected, extra])
        for index in range(4, 7)
    ]
    large_task = _create_install_task(large_hosts, [selected])

    with CaptureQueriesContext(connection) as large_captured:
        large_response = su_client.get(f"{GOVERNANCE_URL}{large_task.id}/")

    assert large_response.status_code == status.HTTP_200_OK
    large_data = _payload(large_response)
    assert len(large_data["host_results"]) == 6
    large_sqls = _projection_sqls(large_captured)
    assert _per_host_projection_lookups(large_sqls) == []
    assert len(large_sqls) <= _PROJECTION_QUERY_BOUND
    assert len(large_sqls) <= len(small_sqls)


@pytest.mark.django_db
def test_install_detail_filters_requirements_by_patch_list(su_client):
    baseline = PatchBaseline.objects.create(name="filter-baseline", os_type=OSType.LINUX, team=[1])
    selected = Patch.objects.create(title="keep", os_type=OSType.LINUX, team=[1])
    extra = Patch.objects.create(title="drop", os_type=OSType.LINUX, team=[1])
    BaselineRequirement.objects.create(baseline=baseline, patch=selected, condition="keep >= 1")
    BaselineRequirement.objects.create(baseline=baseline, patch=extra, condition="drop >= 1")
    target = _create_bound_host(index=1, team=1, baseline=baseline, patches=[selected, extra])
    task = _create_install_task([target], [selected])

    response = su_client.get(f"{GOVERNANCE_URL}{task.id}/")

    assert response.status_code == status.HTTP_200_OK
    requirements = _payload(response)["host_results"][0]["requirements"]
    assert [item["patch_id"] for item in requirements] == [selected.id]
    assert requirements[0]["patch_title"] == "keep"
    assert requirements[0]["condition"] == "keep >= 1"


@pytest.mark.django_db
def test_install_detail_uses_latest_snapshot_per_requirement(su_client):
    baseline = PatchBaseline.objects.create(name="latest-snap", os_type=OSType.LINUX, team=[1])
    older_patch = Patch.objects.create(title="older", os_type=OSType.LINUX, team=[1])
    newer_patch = Patch.objects.create(title="newer", os_type=OSType.LINUX, team=[1])
    older_req = BaselineRequirement.objects.create(
        baseline=baseline, patch=older_patch, condition="older >= 1"
    )
    newer_req = BaselineRequirement.objects.create(
        baseline=baseline, patch=newer_patch, condition="newer >= 1"
    )
    target = PatchTarget.objects.create(
        name="host-latest", ip="10.0.1.8", os_type=OSType.LINUX, team=[1]
    )
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    now = timezone.now()
    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=older_req,
        satisfied=False,
        status=RequirementAssessmentStatus.MISSING,
        reason="stale-missing",
        evidence={"gen": 1},
        evaluated_at=now - timedelta(hours=2),
    )
    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=newer_req,
        satisfied=True,
        status=RequirementAssessmentStatus.SATISFIED,
        reason="fresh-ok",
        evidence={"gen": 2},
        evaluated_at=now,
    )
    task = _create_install_task([target], [older_patch, newer_patch])

    response = su_client.get(f"{GOVERNANCE_URL}{task.id}/")

    assert response.status_code == status.HTTP_200_OK
    by_patch = {
        item["patch_id"]: item
        for item in _payload(response)["host_results"][0]["requirements"]
    }

    assert by_patch[older_patch.id]["satisfied"] is False
    assert by_patch[older_patch.id]["status"] == RequirementAssessmentStatus.MISSING
    assert by_patch[older_patch.id]["reason"] == "stale-missing"
    assert by_patch[older_patch.id]["evidence"] == {"gen": 1}
    assert by_patch[newer_patch.id]["satisfied"] is True
    assert by_patch[newer_patch.id]["status"] == RequirementAssessmentStatus.SATISFIED
    assert by_patch[newer_patch.id]["reason"] == "fresh-ok"
    assert by_patch[newer_patch.id]["evidence"] == {"gen": 2}


@pytest.mark.django_db
def test_install_detail_unbound_host_returns_empty_requirements(su_client):
    baseline = PatchBaseline.objects.create(name="bound-only", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    BaselineRequirement.objects.create(baseline=baseline, patch=patch, condition="openssl >= 1")
    bound = _create_bound_host(index=1, team=1, baseline=baseline, patches=[patch])
    unbound = PatchTarget.objects.create(
        name="unbound", ip="10.0.1.9", os_type=OSType.LINUX, team=[1]
    )
    task = _create_install_task([bound, unbound], [patch])

    response = su_client.get(f"{GOVERNANCE_URL}{task.id}/")

    assert response.status_code == status.HTTP_200_OK
    by_target = {row["target_id"]: row["requirements"] for row in _payload(response)["host_results"]}

    assert len(by_target[bound.id]) == 1
    assert by_target[unbound.id] == []


@pytest.mark.django_db
def test_install_detail_hides_invisible_targets_from_host_results(
    api_client, authenticated_user, mocker
):
    baseline = PatchBaseline.objects.create(name="scoped", os_type=OSType.LINUX, team=[1])
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    BaselineRequirement.objects.create(baseline=baseline, patch=patch, condition="openssl >= 1")
    visible = _create_bound_host(index=1, team=1, baseline=baseline, patches=[patch])
    hidden = _create_bound_host(index=2, team=2, baseline=baseline, patches=[patch])
    task = _create_install_task([visible, hidden], [patch])
    client = _scoped_client(
        api_client,
        authenticated_user,
        mocker,
        {"patch_governance-View"},
    )

    response = client.get(f"{GOVERNANCE_URL}{task.id}/")

    assert response.status_code == status.HTTP_200_OK
    data = _payload(response)
    assert [row["target_id"] for row in data["host_results"]] == [visible.id]
    assert data["target_list"] == [visible.id]
    assert all(item["patch_id"] == patch.id for row in data["host_results"] for item in row["requirements"])
    assert all(item["reason"] != f"host-2-{patch.id}" for row in data["host_results"] for item in row["requirements"])
