import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection

from apps.itsm.models import Service, Workflow, WorkflowVersion


@pytest.mark.django_db
def test_retired_auto_action_disables_only_affected_service():
    module = importlib.import_module("apps.itsm.migrations.0030_disable_unsupported_auto_actions")
    services = []
    for kind in ("retired_action", "job_template"):
        workflow = Workflow.objects.create(key=f"action_{kind}", name=kind)
        version = WorkflowVersion.objects.create(
            workflow=workflow,
            version_no=1,
            is_published=True,
            design={"nodes": [{"id": "execute", "type": "auto", "auto": {"kind": kind}}]},
        )
        workflow.current_version = version
        workflow.save(update_fields=["current_version"])
        services.append(Service.objects.create(workflow=workflow, name=kind, is_enabled=True))

    module.disable_unsupported_auto_actions(apps, SimpleNamespace(connection=connection))

    assert [Service.objects.get(pk=service.pk).is_enabled for service in services] == [False, True]


@pytest.mark.django_db
def test_removed_platform_api_disables_only_affected_service(monkeypatch):
    module = importlib.import_module("apps.itsm.migrations.0031_disable_services_with_missing_platform_api")
    from apps.core.openapi.registry import default_registry

    monkeypatch.setattr(default_registry, "find", lambda service, path, method: None if path == "removed" else object())
    services = []
    for path in ("itsm/removed", "itsm/available"):
        workflow = Workflow.objects.create(key=f"platform_{path[-7:]}", name=path)
        version = WorkflowVersion.objects.create(
            workflow=workflow,
            version_no=1,
            is_published=True,
            design={
                "form_schema": {
                    "fields": [
                        {
                            "key": "rows",
                            "type": "table",
                            "children": [{"key": "choice", "fetch": {"snapshot": {"kind": "api", "config": {"path": path, "method": "GET"}}}}],
                        }
                    ]
                }
            },
        )
        workflow.current_version = version
        workflow.save(update_fields=["current_version"])
        services.append(Service.objects.create(workflow=workflow, name=path, is_enabled=True))

    module.disable_services_with_missing_platform_api(apps, SimpleNamespace(connection=connection))

    assert [Service.objects.get(pk=service.pk).is_enabled for service in services] == [False, True]
