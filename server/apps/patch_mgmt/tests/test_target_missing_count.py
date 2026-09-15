"""目标序列化 missing_count 必须读持久化值，不得把 0 误当成未评估。"""

import pytest

from apps.patch_mgmt.constants import ComplianceStatus, OSType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    HostBaselineBinding,
    Patch,
    PatchBaseline,
    PatchTarget,
)
from apps.patch_mgmt.serializers.patch_target import PatchTargetSerializer


def _serializer(request_factory, authenticated_user):
    request = request_factory.post("/")
    request.user = authenticated_user
    return PatchTargetSerializer(context={"request": request})


def _requirements(baseline, count):
    for index in range(count):
        patch = Patch.objects.create(
            title=f"req-{index}",
            os_type=OSType.LINUX,
            team=[1],
        )
        BaselineRequirement.objects.create(baseline=baseline, patch=patch)


def _bound_target(*, name, ip, status, missing_count, requirement_count=3):
    target = PatchTarget.objects.create(
        name=name,
        ip=ip,
        os_type=OSType.LINUX,
        team=[1],
    )
    baseline = PatchBaseline.objects.create(
        name=f"{name}-baseline",
        os_type=OSType.LINUX,
        team=[1],
    )
    _requirements(baseline, requirement_count)
    HostBaselineBinding.objects.create(
        target=target,
        baseline=baseline,
        compliance_status=status,
        missing_count=missing_count,
    )
    return PatchTarget.objects.select_related("baseline_binding__baseline").get(pk=target.pk)


@pytest.mark.django_db
def test_compliant_zero_missing_count_is_not_requirement_total(
    request_factory, authenticated_user
):
    target = _bound_target(
        name="compliant-host",
        ip="10.0.0.1",
        status=ComplianceStatus.COMPLIANT,
        missing_count=0,
        requirement_count=3,
    )

    assert _serializer(request_factory, authenticated_user).get_missing_count(target) == 0


@pytest.mark.django_db
def test_non_compliant_returns_persisted_positive_missing_count(
    request_factory, authenticated_user
):
    target = _bound_target(
        name="non-compliant-host",
        ip="10.0.0.2",
        status=ComplianceStatus.NON_COMPLIANT,
        missing_count=2,
        requirement_count=3,
    )

    assert _serializer(request_factory, authenticated_user).get_missing_count(target) == 2


@pytest.mark.django_db
def test_pending_zero_missing_count_is_not_requirement_total(
    request_factory, authenticated_user
):
    target = _bound_target(
        name="pending-host",
        ip="10.0.0.3",
        status=ComplianceStatus.PENDING,
        missing_count=0,
        requirement_count=3,
    )

    assert _serializer(request_factory, authenticated_user).get_missing_count(target) == 0


@pytest.mark.django_db
def test_failed_returns_persisted_missing_count(request_factory, authenticated_user):
    target = _bound_target(
        name="failed-host",
        ip="10.0.0.4",
        status=ComplianceStatus.FAILED,
        missing_count=0,
        requirement_count=3,
    )

    assert _serializer(request_factory, authenticated_user).get_missing_count(target) == 0


@pytest.mark.django_db
def test_unbound_target_missing_count_is_zero(request_factory, authenticated_user):
    target = PatchTarget.objects.create(
        name="unbound-host",
        ip="10.0.0.5",
        os_type=OSType.LINUX,
        team=[1],
    )

    assert _serializer(request_factory, authenticated_user).get_missing_count(target) == 0
