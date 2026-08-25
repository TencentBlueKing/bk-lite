"""stringList → string + multiple 导入落库 / 导出防御 / 预检 warning。"""

import yaml

from apps.operation_analysis.constants.import_export import YAML_SCHEMA_VERSION, ConflictAction, ImportExportWarningCode, ObjectType
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument
from apps.operation_analysis.services.import_export.export_service import ExportService
from apps.operation_analysis.services.import_export.import_service import ImportService
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService
from apps.operation_analysis.services.string_param_multiple_migrate import migrate_param_items, migrate_unified_filter_definitions


def _doc(**sections):
    data = {"meta": {"schema_version": YAML_SCHEMA_VERSION}}
    data.update(sections)
    return YAMLDocument(**data)


def _service(doc, **over):
    kwargs = dict(
        doc=doc,
        target_directory_id=None,
        conflict_decisions={},
        secret_supplements={},
        created_by="tester",
        updated_by="tester",
        groups=[1],
    )
    kwargs.update(over)
    return ImportService(**kwargs)


def _legacy_param(**over):
    base = {
        "name": "instance_ids",
        "alias_name": "主机",
        "type": "stringList",
        "filterType": "filter",
        "value": [],
        "inputConfig": {
            "control": "select",
            "picker": "table",
            "optionsSource": {
                "type": "dynamic",
                "sourceRef": {"type": "rest_api", "value": "monitor/get_host_instance_list"},
                "valueField": "instance_id",
                "labelField": "display_name",
            },
        },
    }
    base.update(over)
    return base


def test_migrate_param_preserves_picker_and_dynamic_source():
    migrated, warnings = migrate_param_items([_legacy_param()])
    assert warnings == []
    assert migrated[0]["type"] == "string"
    assert migrated[0]["inputConfig"]["multiple"] is True
    assert migrated[0]["inputConfig"]["picker"] == "table"
    assert migrated[0]["inputConfig"]["optionsSource"]["sourceRef"]["value"] == "monitor/get_host_instance_list"


def test_migrate_param_component_switch_conflict():
    param = _legacy_param(
        inputConfig={
            "control": "select",
            "componentSwitch": True,
            "optionsSource": {"type": "static", "staticItems": [{"label": "a", "value": "a"}]},
        }
    )
    migrated, warnings = migrate_param_items([param])
    assert migrated[0]["inputConfig"]["multiple"] is True
    assert "componentSwitch" not in migrated[0]["inputConfig"]
    assert any(item["code"] == "string_list_component_switch_conflict" for item in warnings)


def test_migrate_dual_id_order_independent():
    list_side = {
        "id": "instance_ids__stringList",
        "key": "instance_ids",
        "name": "主机多选",
        "type": "stringList",
        "order": 1,
        "enabled": True,
        "inputConfig": {
            "control": "select",
            "optionsSource": {"type": "static", "staticItems": [{"label": "a", "value": "a"}]},
        },
    }
    scalar_side = {
        "id": "instance_ids__string",
        "key": "instance_ids",
        "name": "主机单选",
        "type": "string",
        "order": 0,
        "enabled": False,
        "inputConfig": {"control": "input"},
    }
    first, first_warnings = migrate_unified_filter_definitions([scalar_side, list_side])
    second, second_warnings = migrate_unified_filter_definitions([list_side, scalar_side])
    assert first == second
    assert [w["code"] for w in first_warnings] == [w["code"] for w in second_warnings]
    assert first[0]["id"] == "instance_ids__string"
    assert first[0]["inputConfig"]["multiple"] is True


def test_precheck_emits_string_list_migration_warnings(monkeypatch):
    monkeypatch.setattr(PrecheckService, "identify_conflicts", lambda *_args, **_kwargs: [])
    document = {
        "meta": {"schema_version": YAML_SCHEMA_VERSION, "object_counts": {"datasources": 1, "dashboards": 1}},
        "datasources": [
            {
                "key": "host::monitor/query",
                "name": "host",
                "rest_api": "monitor/query",
                "params": [
                    _legacy_param(
                        inputConfig={
                            "control": "select",
                            "componentSwitch": True,
                            "optionsSource": {"type": "static", "staticItems": []},
                        }
                    )
                ],
            }
        ],
        "dashboards": [
            {
                "key": "dashboard::host",
                "name": "host-board",
                "desc": "",
                "other": {},
                "view_sets": [],
                "filters": [
                    {
                        "id": "instance_ids__string",
                        "key": "instance_ids",
                        "name": "主机单选",
                        "type": "string",
                        "order": 0,
                        "enabled": True,
                        "inputConfig": {"control": "input"},
                    },
                    {
                        "id": "instance_ids__stringList",
                        "key": "instance_ids",
                        "name": "主机多选",
                        "type": "stringList",
                        "order": 1,
                        "enabled": True,
                        "inputConfig": {
                            "control": "select",
                            "optionsSource": {"type": "static", "staticItems": [{"label": "a", "value": "a"}]},
                        },
                    },
                ],
            }
        ],
    }
    result = PrecheckService.precheck(yaml.safe_dump(document))
    codes = [item["code"] for item in result["warnings"]]
    assert ImportExportWarningCode.STRING_LIST_MIGRATION in codes
    messages = "\n".join(item["message"] for item in result["warnings"])
    assert "componentSwitch" in messages
    assert "同时存在 string 与 stringList" in messages


def test_import_persists_normalized_string_multiple_and_export_stays_normalized(db):
    directory = Directory.objects.create(name="import-root", groups=[1], created_by="tester")
    doc = _doc(
        datasources=[
            {
                "key": "host::monitor/query",
                "name": "host-ds",
                "rest_api": "monitor/query",
                "desc": "",
                "params": [_legacy_param()],
                "tags": [],
                "chart_type": [],
                "field_schema": [],
                "namespace_keys": [],
            }
        ],
        dashboards=[
            {
                "key": "dashboard::host",
                "name": "host-board",
                "desc": "",
                "other": {},
                "view_sets": [
                    {
                        "id": "w1",
                        "itemType": "widget",
                        "valueConfig": {
                            "chartType": "single",
                            "dataSource": "host::monitor/query",
                            "filterBindings": {"instance_ids__stringList": True},
                            "dataSourceParams": [_legacy_param()],
                        },
                    }
                ],
                "filters": [
                    {
                        "id": "instance_ids__stringList",
                        "key": "instance_ids",
                        "name": "主机",
                        "type": "stringList",
                        "order": 0,
                        "enabled": True,
                        "inputConfig": {
                            "control": "select",
                            "picker": "table",
                            "optionsSource": {
                                "type": "dynamic",
                                "sourceRef": {"type": "rest_api", "value": "monitor/get_host_instance_list"},
                                "valueField": "instance_id",
                                "labelField": "display_name",
                            },
                        },
                    }
                ],
            }
        ],
    )

    result = _service(doc, target_directory_id=directory.id).execute()
    assert result["success"] is True

    ds = DataSourceAPIModel.objects.get(name="host-ds")
    assert ds.params[0]["type"] == "string"
    assert ds.params[0]["inputConfig"]["multiple"] is True
    assert ds.params[0]["inputConfig"]["picker"] == "table"

    dashboard = Dashboard.objects.get(name="host-board")
    assert len(dashboard.filters) == 1
    assert dashboard.filters[0]["id"] == "instance_ids__string"
    assert dashboard.filters[0]["type"] == "string"
    assert dashboard.filters[0]["inputConfig"]["multiple"] is True
    assert dashboard.filters[0]["inputConfig"]["picker"] == "table"

    widget = dashboard.view_sets[0]
    assert widget["valueConfig"]["filterBindings"] == {"instance_ids__string": True}
    assert widget["valueConfig"]["dataSourceParams"][0]["type"] == "string"
    assert widget["valueConfig"]["dataSourceParams"][0]["inputConfig"]["multiple"] is True

    exported = ExportService.convert_canvas_to_yaml(
        dashboard,
        ObjectType.DASHBOARD,
        {ds.id: "host::monitor/query"},
        {},
    )
    assert exported["filters"][0]["type"] == "string"
    assert exported["filters"][0]["inputConfig"]["multiple"] is True
    assert exported["view_sets"][0]["valueConfig"]["filterBindings"] == {"instance_ids__string": True}
    assert "stringList" not in yaml.safe_dump(exported)

    ds_yaml = ExportService.convert_datasource_to_yaml(ds)
    assert ds_yaml["params"][0]["type"] == "string"
    assert ds_yaml["params"][0]["inputConfig"]["multiple"] is True

    again = _service(
        doc,
        target_directory_id=directory.id,
        conflict_decisions={
            "dashboard::host": ConflictAction.OVERWRITE.value,
            "host::monitor/query": ConflictAction.OVERWRITE.value,
        },
    ).execute()
    assert again["success"] is True
    dashboard.refresh_from_db()
    assert dashboard.filters[0]["type"] == "string"
    assert dashboard.filters[0]["id"] == "instance_ids__string"
    widget = dashboard.view_sets[0]
    assert widget["valueConfig"]["filterBindings"] == {"instance_ids__string": True}
    assert set(widget["valueConfig"]["filterBindings"].keys()) == {"instance_ids__string"}

    exported_again = ExportService.convert_canvas_to_yaml(
        dashboard,
        ObjectType.DASHBOARD,
        {ds.id: "host::monitor/query"},
        {},
    )
    assert exported_again["view_sets"][0]["valueConfig"]["filterBindings"] == {"instance_ids__string": True}
    assert yaml.safe_dump(exported_again["view_sets"][0]["valueConfig"]["filterBindings"]) == yaml.safe_dump(
        exported["view_sets"][0]["valueConfig"]["filterBindings"]
    )


def test_overwrite_import_merges_dual_bindings_without_duplicates(db):
    directory = Directory.objects.create(name="import-dual-bindings", groups=[1], created_by="tester")
    doc = _doc(
        datasources=[
            {
                "key": "host::monitor/query",
                "name": "host-ds-dual",
                "rest_api": "monitor/query",
                "desc": "",
                "params": [_legacy_param(name="instance_ids")],
                "tags": [],
                "chart_type": [],
                "field_schema": [],
                "namespace_keys": [],
            }
        ],
        dashboards=[
            {
                "key": "dashboard::dual-bindings",
                "name": "dual-bindings-board",
                "desc": "",
                "other": {},
                "view_sets": [
                    {
                        "id": "w1",
                        "itemType": "widget",
                        "valueConfig": {
                            "chartType": "single",
                            "dataSource": "host::monitor/query",
                            "filterBindings": {
                                "instance_ids__stringList": False,
                                "instance_ids__string": True,
                            },
                            "dataSourceParams": [_legacy_param(name="instance_ids")],
                        },
                    }
                ],
                "filters": [
                    {
                        "id": "instance_ids__stringList",
                        "key": "instance_ids",
                        "name": "主机多选",
                        "type": "stringList",
                        "order": 1,
                        "enabled": True,
                        "inputConfig": {
                            "control": "select",
                            "optionsSource": {"type": "static", "staticItems": []},
                        },
                    },
                    {
                        "id": "instance_ids__string",
                        "key": "instance_ids",
                        "name": "主机单选",
                        "type": "string",
                        "order": 0,
                        "enabled": False,
                        "inputConfig": {"control": "input"},
                    },
                ],
            }
        ],
    )

    first = _service(doc, target_directory_id=directory.id).execute()
    assert first["success"] is True
    dashboard = Dashboard.objects.get(name="dual-bindings-board")
    first_bindings = dashboard.view_sets[0]["valueConfig"]["filterBindings"]
    assert first_bindings == {"instance_ids__string": True}
    assert len(first_bindings) == 1

    first_export = ExportService.convert_canvas_to_yaml(
        dashboard,
        ObjectType.DASHBOARD,
        {DataSourceAPIModel.objects.get(name="host-ds-dual").id: "host::monitor/query"},
        {},
    )

    second = _service(
        doc,
        target_directory_id=directory.id,
        conflict_decisions={
            "dashboard::dual-bindings": ConflictAction.OVERWRITE.value,
            "host::monitor/query": ConflictAction.OVERWRITE.value,
        },
    ).execute()
    assert second["success"] is True
    dashboard.refresh_from_db()
    second_bindings = dashboard.view_sets[0]["valueConfig"]["filterBindings"]
    assert second_bindings == {"instance_ids__string": True}
    assert len(second_bindings) == 1

    second_export = ExportService.convert_canvas_to_yaml(
        dashboard,
        ObjectType.DASHBOARD,
        {DataSourceAPIModel.objects.get(name="host-ds-dual").id: "host::monitor/query"},
        {},
    )
    assert second_export["view_sets"][0]["valueConfig"]["filterBindings"] == first_export["view_sets"][0]["valueConfig"]["filterBindings"]
