from types import SimpleNamespace

import pytest

from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
from apps.node_mgmt.models.sidecar import CloudRegion, Node
from apps.node_mgmt.services.installer import InstallerService

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _user(username, domain="domain.com", *, is_superuser=False):
    return SimpleNamespace(username=username, domain=domain, is_superuser=is_superuser)


def _legacy_task(created_by, domain="domain.com"):
    region = CloudRegion.objects.create(name=f"cr-ctrl-retry-{created_by or 'unknown'}")
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="waiting",
        package_version_id=1,
        created_by=created_by,
        domain=domain,
    )
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.13",
        os="linux",
        port=22,
        username="root",
        password="x",
        node_name="legacy",
        organizations=[1],
        status="waiting",
    )
    return task, task_node


def _query(task, request_user):
    return InstallerService.install_controller_nodes(
        task.id,
        authorized_nodes=Node.objects.none(),
        scope=SimpleNamespace(
            data_team_ids=frozenset({1}),
            username=request_user.username,
            domain=request_user.domain,
            is_superuser=request_user.is_superuser,
        ),
    )


def test_controller_task_node_query_requires_legacy_owner_and_domain():
    task, task_node = _legacy_task("owner")

    denied = _query(task, _user("other"))
    same_username_other_domain = _query(task, _user("owner", "other.com"))
    owner = _query(task, _user("owner"))
    superuser = _query(task, _user("admin", is_superuser=True))

    assert denied == []
    assert same_username_other_domain == []
    assert [item["task_node_id"] for item in owner] == [task_node.id]
    assert [item["task_node_id"] for item in superuser] == [task_node.id]


def test_controller_task_node_query_limits_unknown_legacy_owner_to_superuser():
    task, task_node = _legacy_task("")

    denied = _query(task, _user("ordinary"))
    superuser = _query(task, _user("admin", is_superuser=True))

    assert denied == []
    assert [item["task_node_id"] for item in superuser] == [task_node.id]
