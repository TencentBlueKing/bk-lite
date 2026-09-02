"""监控 NATS 权限模块：按组织分页实例/策略/条件，以及模块列表分组。"""
import pytest

from apps.monitor.models.monitor_condition import MonitorCondition, MonitorConditionOrganization
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject, MonitorObjectType
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyOrganization
from apps.monitor.nats import permission as nats_perm

pytestmark = pytest.mark.django_db


def test_get_monitor_module_data_filters_by_org_and_rejects_unknown():
    obj = MonitorObject.objects.create(name="NatsPermObj", level="base")
    inst = MonitorInstance.objects.create(id="nats-inst-1", name="i1", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=7)
    other = MonitorInstance.objects.create(id="nats-inst-2", name="i2", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=other, organization=8)

    out = nats_perm.get_monitor_module_data("instance", obj.id, 1, 10, 7)
    assert out["count"] == 1
    assert out["items"] == [{"id": "nats-inst-1", "name": "i1"}]

    policy = MonitorPolicy.objects.create(monitor_object=obj, name="p-nats", algorithm="avg")
    PolicyOrganization.objects.create(policy=policy, organization=7)
    out = nats_perm.get_monitor_module_data("policy", obj.id, 1, 10, 7)
    assert out["count"] == 1
    assert out["items"] == [{"id": policy.id, "name": "p-nats"}]

    cond = MonitorCondition.objects.create(name="c-nats", condition={})
    MonitorConditionOrganization.objects.create(monitor_condition=cond, organization=7)
    out = nats_perm.get_monitor_module_data("condition", obj.id, 1, 10, 7)
    assert out["count"] == 1
    assert out["items"] == [{"id": cond.id, "name": "c-nats"}]

    with pytest.raises(ValueError, match="Invalid module type"):
        nats_perm.get_monitor_module_data("unknown", obj.id, 1, 10, 7)


def test_get_monitor_module_list_groups_objects_by_type():
    otype = MonitorObjectType.objects.create(id="host-nats-perm", name="Host")
    obj = MonitorObject.objects.create(name="NatsListObj", level="base", type=otype)
    out = nats_perm.get_monitor_module_list()
    assert out[0]["name"] == "instance"
    assert out[0]["display_name"] == "Instance"
    assert out[1]["name"] == "policy"
    assert out[2] == {"name": "condition", "display_name": "Condition", "children": []}
    host_group = next(item for item in out[0]["children"] if item["name"] == "host-nats-perm")
    assert host_group["display_name"] == "host-nats-perm"
    assert {"name": obj.id, "display_name": "NatsListObj"} in host_group["children"]
    assert out[1]["children"] == out[0]["children"]
