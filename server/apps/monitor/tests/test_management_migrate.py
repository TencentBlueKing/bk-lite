"""management commands / migrate services 规格测试。"""

import json
from io import StringIO

import pytest
from django.core.management import call_command

from apps.monitor.models import Metric
from apps.monitor.models.monitor_metrics import MetricGroup
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.management.services.default_order_migrate import migrate_default_order
from apps.monitor.management.services import plugin_migrate as pm

pytestmark = pytest.mark.django_db


class TestBackfillMetricInstanceIdKeys:
    def test_backfills_object_and_metric_keys(self):
        obj = MonitorObject.objects.create(name="BFObj", level="base", instance_id_keys=[])
        plugin = MonitorPlugin.objects.create(name="BFPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        metric = Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group,
            name="m", instance_id_keys=[],
        )
        out = StringIO()
        call_command("backfill_metric_instance_id_keys", stdout=out)
        obj.refresh_from_db()
        metric.refresh_from_db()
        assert obj.instance_id_keys == ["instance_id"]
        assert metric.instance_id_keys == ["instance_id"]
        assert "monitor_object updated" in out.getvalue()

    def test_dry_run_does_not_write(self):
        obj = MonitorObject.objects.create(name="BFObj2", level="base", instance_id_keys=[])
        out = StringIO()
        call_command("backfill_metric_instance_id_keys", "--dry-run", stdout=out)
        obj.refresh_from_db()
        # dry-run 不写库
        assert obj.instance_id_keys == []
        assert "dry_run=True" in out.getvalue()


class TestMigrateDefaultOrder:
    def test_initializes_order_999(self, mocker):
        mocker.patch(
            "apps.monitor.constants.monitor_object.MonitorObjConstants.DEFAULT_OBJ_ORDER",
            [{"type": "os", "name_list": ["Host"]}],
        )
        t = MonitorObjectType.objects.create(id="os", name="操作系统", order=999)
        obj = MonitorObject.objects.create(name="Host", level="base", type=t, order=999)
        migrate_default_order()
        t.refresh_from_db()
        obj.refresh_from_db()
        assert t.order == 0
        assert obj.order == 0


class TestPluginMigrateHelpers:
    def test_clean_identity_value(self):
        assert pm._clean_identity_value(None) == ""
        assert pm._clean_identity_value("  x  ") == "x"
        assert pm._clean_identity_value(123) == "123"

    def test_resolve_plugin_identity_prefers_metadata(self, mocker):
        mocker.patch(
            "apps.monitor.management.services.plugin_migrate.extract_plugin_path_info",
            return_value=("PathCollector", "path_type"),
        )
        data = {"collector": "MetaCollector", "collect_type": "meta_type"}
        collector, collect_type = pm._resolve_plugin_identity("/x/y", data)
        assert collector == "MetaCollector"
        assert collect_type == "meta_type"
        assert data["collector"] == "MetaCollector"

    def test_resolve_plugin_identity_falls_back_to_path(self, mocker):
        mocker.patch(
            "apps.monitor.management.services.plugin_migrate.extract_plugin_path_info",
            return_value=("PathCollector", "path_type"),
        )
        data = {}
        collector, collect_type = pm._resolve_plugin_identity("/x/y", data)
        assert collector == "PathCollector"
        assert collect_type == "path_type"

    def test_validate_template_identity_raises_on_mismatch(self, tmp_path):
        plugin_dir = tmp_path
        (plugin_dir / "tpl.j2").write_text('collect_type = "wrong_type"\n', encoding="utf-8")
        with pytest.raises(pm.PluginIdentityValidationError):
            pm._validate_template_identity(plugin_dir, "right_type")

    def test_validate_template_identity_ok(self, tmp_path):
        (tmp_path / "tpl.j2").write_text('collect_type = "snmp"\n', encoding="utf-8")
        # 一致 → 不抛错
        assert pm._validate_template_identity(tmp_path, "snmp") is None

    def test_validate_ui_identity_mismatch(self, tmp_path):
        (tmp_path / "UI.json").write_text(
            json.dumps({"collector": "A", "collect_type": "x"}), encoding="utf-8"
        )
        with pytest.raises(pm.PluginIdentityValidationError):
            pm._validate_ui_identity(tmp_path, "B", "x")

    def test_validate_ui_identity_missing_file(self, tmp_path):
        # 无 UI.json → 直接返回
        assert pm._validate_ui_identity(tmp_path, "A", "x") is None


class TestCollectFileSupplementaryIndicators:
    def test_simple_object(self):
        supp = {}
        pm._collect_file_supplementary_indicators(
            {"name": "Host", "supplementary_indicators": ["cpu", "mem"]}, supp,
        )
        assert supp["Host"] == {"cpu", "mem"}

    def test_compound_object(self):
        supp = {}
        pm._collect_file_supplementary_indicators(
            {"is_compound_object": True, "objects": [
                {"name": "Pod", "supplementary_indicators": ["a"]},
                {"name": "Node", "supplementary_indicators": ["b"]},
            ]},
            supp,
        )
        assert supp["Pod"] == {"a"} and supp["Node"] == {"b"}

    def test_no_name_skipped(self):
        supp = {}
        pm._collect_file_supplementary_indicators({"supplementary_indicators": ["x"]}, supp)
        assert supp == {}


class TestReconcileSupplementaryIndicators:
    def test_empty_map_noop(self):
        assert pm._reconcile_supplementary_indicators({}) == 0

    def test_updates_changed_objects(self):
        obj = MonitorObject.objects.create(name="ReconObj", level="base", supplementary_indicators=["old"])
        count = pm._reconcile_supplementary_indicators({"ReconObj": {"new1", "new2"}})
        assert count == 1
        obj.refresh_from_db()
        assert obj.supplementary_indicators == ["new1", "new2"]

    def test_no_change_returns_zero(self):
        MonitorObject.objects.create(name="ReconObj2", level="base", supplementary_indicators=["a", "b"])
        count = pm._reconcile_supplementary_indicators({"ReconObj2": {"a", "b"}})
        assert count == 0
