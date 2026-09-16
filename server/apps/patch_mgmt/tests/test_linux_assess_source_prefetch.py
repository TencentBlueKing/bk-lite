"""Linux 评估写回来源检查必须批量预取 patch.sources，不能随要求条数线性查询。"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.patch_mgmt.constants import OSType, PatchSourceType, RequirementAssessmentStatus
from apps.patch_mgmt.models import (
    BaselineRequirement,
    LinuxPatchDetail,
    Patch,
    PatchBaseline,
    PatchSource,
)
from apps.patch_mgmt.services.assess_parsers import linux_requirement_specs
from apps.patch_mgmt.services.compliance_evaluator import (
    HostAssessmentFacts,
    LinuxPackageFact,
    evaluate_requirements,
)


SOURCES_QUERY_BOUND = 2


def _load_requirements_like_assess_writeback(baseline: PatchBaseline) -> list:
    return list(
        baseline.requirements.select_related("patch__linux_detail", "patch__windows_detail")
    )


def _count_source_m2m_queries(captured: CaptureQueriesContext) -> int:
    through = Patch.sources.through._meta.db_table
    return sum(1 for query in captured if through in query["sql"])


def _make_linux_requirement(
    *,
    baseline: PatchBaseline,
    title: str,
    pkg_name: str,
    sources: list[PatchSource] | None = None,
    deleted_source_snapshots: list | None = None,
    repo_type: str = "apt",
    packages: list[dict[str, str]] | None = None,
) -> BaselineRequirement:
    patch = Patch.objects.create(
        title=title,
        os_type=OSType.LINUX,
        team=[1],
        deleted_source_snapshots=deleted_source_snapshots or [],
    )
    if sources:
        patch.sources.add(*sources)
    detail = LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name=pkg_name,
        pkg_version="1.0",
        distro_name="Ubuntu",
        os_version_range="24.04",
        architectures=["x86_64"],
        repo_type=repo_type,
    )
    if packages is not None:
        detail.packages = packages
        detail.save(update_fields=["packages"])
    return BaselineRequirement.objects.create(baseline=baseline, patch=patch)


def _make_source(name: str, source_type: str) -> PatchSource:
    return PatchSource.objects.create(
        name=name,
        source_type=source_type,
        url=f"https://example.com/{name}",
        team=[1],
    )


def _specs_source_queries(requirements: list) -> tuple[dict[int, list], int]:
    with CaptureQueriesContext(connection) as captured:
        specs = linux_requirement_specs(requirements)
    return specs, _count_source_m2m_queries(captured)


@pytest.mark.django_db
def test_linux_assess_writeback_source_queries_do_not_grow_with_requirement_count():
    apt_source = _make_source("ubuntu-security", PatchSourceType.APT_REPO)
    small_baseline = PatchBaseline.objects.create(name="small-assess", os_type=OSType.LINUX, team=[1])
    large_baseline = PatchBaseline.objects.create(name="large-assess", os_type=OSType.LINUX, team=[1])
    for index in range(4):
        _make_linux_requirement(
            baseline=small_baseline,
            title=f"small-{index}",
            pkg_name=f"pkg-small-{index}",
            sources=[apt_source],
        )
    for index in range(12):
        _make_linux_requirement(
            baseline=large_baseline,
            title=f"large-{index}",
            pkg_name=f"pkg-large-{index}",
            sources=[apt_source],
        )

    _, small_queries = _specs_source_queries(_load_requirements_like_assess_writeback(small_baseline))
    _, large_queries = _specs_source_queries(_load_requirements_like_assess_writeback(large_baseline))

    assert small_queries <= SOURCES_QUERY_BOUND
    assert large_queries <= SOURCES_QUERY_BOUND
    assert large_queries <= small_queries


@pytest.mark.django_db
def test_linux_specs_keep_empty_sources_and_multi_package_semantics():
    baseline = PatchBaseline.objects.create(name="empty-and-multi", os_type=OSType.LINUX, team=[1])
    empty_req = _make_linux_requirement(
        baseline=baseline,
        title="no-source",
        pkg_name="empty-pkg",
        sources=[],
    )
    apt_a = _make_source("apt-a", PatchSourceType.APT_REPO)
    apt_b = _make_source("apt-b", PatchSourceType.APT_REPO)
    multi_source_req = _make_linux_requirement(
        baseline=baseline,
        title="two-apt-sources",
        pkg_name="openssl",
        sources=[apt_a, apt_b],
        packages=[
            {"name": "openssl", "version": "3.0.1", "arch": "x86_64"},
            {"name": "libssl3", "version": "3.0.1", "arch": "x86_64"},
            {"name": "openssl", "version": "3.0.1", "arch": "x86_64"},
        ],
    )

    specs = linux_requirement_specs(_load_requirements_like_assess_writeback(baseline))

    assert [spec.identifier for spec in specs[empty_req.id]] == ["empty-pkg"]
    assert specs[empty_req.id][0].configuration_error == ""
    assert [spec.identifier for spec in specs[multi_source_req.id]] == ["openssl", "libssl3"]
    assert specs[multi_source_req.id][0].configuration_error == ""


@pytest.mark.django_db
def test_linux_specs_mark_apt_rpm_family_conflict_unknown():
    baseline = PatchBaseline.objects.create(name="family-conflict", os_type=OSType.LINUX, team=[1])
    apt_source = _make_source("apt-mixed", PatchSourceType.APT_REPO)
    rpm_source = _make_source("yum-mixed", PatchSourceType.YUM_REPO)
    conflict_req = _make_linux_requirement(
        baseline=baseline,
        title="mixed-families",
        pkg_name="conflict-pkg",
        sources=[apt_source, rpm_source],
    )

    specs = linux_requirement_specs(_load_requirements_like_assess_writeback(baseline))

    assert specs[conflict_req.id][0].configuration_error == "conflicting linux package families"


@pytest.mark.django_db
def test_linux_specs_merge_deleted_source_snapshots_into_family_conflict():
    baseline = PatchBaseline.objects.create(name="deleted-source-merge", os_type=OSType.LINUX, team=[1])
    apt_source = _make_source("live-apt", PatchSourceType.APT_REPO)
    deleted_req = _make_linux_requirement(
        baseline=baseline,
        title="deleted-rpm-history",
        pkg_name="snapshot-pkg",
        sources=[apt_source],
        deleted_source_snapshots=[
            {
                "source_id": 99,
                "source_type": PatchSourceType.YUM_REPO,
                "url": "https://example.com/deleted-yum",
            }
        ],
    )

    specs = linux_requirement_specs(_load_requirements_like_assess_writeback(baseline))

    assert specs[deleted_req.id][0].configuration_error == "conflicting linux package families"

    assessment = evaluate_requirements(
        specs[deleted_req.id],
        HostAssessmentFacts(
            linux_packages={"snapshot-pkg": LinuxPackageFact(installed=False)},
        ),
    )[deleted_req.id]
    assert assessment.status == RequirementAssessmentStatus.UNKNOWN
    assert "APT" in assessment.reason and "RPM" in assessment.reason
