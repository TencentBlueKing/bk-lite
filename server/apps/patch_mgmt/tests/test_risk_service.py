"""风险计算服务单元测试"""

import pytest

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
    WindowsPatchDetail,
)
from apps.patch_mgmt.services import risk_service


def _binding(target, baseline, status=ComplianceStatus.NON_COMPLIANT):
    """创建已评估的基线绑定；默认 non_compliant，确保风险项会生成。"""
    binding = HostBaselineBinding.objects.create(target=target, baseline=baseline)
    if status:
        binding.compliance_status = status
        binding.save(update_fields=["compliance_status", "updated_at"])
    return binding


@pytest.mark.django_db
def test_compute_risk_items_uses_snapshot_when_present():
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(
        name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1]
    )
    binding = _binding(target, baseline)

    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=req,
        satisfied=False,
        evidence={"pkg_name": "openssl"},
        reason="missing",
        evaluated_at="2026-07-10T06:00:00Z",
    )

    items = risk_service.compute_risk_items()
    assert len(items) == 1
    assert items[0].compliance == RiskCompliance.MISSING
    assert items[0].remediation == RemediationStatus.UNPLANNED
    assert items[0].evaluated_at.isoformat().startswith("2026-07-10T06:00:00")
    assert items[0].to_dict()["evaluated_at"].startswith("2026-07-10T06:00:00")


@pytest.mark.django_db
def test_compute_risk_items_skips_satisfied_snapshot():
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(
        name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1]
    )
    binding = _binding(target, baseline)

    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=req,
        satisfied=True,
        evidence={"pkg_name": "openssl"},
        reason="ok",
        evaluated_at="2026-07-10T06:00:00Z",
    )

    items = risk_service.compute_risk_items()
    assert len(items) == 0


@pytest.mark.django_db
def test_newer_install_and_active_reboot_override_satisfied_snapshot():
    """旧快照已满足时，较新安装待重启及活动重启状态仍必须展示。"""
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.WINDOWS, team=[1])
    target = PatchTarget.objects.create(
        name="windows-host", ip="10.0.0.1", os_type=OSType.WINDOWS, team=[1]
    )
    binding = _binding(target, baseline)
    patch = Patch.objects.create(title="KB6000009", os_type=OSType.WINDOWS, team=[1])
    WindowsPatchDetail.objects.create(patch=patch, kb_number="KB6000009")
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=requirement,
        satisfied=True,
        reason="KB 已安装",
        evaluated_at="2026-07-24T00:00:00Z",
    )
    verify = GovernanceTask.objects.create(
        name="旧验证",
        task_type=GovernanceTaskType.VERIFY,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[target.id],
        patch_list=[patch.id],
        risk_snapshot=[{"host_id": target.id, "patch_id": patch.id}],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=verify, target_id=target.id, target_name=target.name, stage="completed"
    )
    install = GovernanceTask.objects.create(
        name="较新重试安装",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[target.id],
        patch_list=[patch.id],
        risk_snapshot=[{"host_id": target.id, "patch_id": patch.id}],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=install, target_id=target.id, target_name=target.name, stage="pending_reboot"
    )

    items = risk_service.compute_risk_items()

    assert len(items) == 1
    assert items[0].compliance == RiskCompliance.SATISFIED
    assert items[0].remediation == RemediationStatus.PENDING_REBOOT

    reboot = GovernanceTask.objects.create(
        name="自动重启",
        task_type=GovernanceTaskType.REBOOT,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
        risk_snapshot=[{"host_id": target.id, "patch_id": patch.id}],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=reboot, target_id=target.id, target_name=target.name, stage="rebooting"
    )

    rebooting_items = risk_service.compute_risk_items()

    assert len(rebooting_items) == 1
    assert rebooting_items[0].remediation == "rebooting"


@pytest.mark.django_db
def test_failed_binding_does_not_expose_stale_snapshot_as_current_risk():
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    binding = _binding(target, baseline, status=ComplianceStatus.FAILED)
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    requirement = BaselineRequirement.objects.create(baseline=baseline, patch=patch)
    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=requirement,
        satisfied=False,
        reason="旧快照",
        evaluated_at="2026-07-10T06:00:00Z",
    )

    assert risk_service.compute_risk_items() == []


@pytest.mark.django_db
def test_compute_risk_items_missing_without_snapshot():
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(
        name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1]
    )
    _binding(target, baseline)

    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    items = risk_service.compute_risk_items()
    assert len(items) == 1
    assert items[0].compliance == RiskCompliance.MISSING


@pytest.mark.django_db
def test_aggregate_by_host_includes_os_type():
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(
        name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1]
    )
    _binding(target, baseline)
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    items = risk_service.compute_risk_items()
    data = risk_service.aggregate_by_host(items)
    assert len(data) == 1
    assert data[0]["os_type"] == OSType.LINUX


@pytest.mark.django_db
def test_aggregate_by_baseline_includes_apply():
    baseline = PatchBaseline.objects.create(name="win-baseline", os_type=OSType.WINDOWS, team=[1])
    target = PatchTarget.objects.create(
        name="host", ip="10.0.0.1", os_type=OSType.WINDOWS, team=[1]
    )
    _binding(target, baseline)
    patch = Patch.objects.create(title="win-patch", os_type=OSType.WINDOWS, team=[1])
    WindowsPatchDetail.objects.create(
        patch=patch, kb_number="KB5034441", product_list=["Windows Server 2019"], architectures=["x64"]
    )
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    items = risk_service.compute_risk_items()
    data = risk_service.aggregate_by_baseline(items)
    assert len(data) == 1
    assert "Windows" in data[0]["apply"]
    assert "Windows Server 2019" in data[0]["apply"]
    assert "x64" in data[0]["apply"]


@pytest.mark.django_db
def test_filter_risk_items_by_host_name():
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(name="web-01", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    _binding(target, baseline)
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    items = risk_service.compute_risk_items()
    assert len(risk_service.filter_risk_items(items, {"host_name": "web"})) == 1
    assert len(risk_service.filter_risk_items(items, {"host_name": "db"})) == 0
    # 主机名称搜索不匹配 IP
    assert len(risk_service.filter_risk_items(items, {"host_name": "10.0.0.1"})) == 0


@pytest.mark.django_db
def test_filter_risk_items_by_patch_name():
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    _binding(target, baseline)
    patch = Patch.objects.create(title="openssl security update", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    items = risk_service.compute_risk_items()
    assert len(risk_service.filter_risk_items(items, {"patch_name": "openssl"})) == 1
    assert len(risk_service.filter_risk_items(items, {"patch_name": "curl"})) == 0


@pytest.mark.django_db
def test_filter_risk_items_by_baseline_name():
    baseline = PatchBaseline.objects.create(name="production-baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    _binding(target, baseline)
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    items = risk_service.compute_risk_items()
    assert len(risk_service.filter_risk_items(items, {"baseline_name": "production"})) == 1
    assert len(risk_service.filter_risk_items(items, {"baseline_name": "staging"})) == 0


@pytest.mark.django_db
def test_compute_risk_items_install_completed_pending_reboot():
    """安装完成但未重启：合规性仍缺失，治理状态为待重启。"""
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    binding = _binding(target, baseline)

    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    # 模拟一次已完成的安装任务（host stage=pending_reboot）
    task = GovernanceTask.objects.create(
        name="install",
        task_type="install",
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[target.id],
        patch_list=[patch.id],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=task, target_id=target.id, target_name="host",
        stage="pending_reboot", stage_color="warning",
    )

    items = risk_service.compute_risk_items()
    assert len(items) == 1
    assert items[0].compliance == RiskCompliance.MISSING
    assert items[0].remediation == RemediationStatus.PENDING_REBOOT


@pytest.mark.django_db
def test_compute_risk_items_install_completed_verify_running_is_verifying():
    """安装后判定无需重启时，自动验证完成前应明确显示“验证中”。"""
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    _binding(target, baseline)
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    install_task = GovernanceTask.objects.create(
        name="install",
        task_type="install",
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[target.id],
        patch_list=[patch.id],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=install_task,
        target_id=target.id,
        target_name=target.name,
        stage="completed",
        stage_color="success",
    )
    GovernanceTask.objects.create(
        name="verify",
        task_type="verify",
        status=GovernanceTaskStatus.PENDING,
        target_list=[target.id],
        patch_list=[patch.id],
        team=[1],
    )

    items = risk_service.compute_risk_items()

    assert len(items) == 1
    assert items[0].remediation == "verifying"


@pytest.mark.django_db
def test_compute_risk_items_matches_exact_host_patch_snapshot_pair():
    """批量治理的 target_list×patch_list 不能被误当成所有主机补丁组合。"""
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
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
    second_requirement = BaselineRequirement.objects.create(baseline=baseline, patch=second_patch)
    for binding in (first_binding, second_binding):
        for requirement in (first_requirement, second_requirement):
            HostComplianceSnapshot.objects.create(
                binding=binding,
                requirement=requirement,
                satisfied=False,
                reason="missing",
                evaluated_at="2026-07-10T06:00:00Z",
            )

    task = GovernanceTask.objects.create(
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
        task=task, target_id=first_target.id, target_name=first_target.name, stage="installing"
    )
    GovernanceTaskHost.objects.create(
        task=task, target_id=second_target.id, target_name=second_target.name, stage="waiting"
    )

    remediation = {
        (item.host_id, item.patch_id): item.remediation
        for item in risk_service.compute_risk_items()
    }

    assert remediation[(first_target.id, first_patch.id)] == "installing"
    assert remediation[(second_target.id, second_patch.id)] == RemediationStatus.SCHEDULED
    assert remediation[(first_target.id, second_patch.id)] == RemediationStatus.UNPLANNED
    assert remediation[(second_target.id, first_patch.id)] == RemediationStatus.UNPLANNED


@pytest.mark.django_db
def test_compute_risk_items_install_and_reboot_completed_pending_reboot():
    """安装+重启都完成，但快照未更新：仍保持待重启（等待自动验证），不会直接标记已修复。"""
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    binding = _binding(target, baseline)

    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    install_task = GovernanceTask.objects.create(
        name="install",
        task_type="install",
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[target.id],
        patch_list=[patch.id],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=install_task, target_id=target.id, target_name="host",
        stage="pending_reboot", stage_color="warning",
    )
    reboot_task = GovernanceTask.objects.create(
        name="reboot",
        task_type="reboot",
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[target.id],
        team=[1],
    )
    GovernanceTaskHost.objects.create(
        task=reboot_task, target_id=target.id, target_name="host",
        stage="pending_reboot", stage_color="warning",
    )

    items = risk_service.compute_risk_items()
    assert len(items) == 1
    assert items[0].compliance == RiskCompliance.MISSING
    assert items[0].remediation == RemediationStatus.PENDING_REBOOT


@pytest.mark.django_db
def test_compute_risk_items_satisfied_after_assess_disappears():
    """评估快照已满足时，风险项应从列表中移除。"""
    baseline = PatchBaseline.objects.create(name="baseline", os_type=OSType.LINUX, team=[1])
    target = PatchTarget.objects.create(name="host", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
    binding = _binding(target, baseline)

    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    LinuxPatchDetail.objects.create(patch=patch, pkg_name="openssl")
    req = BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    HostComplianceSnapshot.objects.create(
        binding=binding,
        requirement=req,
        satisfied=True,
        evidence={"pkg_name": "openssl"},
        reason="ok",
        evaluated_at="2026-07-10T06:00:00Z",
    )

    items = risk_service.compute_risk_items()
    assert len(items) == 0
