"""MonitorObjectService 补充方法规格测试。"""

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorInstanceOrganization
from apps.monitor.models.monitor_object import (
    MonitorObject,
    MonitorObjectType,
    MonitorInstance,
)
from apps.monitor.services.monitor_object import MonitorObjectService as S

pytestmark = pytest.mark.django_db


def _obj(name="MOSObj"):
    return MonitorObject.objects.create(name=name, level="base")


class TestValidateInstanceNameUnique:
    def test_new_name_conflict_raises(self):
        obj = _obj()
        MonitorInstance.objects.create(id="('h1',)", name="dup", monitor_object=obj)
        with pytest.raises(BaseAppException):
            S.validate_new_instance_name_unique(obj.id, "dup")

    def test_new_name_empty_ok(self):
        obj = _obj("MOSObj2")
        assert S.validate_new_instance_name_unique(obj.id, "") is None

    def test_update_same_name_ok(self):
        obj = _obj("MOSObj3")
        inst = MonitorInstance.objects.create(id="('h1',)", name="keep", monitor_object=obj)
        assert S.validate_update_instance_name_unique(inst, "keep") is None

    def test_update_to_conflicting_name_raises(self):
        obj = _obj("MOSObj4")
        MonitorInstance.objects.create(id="('h1',)", name="other", monitor_object=obj)
        inst = MonitorInstance.objects.create(id="('h2',)", name="me", monitor_object=obj)
        with pytest.raises(BaseAppException):
            S.validate_update_instance_name_unique(inst, "other")


class TestGenerateMonitorInstanceId:
    def test_creates_new_instance(self):
        obj = _obj("GMIObj")
        iid = S.generate_monitor_instance_id(obj.id, "host-a", 30)
        assert MonitorInstance.objects.filter(id=iid, name="host-a").exists()

    def test_reuses_existing_and_updates_interval(self):
        obj = _obj("GMIObj2")
        inst = MonitorInstance.objects.create(id="('h1',)", name="host-b", monitor_object=obj, interval=10)
        iid = S.generate_monitor_instance_id(obj.id, "host-b", 60)
        assert iid == "('h1',)"
        inst.refresh_from_db()
        assert inst.interval == 60


class TestCheckMonitorInstance:
    def test_existing_raises(self):
        obj = _obj("CMIObj")
        MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        with pytest.raises(BaseAppException):
            S.check_monitor_instance(obj.id, {"instance_id": "h1", "instance_name": "h1"})

    def test_not_existing_ok(self):
        obj = _obj("CMIObj2")
        assert S.check_monitor_instance(obj.id, {"instance_id": "new", "instance_name": "new"}) is None


class TestSetObjectOrder:
    def test_orders_objects_within_type(self):
        t = MonitorObjectType.objects.create(id="os", name="OS", order=0)
        a = MonitorObject.objects.create(name="Host", level="base", type=t, order=5)
        b = MonitorObject.objects.create(name="Switch", level="base", type=t, order=5)
        S.set_object_order([{"type": "os", "object_list": ["Switch", "Host"]}])
        a.refresh_from_db()
        b.refresh_from_db()
        assert b.order == 0  # Switch 第一
        assert a.order == 1  # Host 第二

    def test_orders_types_when_multiple(self):
        S.set_object_order([
            {"type": "type_x", "object_list": []},
            {"type": "type_y", "object_list": []},
        ])
        tx = MonitorObjectType.objects.get(id="type_x")
        ty = MonitorObjectType.objects.get(id="type_y")
        assert tx.order == 0 and ty.order == 1


class TestUpdateInstance:
    def test_missing_instance_raises(self):
        with pytest.raises(BaseAppException):
            S.update_instance("('missing',)", name="x")

    def test_updates_name_and_orgs(self):
        obj = _obj("UIObj")
        inst = MonitorInstance.objects.create(id="('h1',)", name="old", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=1)
        S.update_instance("('h1',)", name="newname", organizations=[2, 3])
        inst.refresh_from_db()
        assert inst.name == "newname"
        orgs = set(inst.monitorinstanceorganization_set.values_list("organization", flat=True))
        assert orgs == {2, 3}

    def test_updates_extra_fields(self):
        obj = _obj("UIObj2")
        MonitorInstance.objects.create(id="('h1',)", name="x", monitor_object=obj)
        S.update_instance("('h1',)", ip="10.0.0.1", cloud_region_id=2)
        inst = MonitorInstance.objects.get(id="('h1',)")
        assert inst.ip == "10.0.0.1"
        assert inst.cloud_region_id == 2


class TestOrganizationOps:
    def test_add_and_remove_and_set(self):
        obj = _obj("OrgOpsObj")
        MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        S.add_instances_organizations(["('h1',)"], [1, 2])
        assert MonitorInstanceOrganization.objects.filter(monitor_instance_id="('h1',)").count() == 2
        S.remove_instances_organizations(["('h1',)"], [1])
        assert not MonitorInstanceOrganization.objects.filter(
            monitor_instance_id="('h1',)", organization=1
        ).exists()
        S.set_instances_organizations(["('h1',)"], [9])
        orgs = set(
            MonitorInstanceOrganization.objects.filter(monitor_instance_id="('h1',)")
            .values_list("organization", flat=True)
        )
        assert orgs == {9}

    def test_noops_on_empty(self):
        # 空入参不报错
        assert S.add_instances_organizations([], [1]) is None
        assert S.remove_instances_organizations(["x"], []) is None
