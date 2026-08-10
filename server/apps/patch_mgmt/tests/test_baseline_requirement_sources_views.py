"""基线补丁要求的来源展示接口契约。"""

import pytest
from rest_framework import status

from apps.patch_mgmt.constants import OSType, PatchSourceType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    LinuxPatchDetail,
    Patch,
    PatchBaseline,
    PatchSource,
)


BASELINE_URL = "/api/v1/patch_mgmt/api/baseline/"


@pytest.mark.django_db
def test_requirements_api_returns_patch_source_details(su_client):
    source = PatchSource.objects.create(
        name="Ubuntu 24.04 security",
        source_type=PatchSourceType.APT_REPO,
        url="https://archive.ubuntu.com/ubuntu",
        team=[1],
    )
    patch = Patch.objects.create(
        title="USN-7000-1",
        os_type=OSType.LINUX,
        team=[1],
    )
    patch.sources.add(source)
    LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name="openssl",
        pkg_version="3.0.13-0ubuntu3.5",
        distro_name="Ubuntu",
        os_version_range="24.04",
        architectures=["x86_64"],
        repo_type="apt",
    )
    baseline = PatchBaseline.objects.create(
        name="Ubuntu 基线",
        os_type=OSType.LINUX,
        team=[1],
    )
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    response = su_client.get(f"{BASELINE_URL}{baseline.id}/requirements/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data[0]["patch_source_type"] == PatchSourceType.APT_REPO
    assert response.data[0]["patch_source_details"] == [
        {
            "source_id": source.id,
            "source_type": PatchSourceType.APT_REPO,
            "url": "https://archive.ubuntu.com/ubuntu",
            "deleted": False,
        }
    ]


@pytest.mark.django_db
def test_requirements_api_returns_manual_patch_source(su_client):
    patch = Patch.objects.create(
        title="手动录入补丁",
        os_type=OSType.LINUX,
        team=[1],
    )
    LinuxPatchDetail.objects.create(
        patch=patch,
        pkg_name="manual-package",
        pkg_version="1.0",
        distro_name="Linux",
        architectures=["x86_64"],
        repo_type="apt",
    )
    baseline = PatchBaseline.objects.create(
        name="手动补丁基线",
        os_type=OSType.LINUX,
        team=[1],
    )
    BaselineRequirement.objects.create(baseline=baseline, patch=patch)

    response = su_client.get(f"{BASELINE_URL}{baseline.id}/requirements/")

    assert response.status_code == status.HTTP_200_OK
    assert response.data[0]["patch_source_type"] == "manual"
    assert response.data[0]["patch_source_details"] == []
