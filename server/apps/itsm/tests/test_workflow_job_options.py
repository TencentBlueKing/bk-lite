import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import RequestFactory


@pytest.mark.django_db
def test_options_limit_scope_and_only_expose_parameter_metadata():
    from apps.itsm.views.workflow_jobs import workflow_job_options
    from apps.job_mgmt.models import Script, Target

    request = RequestFactory().get("/")
    request.user = SimpleNamespace(domain="test", is_superuser=True, username="admin")
    request.COOKIES["current_team"] = "7"
    script = Script.objects.create(
        domain="test",
        team=[7],
        name="只读",
        params=[{"name": "size", "label": "规格", "default": "private", "type": "enum", "options": ["small", "medium"], "description": "计算资源规格"}],
    )
    Script.objects.create(domain="test", team=[8], name="其他组织")
    Script.objects.create(domain="other", team=[7], name="其他域")
    target = Target.objects.create(domain="test", team=[7], name="执行机", ip="127.0.0.1")
    with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value={"team": [7]}):
        data = json.loads(workflow_job_options(request).content)["data"]
    assert data == {
        "scripts": [
            {
                "id": script.pk,
                "name": "只读",
                "description": "",
                "params": [
                    {
                        "name": "size",
                        "label": "规格",
                        "is_required": False,
                        "type": "enum",
                        "options": ["small", "medium"],
                        "description": "计算资源规格",
                    }
                ],
            }
        ],
        "targets": [{"id": target.pk, "name": "执行机"}],
        "can_execute": True,
    }
    request.user.is_superuser = False
    request.user.permission = {"itsm": {"workflow-Edit"}}
    assert workflow_job_options(request).status_code == 403


@pytest.mark.django_db
def test_publish_replaces_client_binding_and_requires_matching_row_column():
    from apps.itsm.views.workflow_jobs import validate_job_bindings
    from apps.job_mgmt.models import Script, Target
    from apps.job_mgmt.services.template_revision import payload_hash, script_payload

    script = Script.objects.create(domain="test", team=[7], name="只读", params=[{"name": "cpu", "is_required": True}])
    target = Target.objects.create(domain="test", team=[7], name="执行机", ip="127.0.0.1")
    request = RequestFactory().post("/")
    request.user = SimpleNamespace(domain="test", is_superuser=True, username="publisher")
    request.COOKIES["current_team"] = "7"
    auto = {
        "kind": "job_template",
        "script_id": script.pk,
        "target_id": target.pk,
        "table_key": "vm",
        "params": {"cpu": "bad"},
        "binding": {"operator": "wrong"},
    }
    design = {"form_schema": {"fields": [{"key": "vm", "type": "table", "children": [{"key": "vcpus"}]}]}, "nodes": [{"type": "auto", "auto": auto}]}
    with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value={"team": [7]}):
        with pytest.raises(ValueError, match="同行"):
            validate_job_bindings(request, design)
        auto["params"]["cpu"] = "vcpus"
        validate_job_bindings(request, design)
        assert auto["binding"] == {"operator": "publisher", "team_id": 7, "script_hash": payload_hash(script_payload(script))}
        request.user.is_superuser = False
        request.user.permission = {"itsm": {"workflow-Publish"}}
        with pytest.raises(PermissionError):
            validate_job_bindings(request, design)


@pytest.mark.django_db
def test_integration_catalog_read_grants_do_not_require_execution_or_target_access():
    from apps.itsm.views.workflow_jobs import integration_job_catalog
    from apps.job_mgmt.models import Script, Target

    request = RequestFactory().get("/")
    request.user = SimpleNamespace(
        domain="test",
        username="reader",
        is_superuser=False,
        group_list=[{"id": 7}],
        permission={"itsm": {"data-View"}, "job": {"script_library-View"}},
    )
    request.COOKIES["current_team"] = "7"
    script = Script.objects.create(domain="test", team=[7], name="只读")
    target = Target.objects.create(domain="test", team=[7], name="执行机", ip="127.0.0.1")
    with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value={"team": [7]}):
        data = json.loads(integration_job_catalog(request).content)["data"]
        assert data == {"scripts": [{"id": script.pk, "name": "只读", "description": "", "params": []}], "targets": [], "can_execute": False}
        request.user.permission["job"].add("target-View")
        assert json.loads(integration_job_catalog(request).content)["data"]["targets"] == [{"id": target.pk, "name": "执行机"}]
        request.user.permission["job"].add("quick_exec-Add")
        assert json.loads(integration_job_catalog(request).content)["data"]["can_execute"] is True
        request.user.permission["itsm"] = set()
        assert integration_job_catalog(request).status_code == 403
