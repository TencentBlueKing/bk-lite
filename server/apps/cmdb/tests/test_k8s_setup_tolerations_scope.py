import json
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.views.k8s_setup import K8sSetupViewSet

pytestmark = pytest.mark.django_db

CLUSTER_ID = "audit-cluster-b"
ORIGINAL_TOLERATIONS = [{"key": "dedicated", "effect": "NoSchedule", "value": "db"}]
WRITTEN_TOLERATIONS = [{"key": "workload", "effect": "NoExecute"}]


class _CloudRegion:
    def get_cloud_region_public_config(self, cloud_region_id):
        return {"NODE_SERVER_URL": "https://cloud-region.example"}


def _user():
    return SimpleNamespace(
        username="bob",
        is_superuser=False,
        is_authenticated=True,
        is_active=True,
        permission={"cmdb": {"auto_collection-Execute"}},
        group_list=[{"id": 1, "name": "Org 1"}],
        group_tree=[],
        roles=[],
        locale="en",
    )


def _task(name, team, tolerations=None):
    params = {"collector_cluster_id": CLUSTER_ID}
    if tolerations is not None:
        params["tolerations"] = tolerations
    return CollectModels.objects.create(
        name=name,
        task_type=CollectPluginTypes.K8S,
        driver_type=CollectDriverTypes.PROTOCOL,
        model_id="k8s",
        cycle_value_type="cycle",
        team=team,
        params=params,
    )


def _install(data, current_team):
    request = APIRequestFactory().post(
        "/api/v1/cmdb/api/k8s_setup/install_command/",
        data=data,
        format="json",
    )
    request.COOKIES["current_team"] = str(current_team)
    force_authenticate(request, user=_user())
    return K8sSetupViewSet.as_view({"post": "install_command"})(request)


def _payload(**extra):
    data = {"collector_cluster_id": CLUSTER_ID, "cloud_region_id": 9}
    data.update(extra)
    return data


def _body(response):
    return json.loads(response.content)


@pytest.fixture(autouse=True)
def _fake_cloud_and_empty_rules(monkeypatch):
    monkeypatch.setattr("apps.cmdb.views.collect.get_permission_rules", lambda *args, **kwargs: {})
    monkeypatch.setattr("apps.rpc.node_mgmt.NodeMgmt", lambda: _CloudRegion())
    monkeypatch.setattr(
        "apps.cmdb.services.k8s_setup.InfraService.generate_install_token",
        lambda *args, **kwargs: "scoped-test-token",
    )


def _assert_command_returned(response):
    body = _body(response)
    assert response.status_code == 200
    assert body["result"] is True
    assert body["data"]["token"] == "scoped-test-token"
    assert body["data"]["command"]


def test_other_org_empty_tolerations_stay_put_until_current_team_matches():
    task = _task("org-2-k8s", team=[2], tolerations=ORIGINAL_TOLERATIONS)

    denied = _install(_payload(tolerations=[]), current_team=1)

    _assert_command_returned(denied)
    task.refresh_from_db()
    assert task.params["tolerations"] == ORIGINAL_TOLERATIONS

    allowed = _install(_payload(tolerations=[]), current_team=2)

    _assert_command_returned(allowed)
    task.refresh_from_db()
    assert task.params["tolerations"] == []


def test_null_removes_tolerations_key_on_the_authorized_task():
    task = _task("org-2-null", team=[2], tolerations=ORIGINAL_TOLERATIONS)

    response = _install(_payload(tolerations=None), current_team=2)

    _assert_command_returned(response)
    task.refresh_from_db()
    assert "tolerations" not in task.params
    assert task.params["collector_cluster_id"] == CLUSTER_ID


def test_nonempty_tolerations_are_written_to_the_authorized_task():
    task = _task("org-2-write", team=[2], tolerations=ORIGINAL_TOLERATIONS)

    response = _install(_payload(tolerations=WRITTEN_TOLERATIONS), current_team=2)

    _assert_command_returned(response)
    task.refresh_from_db()
    assert task.params["tolerations"] == WRITTEN_TOLERATIONS


def test_duplicate_cluster_id_in_the_same_org_is_not_rewritten():
    first = _task("org-2-dup-a", team=[2], tolerations=ORIGINAL_TOLERATIONS)
    second = _task(
        "org-2-dup-b",
        team=[2],
        tolerations=[{"key": "keep", "effect": "NoSchedule"}],
    )

    response = _install(_payload(tolerations=[]), current_team=2)

    _assert_command_returned(response)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.params["tolerations"] == ORIGINAL_TOLERATIONS
    assert second.params["tolerations"] == [{"key": "keep", "effect": "NoSchedule"}]


def test_request_without_tolerations_leaves_stored_value():
    task = _task("org-2-omit", team=[2], tolerations=ORIGINAL_TOLERATIONS)

    response = _install(_payload(), current_team=2)

    _assert_command_returned(response)
    task.refresh_from_db()
    assert task.params["tolerations"] == ORIGINAL_TOLERATIONS
