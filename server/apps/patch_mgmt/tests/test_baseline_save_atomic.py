"""基线保存必须在同一事务内写入主体和要求集。"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from apps.patch_mgmt.constants import ComplianceStatus, OSType
from apps.patch_mgmt.models import BaselineRequirement, HostBaselineBinding, Patch, PatchBaseline, PatchTarget


BASELINE_URL = "/api/v1/patch_mgmt/api/baseline/"
SAVE_URL = f"{BASELINE_URL}save/"


def _patch(title):
    return Patch.objects.create(title=title, os_type=OSType.LINUX, team=[1])


def _baseline(name="linux-baseline", **kwargs):
    return PatchBaseline.objects.create(name=name, os_type=OSType.LINUX, team=[1], **kwargs)


def _requirement(baseline, patch, condition=""):
    return BaselineRequirement.objects.create(baseline=baseline, patch=patch, condition=condition)


def _patch_ids(baseline):
    return list(baseline.requirements.order_by("id").values_list("patch_id", flat=True))


@pytest.mark.django_db
class TestBaselineSaveAtomic:
    def test_legacy_put_then_missing_patches_keeps_renamed_baseline(self, su_client):
        patch = _patch("openssl")
        baseline = _baseline("old-name")
        _requirement(baseline, patch, condition="openssl >= 3.0")

        put_resp = su_client.put(
            f"{BASELINE_URL}{baseline.id}/",
            {"name": "renamed", "os_type": OSType.LINUX, "description": ""},
            format="json",
        )
        add_resp = su_client.post(
            f"{BASELINE_URL}{baseline.id}/requirements/",
            {"patch_ids": [999999]},
            format="json",
        )

        baseline.refresh_from_db()
        assert put_resp.status_code == status.HTTP_200_OK
        assert add_resp.status_code >= 400
        assert baseline.name == "renamed"
        assert _patch_ids(baseline) == [patch.id]

    def test_create_save_writes_baseline_and_requirements_together(self, su_client):
        first = _patch("openssl")
        second = _patch("tar")

        resp = su_client.post(
            SAVE_URL,
            {
                "name": "linux-security",
                "os_type": OSType.LINUX,
                "description": "core packages",
                "patch_ids": [first.id, second.id],
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        baseline = PatchBaseline.objects.get(name="linux-security")
        assert baseline.description == "core packages"
        assert baseline.os_type == OSType.LINUX
        assert set(_patch_ids(baseline)) == {first.id, second.id}

    def test_create_save_missing_patches_leaves_zero_baselines(self, su_client):
        existing = _patch("openssl")

        resp = su_client.post(
            SAVE_URL,
            {
                "name": "should-not-exist",
                "os_type": OSType.LINUX,
                "description": "",
                "patch_ids": [existing.id, 999999],
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert PatchBaseline.objects.filter(name="should-not-exist").count() == 0
        assert PatchBaseline.objects.count() == 0

    def test_create_save_rejects_empty_patch_ids(self, su_client):
        resp = su_client.post(
            SAVE_URL,
            {
                "name": "empty-reqs",
                "os_type": OSType.LINUX,
                "patch_ids": [],
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert PatchBaseline.objects.count() == 0

    def test_update_save_replaces_requirements_and_renames_in_one_transaction(self, su_client):
        kept = _patch("openssl")
        removed = _patch("tar")
        added = _patch("curl")
        baseline = _baseline("old-name", description="old")
        kept_req = _requirement(baseline, kept, condition="openssl >= 3.0")
        _requirement(baseline, removed, condition="tar >= 1.0")
        target = PatchTarget.objects.create(name="web-01", ip="10.0.0.1", os_type=OSType.LINUX, team=[1])
        binding = HostBaselineBinding.objects.create(
            target=target,
            baseline=baseline,
            compliance_status=ComplianceStatus.COMPLIANT,
            missing_count=2,
        )
        expected = su_client.get(f"{BASELINE_URL}{baseline.id}/").data["updated_at"]

        resp = su_client.put(
            f"{BASELINE_URL}{baseline.id}/save/",
            {
                "name": "new-name",
                "os_type": OSType.WINDOWS,
                "description": "updated",
                "patch_ids": [kept.id, added.id],
                "expected_updated_at": expected,
            },
            format="json",
        )

        baseline.refresh_from_db()
        kept_req.refresh_from_db()
        binding.refresh_from_db()
        assert resp.status_code == status.HTTP_200_OK
        assert baseline.name == "new-name"
        assert baseline.description == "updated"
        assert baseline.os_type == OSType.LINUX
        assert set(_patch_ids(baseline)) == {kept.id, added.id}
        assert kept_req.condition == "openssl >= 3.0"
        assert binding.compliance_status == ComplianceStatus.PENDING
        assert binding.missing_count == 0

    def test_update_save_missing_patches_leaves_name_and_requirements(self, su_client):
        patch = _patch("openssl")
        baseline = _baseline("keep-me", description="unchanged")
        _requirement(baseline, patch, condition="openssl >= 3.0")
        expected = su_client.get(f"{BASELINE_URL}{baseline.id}/").data["updated_at"]

        resp = su_client.put(
            f"{BASELINE_URL}{baseline.id}/save/",
            {
                "name": "should-not-apply",
                "description": "mutated",
                "patch_ids": [patch.id, 999999],
                "expected_updated_at": expected,
            },
            format="json",
        )

        baseline.refresh_from_db()
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert baseline.name == "keep-me"
        assert baseline.description == "unchanged"
        assert _patch_ids(baseline) == [patch.id]
        assert baseline.requirements.get().condition == "openssl >= 3.0"

    def test_update_save_stale_expected_updated_at_returns_409_and_writes_nothing(self, su_client):
        patch = _patch("openssl")
        extra = _patch("tar")
        baseline = _baseline("keep-me")
        _requirement(baseline, patch, condition="openssl >= 3.0")
        stale = (timezone.now() - timedelta(days=1)).isoformat()

        resp = su_client.put(
            f"{BASELINE_URL}{baseline.id}/save/",
            {
                "name": "stale-write",
                "description": "nope",
                "patch_ids": [extra.id],
                "expected_updated_at": stale,
            },
            format="json",
        )

        baseline.refresh_from_db()
        assert resp.status_code == status.HTTP_409_CONFLICT
        assert resp.data["code"] == "stale_baseline"
        assert baseline.name == "keep-me"
        assert _patch_ids(baseline) == [patch.id]

    def test_update_save_same_patch_ids_is_idempotent(self, su_client):
        first = _patch("openssl")
        second = _patch("tar")
        baseline = _baseline("linux-security")
        first_req = _requirement(baseline, first, condition="openssl >= 3.0")
        second_req = _requirement(baseline, second, condition="tar >= 1.0")
        expected = su_client.get(f"{BASELINE_URL}{baseline.id}/").data["updated_at"]

        resp = su_client.put(
            f"{BASELINE_URL}{baseline.id}/save/",
            {
                "name": "linux-security",
                "description": "",
                "patch_ids": [second.id, first.id],
                "expected_updated_at": expected,
            },
            format="json",
        )

        baseline.refresh_from_db()
        assert resp.status_code == status.HTTP_200_OK
        assert set(_patch_ids(baseline)) == {first.id, second.id}
        assert baseline.requirements.get(pk=first_req.id).condition == "openssl >= 3.0"
        assert baseline.requirements.get(pk=second_req.id).condition == "tar >= 1.0"
        assert baseline.requirements.count() == 2

    def test_legacy_add_and_delete_requirements_still_work(self, su_client):
        existing = _patch("openssl")
        extra = _patch("tar")
        baseline = _baseline()
        original = _requirement(baseline, existing)

        add_resp = su_client.post(
            f"{BASELINE_URL}{baseline.id}/requirements/",
            {"patch_ids": [extra.id]},
            format="json",
        )
        delete_resp = su_client.delete(
            f"{BASELINE_URL}{baseline.id}/requirements/",
            {"requirement_ids": [original.id]},
            format="json",
        )

        assert add_resp.status_code == status.HTTP_200_OK
        assert delete_resp.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
        assert _patch_ids(baseline) == [extra.id]
