"""补丁库来源和基线引用筛选的公开接口契约。"""

import pytest
from django.utils import timezone
from rest_framework import status

from apps.patch_mgmt.constants import OSType, PatchSourceType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    LinuxPatchDetail,
    Patch,
    PatchBaseline,
    PatchSource,
    WindowsPatchDetail,
)


BASE = "/api/v1/patch_mgmt/api"


@pytest.mark.django_db
def test_patch_list_exposes_all_source_addresses_and_filters_by_origin_type(su_client):
    apt_source = PatchSource.objects.create(
        name="apt-1",
        source_type=PatchSourceType.APT_REPO,
        url="https://repo-1.example.com/ubuntu",
        team=[1],
    )
    mirror_source = PatchSource.objects.create(
        name="apt-2",
        source_type=PatchSourceType.APT_REPO,
        url="https://repo-2.example.com/ubuntu",
        team=[1],
    )
    synced = Patch.objects.create(
        title="Ubuntu openssl update",
        os_type=OSType.LINUX,
        last_synced_at=timezone.now(),
        team=[1],
    )
    LinuxPatchDetail.objects.create(
        patch=synced,
        pkg_name="openssl",
        pkg_version="3.0.2",
        repo_type="apt",
    )
    synced.sources.add(apt_source, mirror_source)
    Patch.objects.create(title="manual patch", os_type=OSType.LINUX, team=[1])

    response = su_client.get(
        f"{BASE}/patch/?page_size=-1&source_type={PatchSourceType.APT_REPO}"
    )

    assert response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in response.data] == [synced.id]
    assert response.data[0]["source_type"] == PatchSourceType.APT_REPO
    assert response.data[0]["source_details"] == [
        {
            "source_id": apt_source.id,
            "source_type": PatchSourceType.APT_REPO,
            "url": "https://repo-1.example.com/ubuntu",
            "deleted": False,
        },
        {
            "source_id": mirror_source.id,
            "source_type": PatchSourceType.APT_REPO,
            "url": "https://repo-2.example.com/ubuntu",
            "deleted": False,
        },
    ]

    manual_response = su_client.get(
        f"{BASE}/patch/?page_size=-1&source_type=manual"
    )

    assert manual_response.status_code == status.HTTP_200_OK
    assert [item["title"] for item in manual_response.data] == ["manual patch"]
    assert manual_response.data[0]["source_type"] == "manual"
    assert manual_response.data[0]["source_details"] == []


@pytest.mark.django_db
def test_baseline_list_filters_by_patch_ids_and_returns_requirement_names(su_client):
    linux_patch = Patch.objects.create(
        title="Linux update description",
        os_type=OSType.LINUX,
        team=[1],
    )
    LinuxPatchDetail.objects.create(
        patch=linux_patch,
        pkg_name="openssl",
        pkg_version="3.0.2",
    )
    windows_patch = Patch.objects.create(
        title="Windows update description",
        os_type=OSType.WINDOWS,
        team=[1],
    )
    WindowsPatchDetail.objects.create(
        patch=windows_patch,
        kb_number="KB5034441",
    )
    selected = PatchBaseline.objects.create(
        name="selected baseline",
        os_type=OSType.LINUX,
        team=[1],
    )
    other = PatchBaseline.objects.create(
        name="other baseline",
        os_type=OSType.WINDOWS,
        team=[1],
    )
    BaselineRequirement.objects.create(baseline=selected, patch=linux_patch)
    BaselineRequirement.objects.create(baseline=selected, patch=windows_patch)
    BaselineRequirement.objects.create(baseline=other, patch=windows_patch)

    response = su_client.get(
        f"{BASE}/baseline/?page_size=-1&patch_ids={linux_patch.id}"
    )

    assert response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in response.data] == [selected.id]
    assert response.data[0]["requirement_names"] == ["openssl", "KB5034441"]
