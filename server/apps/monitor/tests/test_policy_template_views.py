import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.monitor.models import MonitorObject, MonitorPlugin, PolicyTemplate
from apps.system_mgmt.models import Group

pytestmark = pytest.mark.django_db
BASE = "/api/v1/monitor/api/monitor_policy"


@pytest.fixture(autouse=True)
def template_permissions(mocker):
    team = Group.objects.create(name="TemplateViewTeam", parent_id=0)
    other_team = Group.objects.create(name="TemplateViewOtherTeam", parent_id=0)
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [team.id]},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        return_value={"result": True, "data": [team.id]},
    )
    mocker.patch(
        "apps.monitor.views.monitor_policy.get_permission_rules",
        return_value={"team": [team.id], "instance": []},
    )
    mocker.patch("apps.system_mgmt.middleware.error_log_middleware.write_error_log_async")
    return team, other_team


def _catalog():
    monitor_object = MonitorObject.objects.create(name="TemplateViewHost", level="base")
    plugin = MonitorPlugin.objects.create(name="TemplateViewPlugin", collector="Telegraf")
    plugin.monitor_object.add(monitor_object)
    return monitor_object, plugin


def test_save_list_and_delete_custom_template(api_client, template_permissions):
    team, _ = template_permissions
    api_client.cookies["current_team"] = str(team.id)
    monitor_object, plugin = _catalog()
    response = api_client.post(
        f"{BASE}/template/save/",
        {
            "monitor_object": monitor_object.id,
            "plugin": plugin.id,
            "name": "CPU 自定义模板",
            "config": {
                "name": "CPU 自定义模板",
                "alert_name": "CPU 告警",
                "query_condition": {"type": "pmq", "query": "up"},
                "schedule": {"type": "min", "value": 5},
                "organizations": [team.id],
                "source": {"type": "instance", "values": ["host-a"]},
            },
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    template = PolicyTemplate.objects.get(template_type="custom")
    assert template.organization == team.id
    assert "organizations" not in template.config
    assert "source" not in template.config

    listed = api_client.post(
        f"{BASE}/template/",
        {"monitor_object_name": monitor_object.name},
        format="json",
    )
    assert listed.status_code == 200
    assert listed.json()["data"][0]["template_type"] == "custom"

    deleted = api_client.post(
        f"{BASE}/template/bulk_delete/",
        {"keys": [f"custom:{template.id}"]},
        format="json",
    )
    assert deleted.status_code == 200
    assert not PolicyTemplate.objects.filter(id=template.id).exists()


def test_bulk_delete_rejects_builtin_template(api_client, template_permissions):
    team, _ = template_permissions
    api_client.cookies["current_team"] = str(team.id)
    monitor_object, plugin = _catalog()
    template = PolicyTemplate.objects.create(
        key="builtin:view-test",
        scope_key="builtin",
        template_type="builtin",
        monitor_object=monitor_object,
        plugin=plugin,
        name="内置模板",
        config={},
    )
    response = api_client.post(
        f"{BASE}/template/bulk_delete/",
        {"keys": [f"builtin:{template.id}"]},
        format="json",
    )
    assert response.status_code != 200
    assert PolicyTemplate.objects.filter(id=template.id).exists()


def test_bulk_delete_with_builtin_is_atomic_and_keeps_custom_template(api_client, template_permissions):
    team, _ = template_permissions
    api_client.cookies["current_team"] = str(team.id)
    monitor_object, plugin = _catalog()
    builtin = PolicyTemplate.objects.create(
        key="builtin:mixed-delete",
        scope_key="builtin",
        template_type="builtin",
        monitor_object=monitor_object,
        plugin=plugin,
        name="内置模板",
        config={},
    )
    custom = PolicyTemplate.objects.create(
        key="custom-mixed-delete",
        scope_key=f"custom:{team.id}",
        template_type="custom",
        organization=team.id,
        monitor_object=monitor_object,
        plugin=plugin,
        name="自定义模板",
        config={},
    )

    response = api_client.post(
        f"{BASE}/template/bulk_delete/",
        {"keys": [f"custom:{custom.id}", f"builtin:{builtin.id}"]},
        format="json",
    )

    assert response.status_code != 200
    assert PolicyTemplate.objects.filter(id__in=[builtin.id, custom.id]).count() == 2


def test_custom_templates_are_strictly_isolated_from_other_projects(api_client, template_permissions):
    team, other_team = template_permissions
    api_client.cookies["current_team"] = str(team.id)
    api_client.cookies["include_children"] = "1"
    monitor_object, plugin = _catalog()
    visible = PolicyTemplate.objects.create(
        key="custom-visible",
        scope_key=f"custom:{team.id}",
        template_type="custom",
        organization=team.id,
        monitor_object=monitor_object,
        plugin=plugin,
        name="当前项目模板",
        config={},
    )
    hidden = PolicyTemplate.objects.create(
        key="custom-hidden",
        scope_key=f"custom:{other_team.id}",
        template_type="custom",
        organization=other_team.id,
        monitor_object=monitor_object,
        plugin=plugin,
        name="子项目模板",
        config={},
    )

    listed = api_client.post(
        f"{BASE}/template/",
        {"monitor_object_name": monitor_object.name},
        format="json",
    )
    exported = api_client.post(
        f"{BASE}/template/export/",
        {"keys": [f"custom:{hidden.id}"]},
        format="json",
    )
    deleted = api_client.post(
        f"{BASE}/template/bulk_delete/",
        {"keys": [f"custom:{hidden.id}"]},
        format="json",
    )

    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()["data"]} == {visible.id}
    assert exported.status_code != 200
    assert deleted.status_code != 200
    assert PolicyTemplate.objects.filter(id=hidden.id, organization=other_team.id).exists()


def test_save_requires_current_team_operate_permission(api_client, mocker, template_permissions):
    team, _ = template_permissions
    api_client.cookies["current_team"] = str(team.id)
    monitor_object, plugin = _catalog()
    mocker.patch(
        "apps.monitor.views.monitor_policy.get_permission_rules",
        return_value={"team": [], "instance": []},
    )

    response = api_client.post(
        f"{BASE}/template/save/",
        {
            "monitor_object": monitor_object.id,
            "plugin": plugin.id,
            "name": "无权限模板",
            "config": {"query_condition": {"type": "pmq", "query": "up"}},
        },
        format="json",
    )

    assert response.status_code != 200
    assert not PolicyTemplate.objects.filter(name="无权限模板").exists()


def test_export_then_import_prompts_before_overwrite(api_client, template_permissions):
    team, _ = template_permissions
    api_client.cookies["current_team"] = str(team.id)
    monitor_object, plugin = _catalog()
    builtin = PolicyTemplate.objects.create(
        key="builtin:view-export",
        scope_key="builtin",
        template_type="builtin",
        monitor_object=monitor_object,
        plugin=plugin,
        name="可导出内置模板",
        config={"query_condition": {"type": "pmq", "query": "up"}},
    )
    exported = api_client.post(
        f"{BASE}/template/export/",
        {"keys": [f"builtin:{builtin.id}"]},
        format="json",
    )
    assert exported.status_code == 200
    assert exported["Content-Type"] == "application/zip"

    def upload(overwrite=False):
        return api_client.post(
            f"{BASE}/template/import/",
            {
                "file": SimpleUploadedFile(
                    "templates.zip",
                    exported.content,
                    content_type="application/zip",
                ),
                "overwrite": str(overwrite).lower(),
            },
            format="multipart",
        )

    first = upload()
    assert first.status_code == 200
    assert first.json()["data"]["imported_count"] == 1
    conflict = upload()
    assert conflict.json()["data"]["requires_overwrite"] is True
    overwritten = upload(overwrite=True)
    assert overwritten.json()["data"]["imported_count"] == 1
    assert PolicyTemplate.objects.filter(template_type="custom").count() == 1
    assert PolicyTemplate.objects.filter(id=builtin.id, template_type="builtin").exists()
