import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from apps.workflow_orchestration.models import Workflow
from apps.workflow_orchestration.services.builtin_workflows import (
    BUILTIN_LINUX_KEY,
    BUILTIN_WINDOWS_KEY,
    builtin_engine_name,
    ensure_builtin_health_workflows,
)
from apps.workflow_orchestration.views import WorkflowViewSet


def _request(factory, method, path, user, data=None):
    request = getattr(factory, method)(path, data=data, format="json")
    request.user = user
    request.COOKIES = {"current_team": "1"}
    return request


@pytest.fixture
def builtin_user(db):
    return get_user_model().objects.create(
        username="admin",
        domain="domain.com",
        password="x",
        is_superuser=True,
        group_list=[{"id": 1, "name": "Default"}],
    )


@pytest.mark.django_db
def test_ensure_builtin_health_workflows_are_idempotent(builtin_user, mocker):
    mocker.patch("apps.workflow_orchestration.services.builtin_workflows.ConductorClient").return_value
    mocker.patch(
        "apps.workflow_orchestration.services.builtin_workflows.seed_builtin_health_template_snapshot",
        side_effect=lambda fmt, team_id: {
            "object_key": f"workflow-orchestration/templates/demo/team-{team_id}/health.{fmt}",
            "format": fmt,
            "sha256": "a" * 64,
            "size": 128,
            "filename_prefix": f"health-{fmt}",
        },
    )
    mocker.patch("apps.workflow_orchestration.services.builtin_workflows.ensure_platform_atom")
    mocker.patch("apps.workflow_orchestration.services.builtin_workflows.sync_published_triggers")

    first = ensure_builtin_health_workflows(team_id=1, username=builtin_user.username, domain=builtin_user.domain)
    second = ensure_builtin_health_workflows(team_id=1, username=builtin_user.username, domain=builtin_user.domain)

    assert len(first) == 2
    assert {item.engine_name for item in first} == {
        builtin_engine_name(1, BUILTIN_WINDOWS_KEY),
        builtin_engine_name(1, BUILTIN_LINUX_KEY),
    }
    assert Workflow.objects.filter(is_builtin=True, team=[1]).count() == 2
    assert {item.pk for item in second} == {item.pk for item in first}
    assert all(not item.has_draft and item.enabled and item.current_version == 1 for item in second)


@pytest.mark.django_db
def test_builtin_workflow_rejects_delete_draft_and_publish(builtin_user, mocker):
    mocker.patch("apps.workflow_orchestration.services.builtin_workflows.ConductorClient").return_value
    mocker.patch(
        "apps.workflow_orchestration.services.builtin_workflows.seed_builtin_health_template_snapshot",
        side_effect=lambda fmt, team_id: {
            "object_key": f"workflow-orchestration/templates/demo/team-{team_id}/health.{fmt}",
            "format": fmt,
            "sha256": "b" * 64,
            "size": 64,
            "filename_prefix": f"health-{fmt}",
        },
    )
    mocker.patch("apps.workflow_orchestration.services.builtin_workflows.ensure_platform_atom")
    mocker.patch("apps.workflow_orchestration.services.builtin_workflows.sync_published_triggers")
    workflow = ensure_builtin_health_workflows(team_id=1, username=builtin_user.username)[0]
    factory = APIRequestFactory()

    destroy = WorkflowViewSet.as_view({"delete": "destroy"})
    draft = WorkflowViewSet.as_view({"patch": "partial_update"})
    publish = WorkflowViewSet.as_view({"post": "publish"})

    assert destroy(_request(factory, "delete", f"/workflows/{workflow.id}/", builtin_user), pk=workflow.id).status_code == 409
    assert (
        draft(
            _request(
                factory,
                "patch",
                f"/workflows/{workflow.id}/",
                builtin_user,
                {"name": "改名", "draft_revision": workflow.draft_revision},
            ),
            pk=workflow.id,
        ).status_code
        == 409
    )
    assert publish(_request(factory, "post", f"/workflows/{workflow.id}/publish/", builtin_user, {}), pk=workflow.id).status_code == 409
    assert Workflow.objects.filter(pk=workflow.pk, deleted_at__isnull=True, is_builtin=True).exists()
