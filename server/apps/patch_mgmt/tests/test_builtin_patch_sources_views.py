"""全局内置补丁源 API 行为测试。"""

import pytest
from rest_framework import status

from apps.patch_mgmt.constants import PatchSourceType
from apps.patch_mgmt.models import PatchSource


pytestmark = [pytest.mark.unit, pytest.mark.django_db]

PATCH_SOURCE_URL = "/api/v1/patch_mgmt/api/patch_source/"


def _create_builtin(**overrides):
    values = {
        "name": "Oracle Linux 9 BaseOS (YUM)",
        "source_type": PatchSourceType.YUM_REPO,
        "url": "https://yum.oracle.com/repo/OracleLinux/OL9/baseos/latest/x86_64",
        "distro_name": "Oracle Linux",
        "os_version": "9",
        "arch": "x86_64",
        "is_builtin": True,
        "builtin_key": "oracle-linux-9-yum-baseos",
        "team": [],
    }
    values.update(overrides)
    return PatchSource.objects.create(**values)


def _team_client(api_client, authenticated_user, mocker, permissions):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"patch": set(permissions)}
    api_client.cookies["current_team"] = "1"
    mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    return api_client


def test_builtin_sources_are_globally_visible_but_other_team_custom_sources_are_not(
    api_client, authenticated_user, mocker
):
    builtin = PatchSource.objects.create(
        name="Global Ubuntu",
        source_type=PatchSourceType.APT_REPO,
        url="https://security.ubuntu.com/ubuntu",
        distro_name="Ubuntu",
        os_version="24.04",
        arch="x86_64",
        is_builtin=True,
        builtin_key="ubuntu-global",
        team=[],
    )
    PatchSource.objects.create(
        name="Other team",
        source_type=PatchSourceType.APT_REPO,
        url="https://example.com/ubuntu",
        team=[2],
    )
    client = _team_client(
        api_client,
        authenticated_user,
        mocker,
        {"patch_source-View"},
    )

    response = client.get(PATCH_SOURCE_URL)

    assert response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in response.json()["data"]] == [builtin.id]
    assert response.json()["data"][0]["is_builtin"] is True
    assert response.json()["data"][0]["permission"] == ["View"]


def test_team_patch_source_admin_cannot_modify_builtin_source(
    api_client, authenticated_user, mocker
):
    source = _create_builtin()
    client = _team_client(
        api_client,
        authenticated_user,
        mocker,
        {"patch_source-View", "patch_source-Edit"},
    )

    response = client.patch(
        f"{PATCH_SOURCE_URL}{source.id}/",
        {"name": "team changed"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    source.refresh_from_db()
    assert source.name == "Oracle Linux 9 BaseOS (YUM)"


def test_builtin_source_cannot_be_deleted_even_by_superuser(
    api_client, authenticated_user
):
    source = _create_builtin()
    authenticated_user.is_superuser = True

    response = api_client.delete(f"{PATCH_SOURCE_URL}{source.id}/")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert PatchSource.objects.filter(id=source.id).exists()


def test_superuser_can_modify_builtin_source(api_client, authenticated_user):
    source = _create_builtin(
        name="locally customized",
        url="https://mirror.example.com/oracle/9",
        proxy_host="proxy.example.com",
        proxy_port=8080,
        is_enabled=False,
        connectivity_status="connected",
    )
    authenticated_user.is_superuser = True

    update_response = api_client.patch(
        f"{PATCH_SOURCE_URL}{source.id}/",
        {"name": "admin customized"},
        format="json",
    )
    assert update_response.status_code == status.HTTP_200_OK
    source.refresh_from_db()
    assert source.name == "admin customized"
    assert source.url == "https://mirror.example.com/oracle/9"
    assert source.proxy_host == "proxy.example.com"


def test_builtin_source_has_no_restore_defaults_action(api_client, authenticated_user):
    source = _create_builtin()
    authenticated_user.is_superuser = True

    response = api_client.post(
        f"{PATCH_SOURCE_URL}{source.id}/restore_defaults/",
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_superuser_can_enable_and_disable_builtin_source(
    api_client, authenticated_user
):
    source = _create_builtin(is_enabled=True)
    authenticated_user.is_superuser = True

    response = api_client.post(
        f"{PATCH_SOURCE_URL}{source.id}/set_enabled/",
        {"is_enabled": False},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    source.refresh_from_db()
    assert source.is_enabled is False


def test_builtin_source_cannot_use_full_sync_that_would_create_global_patches(
    api_client, authenticated_user, mocker
):
    source = _create_builtin()
    authenticated_user.is_superuser = True
    sync = mocker.patch(
        "apps.patch_mgmt.services.source_sync_service.SourceSyncService.sync_linux_repo"
    )

    response = api_client.post(f"{PATCH_SOURCE_URL}{source.id}/sync/", format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    sync.assert_not_called()


def test_team_patch_admin_can_preview_builtin_source(
    api_client, authenticated_user, mocker
):
    source = _create_builtin()
    client = _team_client(
        api_client,
        authenticated_user,
        mocker,
        {"patch_source-View"},
    )
    preview = mocker.patch(
        "apps.patch_mgmt.services.source_sync_service.SourceSyncService.preview_sync_candidates",
        return_value=[],
    )

    response = client.post(
        f"{PATCH_SOURCE_URL}{source.id}/preview_sync/",
        {"page": 1, "page_size": 20},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    preview.assert_called_once_with(source)


def test_team_patch_admin_ingests_builtin_source_into_current_team(
    api_client, authenticated_user, mocker
):
    source = _create_builtin()
    client = _team_client(
        api_client,
        authenticated_user,
        mocker,
        {"patch-Add"},
    )
    ingest = mocker.patch(
        "apps.patch_mgmt.services.source_sync_service.SourceSyncService.ingest_selected",
        return_value={"created": 1, "updated": 0, "skipped": 0, "total": 1},
    )

    response = client.post(
        f"{PATCH_SOURCE_URL}{source.id}/ingest/",
        {"keys": ["ELSA-2026:0001"]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    ingest.assert_called_once_with(
        source,
        ["ELSA-2026:0001"],
        severity_overrides={},
        team_id=1,
    )
