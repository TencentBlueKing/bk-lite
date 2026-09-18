"""风险计算按授权主机收口后，治理任务查询不得随隐藏租户线性增长。"""

import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.monitor.models import MonitorPlugin  # noqa: F401  INSTALL_APPS 需含 monitor
from apps.node_mgmt.models import Node  # noqa: F401  包装器缺 node_mgmt 时补齐导入
from apps.patch_mgmt.constants import (
    ComplianceStatus,
    GovernanceTaskStatus,
    GovernanceTaskType,
    OSType,
    RemediationStatus,
    RiskCompliance,
)
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    HostComplianceSnapshot,
    LinuxPatchDetail,
    Patch,
    PatchBaseline,
    PatchTarget,
)
from apps.patch_mgmt.services import risk_service

_BINDING_TABLE = "patch_host_baseline_binding"
_TASK_TABLE = "patch_governance_task"
_TASK_HOST_TABLE = "patch_governance_task_host"
_PER_TARGET_LOOKUP = re.compile(r"target_id[\"'`]?\s*=\s*(?:%s|\?|\d+)", re.IGNORECASE)
# 批量投影：候选任务 + 主机结果，允许 distinct/exists 余量，不得随 pair 线性增长。
_GOVERNANCE_QUERY_BOUND = 6


def _binding(target, baseline, status=ComplianceStatus.NON_COMPLIANT):
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    if status:
        binding.compliance_status = status
        binding.save(update_fields=["compliance_status", "updated_at"])
    return binding


def _linux_pair(*, name, ip, team, title, pkg_name, baseline=None):
    if baseline is None:
        baseline = PatchBaseline.objects.create(
            name=f"baseline-{name}", os_type=OSType.LINUX, team=[team]
        )
    target = PatchTarget.objects.create(
        name=name, ip=ip, os_type=OSType.LINUX, team=[team]
    )
    binding = _binding(target, baseline)
    patch = Patch.objects.create(title=title, os_type=OSType.LINUX, team=[team])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name=pkg_name)
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=requirement,
        satisfied=False,
        reason="missing",
        evaluated_at="2026-07-10T06:00:00Z",
    )
    return target, patch, binding, requirement


def _install_running(target, patch, *, stage):
    task = GovernanceTask.objects.create(
        name=f"install-{target.name}-{patch.title}",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
        patch_list=[patch.id],
        risk_snapshot=[{"host_id": target.id, "patch_id": patch.id}],
        team=list(target.team),
    )
    GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        stage=stage,
    )
    return task


def _table_queries(captured, table):
    return [query["sql"] for query in captured.captured_queries if table in query["sql"]]


def _governance_queries(captured):
    return [
        query["sql"]
        for query in captured.captured_queries
        if _TASK_TABLE in query["sql"] or _TASK_HOST_TABLE in query["sql"]
    ]


def _per_target_lookups(sqls):
    return [
        sql
        for sql in sqls
        if _PER_TARGET_LOOKUP.search(sql)
        and not re.search(r"target_id[\"'`]?\s+IN\s*\(", sql, re.IGNORECASE)
    ]


def _item_key(item):
    return (
        item.host_id,
        item.patch_id,
        item.baseline_id,
        item.compliance,
        item.remediation,
    )


@pytest.mark.django_db
def test_empty_target_ids_returns_no_risk_items_without_scanning():
    target, patch, _binding_obj, _requirement = _linux_pair(
        name="visible", ip="10.0.0.1", team=1, title="openssl", pkg_name="openssl"
    )
    _install_running(target, patch, stage="installing")

    with CaptureQueriesContext(connection) as captured:
        items = risk_service.compute_risk_items([])

    assert items == []
    assert _table_queries(captured, _BINDING_TABLE) == []
    assert _governance_queries(captured) == []


@pytest.mark.django_db
def test_scoped_binding_query_filters_by_target_id():
    visible, patch, _binding_obj, _requirement = _linux_pair(
        name="visible", ip="10.0.0.1", team=1, title="openssl", pkg_name="openssl"
    )
    hidden, hidden_patch, _hidden_binding, _hidden_req = _linux_pair(
        name="hidden", ip="10.0.0.2", team=2, title="curl", pkg_name="curl"
    )
    _install_running(visible, patch, stage="installing")
    _install_running(hidden, hidden_patch, stage="waiting")

    with CaptureQueriesContext(connection) as captured:
        items = risk_service.compute_risk_items([visible.id])

    binding_sqls = _table_queries(captured, _BINDING_TABLE)
    assert binding_sqls
    assert any(
        re.search(r"target_id[\"'`]?\s+IN\s*\(", sql, re.IGNORECASE) for sql in binding_sqls
    )
    assert {(item.host_id, item.patch_id) for item in items} == {(visible.id, patch.id)}
    assert all(item.host_id != hidden.id for item in items)


@pytest.mark.django_db
def test_scoped_governance_queries_do_not_grow_with_hidden_tenant_pairs():
    visible_pairs = []
    for index in range(2):
        target, patch, _binding_obj, _requirement = _linux_pair(
            name=f"visible-{index}",
            ip=f"10.0.1.{index}",
            team=1,
            title=f"pkg-visible-{index}",
            pkg_name=f"pkg-visible-{index}",
        )
        stage = "installing" if index == 0 else "waiting"
        _install_running(target, patch, stage=stage)
        visible_pairs.append((target, patch, stage))

    visible_ids = [target.id for target, _patch, _stage in visible_pairs]

    with CaptureQueriesContext(connection) as before:
        before_items = risk_service.compute_risk_items(visible_ids)

    before_sqls = _governance_queries(before)
    assert len(before_items) == 2
    assert len(_per_target_lookups(before_sqls)) == 0
    assert len(before_sqls) <= _GOVERNANCE_QUERY_BOUND

    hidden_baseline = PatchBaseline.objects.create(
        name="hidden-baseline", os_type=OSType.LINUX, team=[2]
    )
    hidden_patches = []
    for index in range(4):
        patch = Patch.objects.create(
            title=f"hidden-patch-{index}", os_type=OSType.LINUX, team=[2]
        )
        LinuxPatchDetail.objects.create(patch=patch, pkg_name=f"hidden-pkg-{index}")
        BaselineRequirement.objects.create(baseline=hidden_baseline, patch=patch)
        hidden_patches.append(patch)
    for host_index in range(8):
        target = PatchTarget.objects.create(
            name=f"hidden-{host_index}",
            ip=f"10.0.2.{host_index}",
            os_type=OSType.LINUX,
            team=[2],
        )
        binding = _binding(target, hidden_baseline)
        for patch in hidden_patches:
            HostComplianceSnapshot.objects.create(
                binding=binding,
                requirement=BaselineRequirement.objects.get(
                    baseline=hidden_baseline, patch=patch
                ),
                satisfied=False,
                reason="missing",
                evaluated_at="2026-07-10T06:00:00Z",
            )
            _install_running(target, patch, stage="installing")

    with CaptureQueriesContext(connection) as after:
        after_items = risk_service.compute_risk_items(visible_ids)

    after_sqls = _governance_queries(after)
    assert {(item.host_id, item.patch_id) for item in after_items} == {
        (target.id, patch.id) for target, patch, _stage in visible_pairs
    }
    assert len(_per_target_lookups(after_sqls)) == 0
    assert len(after_sqls) <= _GOVERNANCE_QUERY_BOUND
    assert len(after_sqls) <= len(before_sqls) + 1


@pytest.mark.django_db
def test_scoped_priority_and_exact_pairs_match_unscoped_compute_risk_items():
    baseline = PatchBaseline.objects.create(name="priority", os_type=OSType.LINUX, team=[1])
    first_target = PatchTarget.objects.create(
        name="host-1", ip="10.0.0.1", os_type=OSType.LINUX, team=[1]
    )
    second_target = PatchTarget.objects.create(
        name="host-2", ip="10.0.0.2", os_type=OSType.LINUX, team=[1]
    )
    first_binding = _binding(first_target, baseline)
    second_binding = _binding(second_target, baseline)
    first_patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    second_patch = Patch.objects.create(title="curl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=first_patch, pkg_name="openssl")
    LinuxPatchDetail.objects.create(patch=second_patch, pkg_name="curl")
    first_requirement = BaselineRequirement.objects.create(baseline=baseline, patch=first_patch)
    second_requirement = BaselineRequirement.objects.create(
        baseline=baseline, patch=second_patch
    )
    for binding in (first_binding, second_binding):
        for requirement in (first_requirement, second_requirement):
            HostComplianceSnapshot.objects.create(
                binding=binding,
                requirement=requirement,
                satisfied=False,
                reason="missing",
                evaluated_at="2026-07-10T06:00:00Z",
            )

    install = GovernanceTask.objects.create(
        name="exact-pairs",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[first_target.id, second_target.id],
        patch_list=[first_patch.id, second_patch.id],
        risk_snapshot=[
            {"host_id": first_target.id, "patch_id": first_patch.id},
            {"host_id": second_target.id, "patch_id": second_patch.id},
        ],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=install,
        target_id=first_target.id,
        target_name=first_target.name,
        stage="installing",
    )
    GovernanceTaskHost.objects.create(
        task=install,
        target_id=second_target.id,
        target_name=second_target.name,
        stage="waiting",
    )

    reboot = GovernanceTask.objects.create(
        name="reboot-first",
        task_type=GovernanceTaskType.REBOOT,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[first_target.id],
        patch_list=[first_patch.id],
        risk_snapshot=[{"host_id": first_target.id, "patch_id": first_patch.id}],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=reboot,
        target_id=first_target.id,
        target_name=first_target.name,
        stage="rebooting",
    )
    verify = GovernanceTask.objects.create(
        name="verify-second",
        task_type=GovernanceTaskType.VERIFY,
        status=GovernanceTaskStatus.PENDING,
        target_list=[second_target.id],
        patch_list=[second_patch.id],
        risk_snapshot=[{"host_id": second_target.id, "patch_id": second_patch.id}],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=verify,
        target_id=second_target.id,
        target_name=second_target.name,
        stage="verifying",
    )

    unscoped = risk_service.compute_risk_items()
    scoped = risk_service.compute_risk_items([first_target.id, second_target.id])

    assert sorted(_item_key(item) for item in scoped) == sorted(
        _item_key(item) for item in unscoped
    )
    remediation = {
        (item.host_id, item.patch_id): item.remediation for item in scoped
    }
    assert remediation[(first_target.id, first_patch.id)] == "installing"
    assert remediation[(second_target.id, second_patch.id)] == RemediationStatus.SCHEDULED
    assert remediation[(first_target.id, second_patch.id)] == RemediationStatus.UNPLANNED
    assert remediation[(second_target.id, first_patch.id)] == RemediationStatus.UNPLANNED
    assert all(item.compliance == RiskCompliance.MISSING for item in scoped)
