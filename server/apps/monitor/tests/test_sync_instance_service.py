"""SyncInstance 规格测试。

聚焦 VM 指标 → 监控实例的增/恢复/标记不活跃/物理删除的 DB 副作用。
唯一外部边界 VictoriaMetricsAPI mock，返回真实形态 VM 结果。
"""

from types import SimpleNamespace

import pytest

from apps.monitor.models.monitor_object import (
    MonitorObject,
    MonitorInstance,
    MonitorInstanceOrganization,
)
from apps.monitor.tasks.services.sync_instance import SyncInstance

pytestmark = pytest.mark.django_db


def _vm_result(*items):
    return {"data": {"result": list(items)}}


def _make_obj():
    return MonitorObject.objects.create(
        name="SyncHost", level="base",
        default_metric="any({}) by (instance_id)",
        instance_id_keys=["instance_id"],
    )


class TestParseOrganizationId:
    def test_valid_int_string(self):
        assert SyncInstance.parse_organization_id({"metric": {"organization_id": "12"}}) == 12

    def test_none_or_empty(self):
        assert SyncInstance.parse_organization_id({"metric": {"organization_id": None}}) is None
        assert SyncInstance.parse_organization_id({"metric": {"organization_id": ""}}) is None
        assert SyncInstance.parse_organization_id({"metric": {}}) is None

    def test_non_numeric(self):
        assert SyncInstance.parse_organization_id({"metric": {"organization_id": "abc"}}) is None


class TestBuildOrganizationRelations:
    def test_skips_none_org(self):
        m = {
            "('h1',)": {"organization_id": 5},
            "('h2',)": {"organization_id": None},
        }
        rels = SyncInstance.build_organization_relations(["('h1',)", "('h2',)"], m)
        assert len(rels) == 1
        assert rels[0].monitor_instance_id == "('h1',)"
        assert rels[0].organization == 5


class TestGetInstanceMapByMetrics:
    def test_builds_map_from_vm(self, mocker):
        _make_obj()
        vm = mocker.patch("apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI")
        vm.return_value.query.return_value = _vm_result(
            {"metric": {"instance_id": "h1", "organization_id": "3"}},
        )
        svc = SyncInstance()
        result = svc.get_instance_map_by_metrics()
        assert "('h1',)" in result
        entry = result["('h1',)"]
        assert entry["name"] == "h1"
        assert entry["auto"] is True
        assert entry["organization_id"] == 3


class TestSyncMonitorInstances:
    def test_adds_new_instances(self, mocker):
        obj = _make_obj()
        vm = mocker.patch("apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI")
        vm.return_value.query.return_value = _vm_result(
            {"metric": {"instance_id": "h1", "organization_id": "3"}},
        )
        SyncInstance().run()
        inst = MonitorInstance.objects.get(id="('h1',)")
        assert inst.auto is True and inst.is_deleted is False and inst.is_active is True
        assert MonitorInstanceOrganization.objects.filter(monitor_instance_id="('h1',)", organization=3).exists()

    def test_recovers_soft_deleted_instance(self, mocker):
        obj = _make_obj()
        MonitorInstance.objects.create(
            id="('h1',)", name="h1", monitor_object=obj, auto=True, is_deleted=True,
        )
        vm = mocker.patch("apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI")
        vm.return_value.query.return_value = _vm_result(
            {"metric": {"instance_id": "h1"}},
        )
        SyncInstance().run()
        inst = MonitorInstance.objects.get(id="('h1',)")
        assert inst.is_deleted is False
        assert inst.is_active is True

    def test_marks_missing_instance_inactive(self, mocker):
        obj = _make_obj()
        MonitorInstance.objects.create(
            id="('gone',)", name="gone", monitor_object=obj, auto=True,
            is_deleted=False, is_active=True,
        )
        vm = mocker.patch("apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI")
        vm.return_value.query.return_value = _vm_result()  # VM 中无任何实例
        SyncInstance().run()
        inst = MonitorInstance.objects.get(id="('gone',)")
        assert inst.is_active is False

    def test_deletes_continuous_inactive(self, mocker):
        obj = _make_obj()
        # 已经 is_active=False（上周期不活跃），本周期 VM 仍无 → 连续两周期 → 物理删除
        MonitorInstance.objects.create(
            id="('dead',)", name="dead", monitor_object=obj, auto=True,
            is_deleted=False, is_active=False,
        )
        vm = mocker.patch("apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI")
        vm.return_value.query.return_value = _vm_result()
        SyncInstance().run()
        assert not MonitorInstance.objects.filter(id="('dead',)").exists()
