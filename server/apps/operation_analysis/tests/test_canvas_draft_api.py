import json

import pytest
import yaml
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.operation_analysis.models.canvas_draft import CanvasDraftCheckpoint
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Dashboard, Directory, Screen
from apps.operation_analysis.views import view as view_module
from apps.operation_analysis.views.canvas_draft_view import CanvasDraftViewSet


def _request(method, path, user, data=None, team="1"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    request.COOKIES["current_team"] = str(team)
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _superuser(user):
    user.is_superuser = True
    return user


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _call(actions, method, user, *, resource_type, pk, data=None, team="1"):
    request = _request(method, f"/canvas_draft/{resource_type}/{pk}/", user, data=data, team=team)
    response = CanvasDraftViewSet.as_view(actions)(request, resource_type=resource_type, pk=str(pk))
    return response, _render(response)


def _call_checkpoint(actions, method, user, *, resource_type, pk, checkpoint_id, data=None, team="1"):
    request = _request(
        method,
        f"/canvas_draft/{resource_type}/{pk}/checkpoints/{checkpoint_id}/",
        user,
        data=data,
        team=team,
    )
    response = CanvasDraftViewSet.as_view(actions)(
        request,
        resource_type=resource_type,
        pk=str(pk),
        checkpoint_id=str(checkpoint_id),
    )
    return response, _render(response)


def _dashboard(**over):
    directory = Directory.objects.create(name="draft-dir", groups=[1], created_by="testuser")
    fields = dict(
        name="draft-dash",
        groups=[1],
        directory=directory,
        view_sets=[],
        created_by="testuser",
    )
    fields.update(over)
    return Dashboard.objects.create(**fields)


def _yaml_doc(**over):
    doc = {
        "type": "dashboard",
        "name": "draft-dash",
        "view_sets": [
            {
                "i": "w1",
                "x": 0,
                "y": 0,
                "w": 4,
                "h": 3,
                "valueConfig": {"chartType": "line"},
            }
        ],
    }
    doc.update(over)
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)


@pytest.mark.django_db
def test_get_yaml_projects_formal_without_checkpoint(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()

    response, payload = _call({"get": "yaml"}, "get", user, resource_type="dashboard", pk=dashboard.id)

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["revision"] == 0
    assert yaml.safe_load(payload["data"]["yaml"])["type"] == "dashboard"
    assert CanvasDraftCheckpoint.objects.count() == 0


@pytest.mark.django_db
def test_get_yaml_uses_latest_checkpoint_revision(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()
    _call(
        {"post": "checkpoints"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"payload": {"view_sets": [], "name": "frame-1"}},
    )
    checkpoint = CanvasDraftCheckpoint.objects.get(resource_id=dashboard.id, username="testuser")

    response, payload = _call({"get": "yaml"}, "get", user, resource_type="dashboard", pk=dashboard.id)

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["revision"] == checkpoint.id
    assert yaml.safe_load(payload["data"]["yaml"])["name"] == "frame-1"


@pytest.mark.django_db
def test_checkpoint_enters_history_and_trims_to_20(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()
    for index in range(21):
        response, payload = _call(
            {"post": "checkpoints"},
            "post",
            user,
            resource_type="dashboard",
            pk=dashboard.id,
            data={"payload": {"view_sets": [], "name": f"frame-{index}"}},
        )
        assert response.status_code == status.HTTP_200_OK
        assert payload["data"]["id"] > 0

    assert CanvasDraftCheckpoint.objects.filter(resource_id=dashboard.id, username="testuser").count() == 20
    assert not CanvasDraftCheckpoint.objects.filter(payload__name="frame-0").exists()


@pytest.mark.django_db
def test_restore_returns_payload_without_writing_new_checkpoint(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()
    _call(
        {"post": "checkpoints"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"payload": {"view_sets": [{"i": "w1", "x": 0, "y": 0, "w": 4, "h": 3}], "name": "frame-1"}},
    )
    checkpoint = CanvasDraftCheckpoint.objects.get(resource_id=dashboard.id, username="testuser")
    count_before = CanvasDraftCheckpoint.objects.count()

    response, payload = _call(
        {"post": "restore_checkpoint"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"checkpoint_id": checkpoint.id},
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["payload"]["name"] == "frame-1"
    assert CanvasDraftCheckpoint.objects.count() == count_before


@pytest.mark.django_db
def test_update_checkpoint_label(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()
    _call(
        {"post": "checkpoints"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"payload": {"view_sets": [], "name": "draft-dash"}},
    )
    checkpoint = CanvasDraftCheckpoint.objects.get(resource_id=dashboard.id, username="testuser")

    response, payload = _call_checkpoint(
        {"patch": "update_checkpoint"},
        "patch",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        checkpoint_id=checkpoint.id,
        data={"label": "  CPU 趋势图  "},
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["label"] == "CPU 趋势图"
    checkpoint.refresh_from_db()
    assert checkpoint.label == "CPU 趋势图"

    response, payload = _call(
        {"get": "history"},
        "get",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
    )
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"][0]["label"] == "CPU 趋势图"


@pytest.mark.django_db
def test_update_checkpoint_label_clears_to_empty(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()
    _call(
        {"post": "checkpoints"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"payload": {"view_sets": [], "name": "draft-dash"}},
    )
    checkpoint = CanvasDraftCheckpoint.objects.get(resource_id=dashboard.id, username="testuser")
    _call_checkpoint(
        {"patch": "update_checkpoint"},
        "patch",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        checkpoint_id=checkpoint.id,
        data={"label": "临时名"},
    )

    response, payload = _call_checkpoint(
        {"patch": "update_checkpoint"},
        "patch",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        checkpoint_id=checkpoint.id,
        data={"label": "   "},
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["label"] == ""


@pytest.mark.django_db
def test_update_checkpoint_label_rejects_non_string(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()
    _call(
        {"post": "checkpoints"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"payload": {"view_sets": [], "name": "draft-dash"}},
    )
    checkpoint = CanvasDraftCheckpoint.objects.get(resource_id=dashboard.id, username="testuser")

    response, payload = _call_checkpoint(
        {"patch": "update_checkpoint"},
        "patch",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        checkpoint_id=checkpoint.id,
        data={"label": 123},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["data"]["errors"] == [
        {"field": "label", "message": "label 必须是字符串"},
    ]
    checkpoint.refresh_from_db()
    assert checkpoint.label == ""


@pytest.mark.django_db
def test_other_team_canvas_returns_403(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()

    response, _payload = _call(
        {"get": "yaml"},
        "get",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        team="99",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert CanvasDraftCheckpoint.objects.count() == 0


@pytest.mark.django_db
def test_builtin_draft_returns_403(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard(name="builtin-dash", is_build_in=True, build_in_key="builtin-dash")

    response, _payload = _call({"get": "yaml"}, "get", user, resource_type="dashboard", pk=dashboard.id)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_numeric_datasource_id_in_yaml_is_rejected(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()
    doc = yaml.safe_load(_yaml_doc())
    doc["view_sets"][0]["valueConfig"]["dataSource"] = 12

    response, payload = _call(
        {"post": "preview"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"yaml": yaml.safe_dump(doc, allow_unicode=True)},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["data"]["errors"][0]["code"] == "unresolved_datasource"
    assert CanvasDraftCheckpoint.objects.count() == 0


@pytest.mark.django_db
def test_broken_filter_binding_is_rejected(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()
    doc = yaml.safe_load(_yaml_doc())
    doc["view_sets"][0]["valueConfig"]["filterBindings"] = {"missing-filter": True}

    response, payload = _call(
        {"post": "preview"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"yaml": yaml.safe_dump(doc, allow_unicode=True)},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["data"]["errors"][0]["code"] == "broken_filter_binding"
    assert CanvasDraftCheckpoint.objects.count() == 0


@pytest.mark.django_db
def test_screen_checkpoint_accepts_flat_item_layout(authenticated_user):
    user = _superuser(authenticated_user)
    directory = Directory.objects.create(name="draft-screen-dir", groups=[1], created_by="testuser")
    screen = Screen.objects.create(
        name="draft-screen",
        groups=[1],
        directory=directory,
        view_sets={
            "viewport": {"width": 1920, "height": 1080, "theme": "screen-dark"},
            "items": [],
            "decorations": {},
            "filters": [],
        },
        created_by="testuser",
    )

    response, payload = _call(
        {"post": "checkpoints"},
        "post",
        user,
        resource_type="screen",
        pk=screen.id,
        data={
            "payload": {
                "view_sets": {
                    "viewport": {"width": 1920, "height": 1080, "theme": "screen-dark"},
                    "decorations": {"showTitle": False, "showClock": False},
                    "filters": [],
                    "items": [
                        {
                            "id": "w1",
                            "type": "widget",
                            "chartType": "line",
                            "title": "趋势",
                            "x": 48,
                            "y": 96,
                            "w": 480,
                            "h": 240,
                            "zIndex": 1,
                            "valueConfig": {"chartType": "line"},
                        }
                    ],
                }
            }
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["id"] > 0
    assert CanvasDraftCheckpoint.objects.filter(resource_id=screen.id, username="testuser").count() == 1


@pytest.mark.django_db
def test_unresolved_business_key_does_not_create_datasource_or_checkpoint(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()
    doc = _yaml_doc()
    loaded = yaml.safe_load(doc)
    loaded["view_sets"][0]["valueConfig"]["dataSource"] = "missing::query"

    response, payload = _call(
        {"post": "preview"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"yaml": yaml.safe_dump(loaded, allow_unicode=True)},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["data"]["errors"][0]["code"] == "unresolved_datasource"
    assert CanvasDraftCheckpoint.objects.count() == 0
    assert not DataSourceAPIModel.objects.filter(name="missing").exists()


@pytest.mark.django_db
def test_package_yaml_is_rejected(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()

    response, payload = _call(
        {"post": "preview"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"yaml": "meta: {}\ndatasources: []\ntype: dashboard\nname: draft-dash\nview_sets: []\n"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["data"]["errors"][0]["code"] == "package_document"


@pytest.mark.django_db
def test_unknown_widget_type_is_rejected(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()

    response, payload = _call(
        {"post": "preview"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"yaml": _yaml_doc(view_sets=[{"i": "w1", "x": 0, "y": 0, "w": 4, "h": 3, "valueConfig": {"chartType": "nope"}}])},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["data"]["errors"][0]["code"] == "unknown_component_type"


@pytest.mark.django_db
def test_preview_does_not_write_checkpoint(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()

    response, payload = _call(
        {"post": "preview"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"yaml": _yaml_doc()},
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["payload"]["view_sets"][0]["i"] == "w1"
    assert CanvasDraftCheckpoint.objects.count() == 0


@pytest.mark.django_db
def test_user_b_cannot_read_user_a_history(authenticated_user):
    user_a = _superuser(authenticated_user)
    dashboard = _dashboard()
    _call(
        {"post": "checkpoints"},
        "post",
        user_a,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"payload": {"view_sets": [{"i": "w1", "x": 0, "y": 0, "w": 4, "h": 3}], "name": "frame-a"}},
    )

    user_b = User.objects.create_user(
        username="otheruser",
        password="testpass123",
        domain="domain.com",
        group_list=[{"id": 1, "name": "Default Team"}],
        roles=["admin"],
    )
    user_b.is_superuser = True

    response, payload = _call({"get": "history"}, "get", user_b, resource_type="dashboard", pk=dashboard.id)

    assert response.status_code == status.HTTP_200_OK
    assert payload["data"] == []
    assert CanvasDraftCheckpoint.objects.filter(username="testuser").count() == 1


@pytest.mark.django_db
def test_checkpoint_accepts_long_username(authenticated_user):
    user = _superuser(authenticated_user)
    user.username = "u" * 40
    user.save(update_fields=["username"])
    dashboard = _dashboard()

    response, payload = _call(
        {"post": "checkpoints"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"payload": {"view_sets": [], "name": "long-user-frame"}},
    )

    assert response.status_code == status.HTTP_200_OK
    checkpoint = CanvasDraftCheckpoint.objects.get(id=payload["data"]["id"])
    assert checkpoint.username == "u" * 40


@pytest.mark.django_db
def test_deleting_canvas_cascades_history(authenticated_user):
    user = _superuser(authenticated_user)
    dashboard = _dashboard()
    _call(
        {"post": "checkpoints"},
        "post",
        user,
        resource_type="dashboard",
        pk=dashboard.id,
        data={"payload": {"view_sets": []}},
    )

    request = _request("delete", f"/dashboard/{dashboard.id}/", user)
    response = view_module.DashboardModelViewSet.as_view({"delete": "destroy"})(request, pk=str(dashboard.id))

    assert response.status_code in {status.HTTP_200_OK, status.HTTP_204_NO_CONTENT}
    assert CanvasDraftCheckpoint.objects.count() == 0
