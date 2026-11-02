import pytest

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collect_reconcile import create_reconcile, load_write_context, task_collected_fields, update_reconcile
from apps.core.exceptions.base_app_exception import ValidationAppException

pytestmark = pytest.mark.django_db


class _Request:
    class user:
        username = "windy"
        domain = "example.com"


def _task(name, task_type="protocol", model_id="mysql"):
    return CollectModels.objects.create(
        name=name,
        task_type=task_type,
        model_id=model_id,
        cycle_value_type="cycle",
        team=[1],
        params={},
    )


@pytest.fixture
def visible(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.collect_reconcile._visible_tasks", lambda request: CollectModels.objects.all())


def test_field_order_uses_converted_model_fields(visible, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.collect_reconcile._custom_conversion_fields",
        lambda model_id: ["port", "db_size"],
    )
    builtin = _task("builtin")
    builtin.params = {"collect_fields": ["not_a_model_field"]}
    builtin.save(update_fields=["params"])
    custom = _task("custom", "custom_script")
    payload = create_reconcile(_Request(), name="mysql-ab", model_id="mysql", task_ids=[builtin.id, custom.id])
    orders = {item["field"]: [task["id"] for task in item["tasks"]] for item in payload["field_orders"]}
    assert orders["port"] == [builtin.id, custom.id]
    assert orders["ip_addr"] == [builtin.id]
    assert orders["db_size"] == [custom.id]
    assert "not_a_model_field" not in orders
    assert "proa" not in orders
    assert load_write_context(custom.id)["member_order"] == [str(builtin.id), str(custom.id)]


def test_two_network_tasks_share_the_model_field_not_the_snmp_name(visible):
    task_a = _task("A", CollectPluginTypes.SNMP, "network")
    task_b = _task("B", CollectPluginTypes.SNMP, "network")
    payload = create_reconcile(_Request(), name="net", model_id="network", task_ids=[task_a.id, task_b.id])
    orders = {item["field"]: [task["id"] for task in item["tasks"]] for item in payload["field_orders"]}
    assert orders["sys_desc"] == [task_a.id, task_b.id]
    assert "sysdescr" not in orders
    assert "mac" not in orders


def test_tasks_of_different_models_cannot_form_one_reconcile(visible):
    network = _task("sw", CollectPluginTypes.SNMP, "network")
    mysql = _task("db")
    with pytest.raises(ValidationAppException, match="模型"):
        create_reconcile(_Request(), name="mixed", model_id="network", task_ids=[network.id, mysql.id])


def test_task_cannot_join_a_second_reconcile_or_an_unsupported_type(visible):
    task_a = _task("A")
    task_b = _task("B", "custom_script")
    create_reconcile(_Request(), name="one", model_id="mysql", task_ids=[task_a.id, task_b.id])
    task_c = _task("C")
    with pytest.raises(ValidationAppException):
        create_reconcile(_Request(), name="two", model_id="mysql", task_ids=[task_b.id, task_c.id])
    cloud = _task("cloud", CollectPluginTypes.CLOUD, "aliyun")
    other = _task("other-cloud", CollectPluginTypes.CLOUD, "aliyun")
    with pytest.raises(ValidationAppException):
        create_reconcile(_Request(), name="cloud", model_id="aliyun", task_ids=[cloud.id, other.id])
    vc = _task("vc", CollectPluginTypes.CUSTOM_SCRIPT, "vmware_vc")
    vc2 = _task("vc2", CollectPluginTypes.CUSTOM_SCRIPT, "vmware_vc")
    with pytest.raises(ValidationAppException):
        create_reconcile(_Request(), name="vc", model_id="vmware_vc", task_ids=[vc.id, vc2.id])
    docker = _task("docker", CollectPluginTypes.MIDDLEWARE, "docker")
    docker2 = _task("docker2", CollectPluginTypes.MIDDLEWARE, "docker")
    with pytest.raises(ValidationAppException, match="容器"):
        create_reconcile(_Request(), name="docker", model_id="docker", task_ids=[docker.id, docker2.id])


def test_switch_snmp_task_uses_the_same_device_model_fields():
    task = _task("sw", CollectPluginTypes.SNMP, "switch")
    fields = task_collected_fields(task)
    assert "sys_desc" in fields
    assert "sysdescr" not in fields


def test_custom_network_task_uses_the_device_field_table(monkeypatch):
    def boom(model_id):
        raise AssertionError(model_id)

    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr", boom)
    task = _task("custom-net", CollectPluginTypes.CUSTOM_SCRIPT, "network")
    fields = task_collected_fields(task)
    assert "sys_desc" in fields
    assert "soid" in fields
    assert "sysdescr" not in fields
    assert "inst_name" not in fields
    assert "mac" not in fields


def test_custom_and_snmp_network_share_sys_desc(visible):
    custom = _task("custom-net", CollectPluginTypes.CUSTOM_SCRIPT, "network")
    builtin = _task("builtin-net", CollectPluginTypes.SNMP, "network")
    payload = create_reconcile(_Request(), name="net-custom", model_id="network", task_ids=[custom.id, builtin.id])
    orders = {item["field"]: [task["id"] for task in item["tasks"]] for item in payload["field_orders"]}
    assert orders["sys_desc"] == [custom.id, builtin.id]
    assert "sysdescr" not in orders


def test_snmp_task_uses_device_model_fields_not_source_names():
    task = _task("sw", CollectPluginTypes.SNMP, "network")
    fields = task_collected_fields(task)
    assert "sys_desc" in fields
    assert "soid" in fields
    assert "sysdescr" not in fields
    assert "sysobjectid" not in fields
    assert "inst_name" not in fields
    assert "mac" not in fields


def test_other_snmp_model_uses_its_own_field_mapping():
    task = _task("fw", CollectPluginTypes.SNMP, "security_device")
    fields = task_collected_fields(task)
    assert "sn" not in fields
    assert "sys_desc" not in fields
    assert "soid" not in fields


def test_version_conflict_rejects_the_later_save_and_hidden_member_stays(visible, monkeypatch):
    hidden = _task("hidden")
    visible_a = _task("A", "custom_script")
    visible_b = _task("B")
    payload = create_reconcile(_Request(), name="group", model_id="mysql", task_ids=[hidden.id, visible_a.id, visible_b.id])
    monkeypatch.setattr(
        "apps.cmdb.services.collect_reconcile._visible_tasks",
        lambda request: CollectModels.objects.exclude(id=hidden.id),
    )
    with pytest.raises(ValidationAppException, match="刷新"):
        update_reconcile(_Request(), payload["id"], version=payload["version"] + 1, task_ids=[visible_b.id, visible_a.id])
    updated = update_reconcile(_Request(), payload["id"], version=payload["version"], task_ids=[visible_b.id, visible_a.id])
    assert [item["id"] for item in updated["members"]] == [visible_b.id, visible_a.id]
    assert load_write_context(hidden.id)["member_order"][0] == str(hidden.id)


def test_deleting_a_member_down_to_one_stops_the_reconcile(visible):
    task_a = _task("A")
    task_b = _task("B", "custom_script")
    create_reconcile(_Request(), name="ab", model_id="mysql", task_ids=[task_a.id, task_b.id])
    task_a.delete()
    assert load_write_context(task_b.id) is None
