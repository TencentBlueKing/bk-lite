import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.workflow.models import Workflow
from apps.workflow.views import WorkflowViewSet


def _user(username, permissions):
    user = get_user_model().objects.create(username=username, domain="example.com")
    user.group_list = [{"id": 7, "name": "Current"}]
    user.group_tree = []
    user.permission = {"workflow": set(permissions)}
    return user


def _request(method, path, user, data=None):
    request = getattr(APIRequestFactory(), method)(path, data or {}, format="json")
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=user)
    return request


@pytest.fixture
def catalog(db, mocker):
    mocker.patch(
        "apps.workflow.permissions.get_permission_rules",
        return_value={"team": [7], "instance": []},
    )
    custom = Workflow.objects.create(name="custom", team=[7], definition={})
    builtin = Workflow.objects.create(name="builtin", team=[7], definition={}, is_builtin=True)
    return custom, builtin


@pytest.mark.django_db
def test_catalog_list_and_retrieve_follow_the_requested_menu(catalog):
    custom, builtin = catalog
    market_user = _user("market-reader", ["workflow_market-View"])
    workflow_user = _user("workflow-reader", ["workflow-View"])
    list_view = WorkflowViewSet.as_view({"get": "list"})
    retrieve = WorkflowViewSet.as_view({"get": "retrieve"})

    denied_custom = list_view(_request("get", "/workflows/?is_builtin=false", market_user))
    denied_builtin = list_view(_request("get", "/workflows/?is_builtin=true", workflow_user))
    market_rows = list_view(_request("get", "/workflows/?is_builtin=true", market_user))
    workflow_rows = list_view(_request("get", "/workflows/", workflow_user))
    denied_builtin_detail = retrieve(_request("get", f"/workflows/{builtin.id}/", workflow_user), pk=builtin.id)
    denied_custom_detail = retrieve(_request("get", f"/workflows/{custom.id}/", market_user), pk=custom.id)

    assert denied_custom.status_code == 403
    assert denied_builtin.status_code == 403
    assert [item["id"] for item in market_rows.data["items"]] == [builtin.id]
    assert [item["id"] for item in workflow_rows.data["items"]] == [custom.id]
    assert denied_builtin_detail.status_code == 403
    assert denied_custom_detail.status_code == 403


@pytest.mark.django_db
def test_duplicate_uses_the_source_catalog_add_permission(catalog):
    custom, builtin = catalog
    market_user = _user("market-copier", ["workflow_market-View", "workflow_market-Add"])
    workflow_user = _user("workflow-copier", ["workflow-View", "workflow-Add"])
    duplicate = WorkflowViewSet.as_view({"post": "duplicate"})

    denied_builtin = duplicate(_request("post", f"/workflows/{builtin.id}/duplicate/", workflow_user), pk=builtin.id)
    denied_custom = duplicate(_request("post", f"/workflows/{custom.id}/duplicate/", market_user), pk=custom.id)

    assert denied_builtin.status_code == 403
    assert denied_custom.status_code == 403
