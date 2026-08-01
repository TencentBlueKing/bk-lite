import io
import zipfile
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction

from apps.monitor.models import Metric, MetricGroup, MonitorObject, MonitorPlugin, PolicyTemplate
from apps.monitor.services.policy import PolicyService


pytestmark = pytest.mark.django_db


def _catalog():
    monitor_object = MonitorObject.objects.create(name="TemplateHost", level="base")
    plugin = MonitorPlugin.objects.create(name="TemplatePlugin", collector="Telegraf")
    plugin.monitor_object.add(monitor_object)
    return monitor_object, plugin


def _document(names):
    return {
        "object": "TemplateHost",
        "plugin": "TemplatePlugin",
        "templates": [{"name": name, "metric_name": name.lower()} for name in names],
    }


def _user():
    return SimpleNamespace(username="tester", domain="example.com")


def test_builtin_sync_is_idempotent_and_never_touches_custom_templates():
    monitor_object, plugin = _catalog()
    custom = PolicyTemplate.objects.create(
        key="custom-key",
        scope_key="custom:7",
        template_type="custom",
        organization=7,
        monitor_object=monitor_object,
        plugin=plugin,
        name="CPU",
        config={"threshold": []},
    )

    first = PolicyService.sync_builtin_policy_templates([_document(["CPU", "Memory"])])
    second = PolicyService.sync_builtin_policy_templates([_document(["CPU"])])

    assert first["created_count"] == 2
    assert second["created_count"] == 0
    assert PolicyTemplate.objects.filter(template_type="builtin").values_list("name", flat=True).get() == "CPU"
    assert PolicyTemplate.objects.get(id=custom.id).template_type == "custom"


def test_builtin_and_custom_with_same_name_can_coexist():
    monitor_object, plugin = _catalog()
    PolicyService.sync_builtin_policy_templates([_document(["CPU"])])
    PolicyTemplate.objects.create(
        key="custom-key",
        scope_key="custom:7",
        template_type="custom",
        organization=7,
        monitor_object=monitor_object,
        plugin=plugin,
        name="CPU",
        config={},
    )

    templates = PolicyService.get_policy_templates("TemplateHost", organization=7)
    assert {item["template_type"] for item in templates} == {"builtin", "custom"}


def test_custom_template_requires_project_but_builtin_must_not_have_one():
    monitor_object, plugin = _catalog()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PolicyTemplate.objects.create(
                key="bad-custom",
                scope_key="custom:missing",
                template_type="custom",
                organization=None,
                monitor_object=monitor_object,
                plugin=plugin,
                name="bad",
                config={},
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PolicyTemplate.objects.create(
                key="bad-builtin",
                scope_key="custom:7",
                template_type="builtin",
                organization=None,
                monitor_object=monitor_object,
                plugin=plugin,
                name="bad builtin",
                config={},
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PolicyTemplate.objects.create(
                key="bad-custom-scope",
                scope_key="custom:8",
                template_type="custom",
                organization=7,
                monitor_object=monitor_object,
                plugin=plugin,
                name="bad custom scope",
                config={},
            )


def test_export_import_prompts_then_overwrites_custom_only():
    monitor_object, plugin = _catalog()
    builtin = PolicyTemplate.objects.create(
        key="builtin:cpu",
        scope_key="builtin",
        template_type="builtin",
        monitor_object=monitor_object,
        plugin=plugin,
        name="CPU",
        config={"threshold": [{"level": "warning", "method": ">", "value": 80}]},
    )
    archive = PolicyService.export_archive([f"builtin:{builtin.id}"], organization=7)

    first = PolicyService.import_archive(archive, organization=7, user=_user())
    assert first["imported_count"] == 1
    custom = PolicyTemplate.objects.get(template_type="custom")
    assert custom.name == builtin.name

    combined = PolicyService.export_archive(
        [f"builtin:{builtin.id}", f"custom:{custom.id}"],
        organization=7,
    )
    with zipfile.ZipFile(combined) as exported:
        assert len([name for name in exported.namelist() if name.startswith("templates/")]) == 1
    combined.seek(0)
    assert PolicyService.import_archive(combined, organization=8, user=_user())["imported_count"] == 1

    archive.seek(0)
    conflict = PolicyService.import_archive(archive, organization=7, user=_user())
    assert conflict["requires_overwrite"] is True
    assert PolicyTemplate.objects.filter(template_type="custom", organization=7).count() == 1

    archive.seek(0)
    result = PolicyService.import_archive(archive, organization=7, user=_user(), overwrite=True)
    assert result["imported_count"] == 1
    assert PolicyTemplate.objects.filter(template_type="custom", organization=7).count() == 1
    assert PolicyTemplate.objects.get(id=builtin.id).template_type == "builtin"


def test_import_rejects_path_traversal():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../manifest.json", "{}")
    buffer.seek(0)
    with pytest.raises(Exception, match="非法路径"):
        PolicyService.import_archive(buffer, organization=7, user=_user())


def test_import_rejects_oversized_manifest_file():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", b"x" * (2 * 1024 * 1024 + 1))
    buffer.seek(0)
    with pytest.raises(Exception, match="单个文件"):
        PolicyService.import_archive(buffer, organization=7, user=_user())


def test_formula_config_is_stored_portably_and_resolved_for_runtime():
    monitor_object, plugin = _catalog()
    group = MetricGroup.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        name="system",
    )
    cpu = Metric.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        metric_group=group,
        name="cpu_usage",
    )
    memory = Metric.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        metric_group=group,
        name="memory_usage",
    )
    config = {
        "organizations": [7],
        "source": {"type": "instance", "values": ["host-a"]},
        "notice_type_ids": [9],
        "collect_type": plugin.id,
        "schedule": {"type": "min", "value": 5},
        "query_condition": {
            "type": "formula",
            "result_name": "资源压力",
            "expression": "$A + $B",
            "queries": [
                {"ref": "A", "metric_id": cpu.id, "group_algorithm": "avg", "group_by": ["instance_id"]},
                {"ref": "B", "metric_id": memory.id, "group_algorithm": "avg", "group_by": ["instance_id"]},
            ],
        },
    }

    portable = PolicyService.portable_config(config)
    assert "organizations" not in portable
    assert "source" not in portable
    assert "notice_type_ids" not in portable
    assert "collect_type" not in portable
    assert [item["metric_name"] for item in portable["query_condition"]["queries"]] == [
        "cpu_usage",
        "memory_usage",
    ]

    runtime = PolicyService._runtime_query_condition(
        portable["query_condition"], monitor_object
    )
    assert [item["metric_id"] for item in runtime["queries"]] == [cpu.id, memory.id]
