"""补丁源、补丁、基线和目标的删除契约。"""

import pytest
from rest_framework import status

from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType, OSType
from apps.patch_mgmt.models import (
    GovernanceTask,
    GovernanceTaskHost,
    Patch,
    PatchSource,
    PatchTarget,
)


BASE = "/api/v1/patch_mgmt/api"


@pytest.mark.django_db
def test_deleting_custom_source_only_detaches_patches(su_client):
    source = PatchSource.objects.create(name="custom", source_type="apt", team=[1])
    patch = Patch.objects.create(title="openssl", os_type=OSType.LINUX, team=[1])
    patch.sources.add(source)

    response = su_client.delete(f"{BASE}/patch_source/{source.id}/")

    assert response.status_code == status.HTTP_200_OK
    assert Patch.objects.filter(pk=patch.id).exists()
    assert not patch.sources.filter(pk=source.id).exists()


@pytest.mark.django_db
def test_source_being_synchronized_cannot_be_deleted(su_client):
    source = PatchSource.objects.create(
        name="syncing", source_type="apt", sync_in_progress=True, team=[1]
    )

    response = su_client.delete(f"{BASE}/patch_source/{source.id}/")

    assert response.status_code == status.HTTP_409_CONFLICT
    assert PatchSource.objects.filter(pk=source.id).exists()


@pytest.mark.django_db
def test_patch_referenced_by_another_patch_cannot_be_deleted(su_client):
    dependency = Patch.objects.create(
        title="dependency", os_type=OSType.LINUX, team=[1]
    )
    Patch.objects.create(
        title="dependent",
        os_type=OSType.LINUX,
        dependency_ids=[dependency.id],
        team=[1],
    )

    response = su_client.delete(f"{BASE}/patch/{dependency.id}/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert Patch.objects.filter(pk=dependency.id).exists()


@pytest.mark.django_db
def test_same_batch_can_delete_patch_and_its_dependent(su_client):
    dependency = Patch.objects.create(
        title="dependency", os_type=OSType.LINUX, team=[1]
    )
    dependent = Patch.objects.create(
        title="dependent",
        os_type=OSType.LINUX,
        dependency_ids=[dependency.id],
        team=[1],
    )

    response = su_client.post(
        f"{BASE}/patch/batch_delete/",
        {"ids": [dependency.id, dependent.id]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert not Patch.objects.filter(pk__in=[dependency.id, dependent.id]).exists()


@pytest.mark.django_db
def test_target_delete_trims_mixed_task_and_deletes_empty_task(su_client):
    removed = PatchTarget.objects.create(name="removed", ip="10.0.1.1", team=[1])
    retained = PatchTarget.objects.create(name="retained", ip="10.0.1.2", team=[1])
    mixed = GovernanceTask.objects.create(
        name="mixed",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[removed.id, retained.id],
        risk_snapshot=[
            {"id": "removed", "host_id": removed.id, "patch_id": 1},
            {"id": "retained", "host_id": retained.id, "patch_id": 2},
        ],
        result_snapshot=[
            {"host_id": removed.id, "patch_id": 1},
            {"host_id": retained.id, "patch_id": 2},
        ],
        patch_list=[1, 2],
        team=[1],
    )
    empty = GovernanceTask.objects.create(
        name="empty",
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[removed.id],
        risk_snapshot=[{"id": "removed", "host_id": removed.id, "patch_id": 1}],
        patch_list=[1],
        team=[1],
    )
    for task, target in ((mixed, removed), (mixed, retained), (empty, removed)):
        GovernanceTaskHost.objects.create(
            task=task,
            target_id=target.id,
            target_name=target.name,
            stage="completed",
        )

    response = su_client.delete(f"{BASE}/patch_target/{removed.id}/")

    assert response.status_code == status.HTTP_200_OK
    mixed.refresh_from_db()
    assert mixed.target_list == [retained.id]
    assert [item["host_id"] for item in mixed.risk_snapshot] == [retained.id]
    assert [item["host_id"] for item in mixed.result_snapshot] == [retained.id]
    assert mixed.patch_list == [2]
    assert list(mixed.host_results.values_list("target_id", flat=True)) == [
        retained.id
    ]
    assert not GovernanceTask.objects.filter(pk=empty.id).exists()
