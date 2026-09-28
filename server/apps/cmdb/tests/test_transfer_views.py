import json
from types import SimpleNamespace

from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.services.transfer_service import TransferService
from apps.cmdb.tests.test_transfer_service import submit
from apps.cmdb.views.transfer_task import TransferTaskViewSet
from apps.system_mgmt.models.user import User


def request_view(user, action, method="get", task_id=None, data=None):
    request = getattr(APIRequestFactory(), method)("/cmdb/api/transfer_tasks/", data=data or {}, format="json")
    force_authenticate(request, user=SimpleNamespace(username=user.username, domain=user.domain, is_authenticated=True))
    return TransferTaskViewSet.as_view({method: action})(request, **({"pk": str(task_id)} if task_id else {}))


def test_personal_list_hides_keys_and_cross_domain_tasks(transfer_owner):
    task = submit(transfer_owner)
    other = User.objects.create(username=transfer_owner.username, domain="other")
    response = request_view(transfer_owner, "list")
    data = json.loads(response.content)["data"]
    assert data["items"][0]["task_id"] == str(task.pk)
    assert "source_key" not in data["items"][0]
    assert "authorization" not in data["items"][0]
    response = request_view(other, "retrieve", task_id=task.pk)
    assert response.status_code == 404
    response = request_view(transfer_owner, "cancel", "post", task.pk)
    assert response.status_code == 200
    assert TransferService.get(transfer_owner, task.pk).status == "cancelled"
    assert request_view(transfer_owner, "destroy", "delete", task.pk).status_code == 200
    assert not TransferService.list(transfer_owner).exists()
