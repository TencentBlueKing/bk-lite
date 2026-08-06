"""公开补丁合规评估服务契约。"""

from apps.patch_mgmt.constants import OSType, RequirementAssessmentStatus
from apps.patch_mgmt.services.compliance_evaluator import (
    HostAssessmentFacts,
    LinuxPackageFact,
    RequirementSpec,
    WindowsUpdateFacts,
    evaluate_requirements,
)


def test_linux_uses_native_comparison_and_does_not_treat_absence_as_satisfied():
    requirements = [
        RequirementSpec(1, OSType.LINUX, "openssl", required_version="3.0.0"),
        RequirementSpec(2, OSType.LINUX, "curl", required_version="8.0.0"),
        RequirementSpec(3, OSType.LINUX, "bash", required_version="5.0.0"),
        RequirementSpec(4, OSType.LINUX, "tar", required_version="1.0.0"),
    ]
    facts = HostAssessmentFacts(
        linux_packages={
            "openssl": LinuxPackageFact(installed=True, installed_version="3.0.1", comparison=1),
            "curl": LinuxPackageFact(installed=True, installed_version="7.9.0", comparison=-1),
            "bash": LinuxPackageFact(installed=False),
            "tar": LinuxPackageFact(
                installed=True,
                installed_version="1.2.0",
                comparison=None,
                error="目标包管理器无法比较版本",
            ),
        }
    )

    result = evaluate_requirements(requirements, facts)

    assert result[1].status == RequirementAssessmentStatus.SATISFIED
    assert result[2].status == RequirementAssessmentStatus.MISSING
    assert result[3].status == RequirementAssessmentStatus.MISSING
    assert result[4].status == RequirementAssessmentStatus.UNKNOWN
    assert result[3].satisfied is False


def test_collection_failure_is_unknown_instead_of_compliant_or_missing():
    requirements = [
        RequirementSpec(1, OSType.LINUX, "openssl", required_version="3.0.0"),
        RequirementSpec(2, OSType.WINDOWS, "KB5000001"),
    ]

    result = evaluate_requirements(
        requirements,
        HostAssessmentFacts(collection_error="执行器返回无法解析的结果"),
    )

    assert {item.status for item in result.values()} == {RequirementAssessmentStatus.UNKNOWN}


def test_windows_supports_installed_replacement_missing_not_applicable_and_unknown():
    requirements = [
        RequirementSpec(1, OSType.WINDOWS, "KB5000001", replacement_identifiers=("KB5000002",)),
        RequirementSpec(2, OSType.WINDOWS, "KB5000003"),
        RequirementSpec(3, OSType.WINDOWS, "KB5000004"),
        RequirementSpec(4, OSType.WINDOWS, "KB5000005"),
    ]
    facts = HostAssessmentFacts(
        windows=WindowsUpdateFacts(
            installed_kbs=frozenset({"KB5000002"}),
            applicable_missing_kbs=frozenset({"KB5000003"}),
            not_applicable_kbs=frozenset({"KB5000004"}),
        )
    )

    result = evaluate_requirements(requirements, facts)

    assert result[1].status == RequirementAssessmentStatus.SATISFIED
    assert result[1].evidence["satisfied_by"] == "KB5000002"
    assert result[2].status == RequirementAssessmentStatus.MISSING
    assert result[3].status == RequirementAssessmentStatus.NOT_APPLICABLE
    assert result[4].status == RequirementAssessmentStatus.UNKNOWN


def test_windows_currently_offered_revision_wins_over_same_installed_kb():
    requirement = RequirementSpec(1, OSType.WINDOWS, "KB4052623")
    facts = HostAssessmentFacts(
        windows=WindowsUpdateFacts(
            installed_kbs=frozenset({"KB4052623"}),
            applicable_missing_kbs=frozenset({"KB4052623"}),
        )
    )

    result = evaluate_requirements([requirement], facts)

    assert result[1].status == RequirementAssessmentStatus.MISSING
    assert result[1].reason == "KB4052623 适用但未安装"
