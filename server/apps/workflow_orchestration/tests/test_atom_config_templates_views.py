import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.workflow_orchestration.models import AtomConfigTemplate, AtomDefinition
from apps.workflow_orchestration.views import AtomConfigTemplateViewSet


@pytest.fixture
def template_admin(db):
    return get_user_model().objects.create(username="template-admin", domain="example.com", is_superuser=True)


def _request(method, path, user, data=None, *, team=7):
    request = getattr(APIRequestFactory(), method)(path, data or {}, format="json")
    request.COOKIES["current_team"] = str(team)
    force_authenticate(request, user=user)
    return request


@pytest.fixture
def template_atom(db):
    return AtomDefinition.objects.create(
        key="custom.template-test",
        name="模板测试原子",
        category="测试",
        source_type=AtomDefinition.SourceType.PACKAGE,
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "url": {"type": "string", "title": "URL"},
                "token": {"type": "string", "sensitive": True},
                "nested": {
                    "type": "object",
                    "properties": {
                        "visible": {"type": "string"},
                        "password": {"type": "string", "sensitive": True},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    )


@pytest.mark.django_db
def test_atom_config_template_is_shared_inside_team_and_strips_sensitive_values(template_admin, template_atom):
    create = AtomConfigTemplateViewSet.as_view({"post": "create"})
    list_view = AtomConfigTemplateViewSet.as_view({"get": "list"})

    created = create(
        _request(
            "post",
            "/atom-config-templates/",
            template_admin,
            {
                "name": "巡检默认通知",
                "atom_key": template_atom.key,
                "parameters": {
                    "message": "${scan.output.result}",
                    "url": "https://example.com/health",
                    "token": "plain-secret",
                    "nested": {"visible": "keep", "password": "nested-secret"},
                },
            },
        )
    )

    assert created.status_code == 201
    assert created.data["organization_id"] == 7
    assert created.data["parameters"] == {
        "message": "${scan.output.result}",
        "url": "https://example.com/health",
        "nested": {"visible": "keep"},
    }
    stored = AtomConfigTemplate.objects.get(pk=created.data["id"])
    assert "plain-secret" not in str(stored.parameters)
    assert "nested-secret" not in str(stored.parameters)

    own_team = list_view(_request("get", f"/atom-config-templates/?atom_key={template_atom.key}", template_admin))
    assert own_team.status_code == 200
    assert [item["name"] for item in own_team.data["items"]] == ["巡检默认通知"]

    other_team = list_view(_request("get", f"/atom-config-templates/?atom_key={template_atom.key}", template_admin, team=8))
    assert other_team.status_code == 200
    assert other_team.data["items"] == []


@pytest.mark.django_db
def test_atom_config_template_list_requires_atom_and_mutations_stay_tenant_scoped(template_admin, template_atom):
    template = AtomConfigTemplate.objects.create(
        organization_id=7,
        atom_key=template_atom.key,
        name="旧名称",
        parameters={"message": "saved"},
        created_by=template_admin.username,
        updated_by=template_admin.username,
    )
    list_view = AtomConfigTemplateViewSet.as_view({"get": "list"})
    update = AtomConfigTemplateViewSet.as_view({"patch": "partial_update"})
    destroy = AtomConfigTemplateViewSet.as_view({"delete": "destroy"})

    missing_atom = list_view(_request("get", "/atom-config-templates/", template_admin))
    assert missing_atom.status_code == 400

    renamed = update(
        _request("patch", f"/atom-config-templates/{template.pk}/", template_admin, {"name": "新名称"}),
        pk=template.pk,
    )
    assert renamed.status_code == 200
    assert renamed.data["name"] == "新名称"

    cross_team_delete = destroy(
        _request("delete", f"/atom-config-templates/{template.pk}/", template_admin, team=8),
        pk=template.pk,
    )
    assert cross_team_delete.status_code == 404
    assert AtomConfigTemplate.objects.filter(pk=template.pk).exists()

    deleted = destroy(
        _request("delete", f"/atom-config-templates/{template.pk}/", template_admin),
        pk=template.pk,
    )
    assert deleted.status_code == 204
    assert not AtomConfigTemplate.objects.filter(pk=template.pk).exists()
