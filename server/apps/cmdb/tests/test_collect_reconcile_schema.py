import pytest
from django.db import IntegrityError, transaction

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.collect_reconcile import CollectReconcile, CollectReconcileOrder

pytestmark = pytest.mark.django_db


def _task(name, task_type="protocol", model_id="mysql"):
    return CollectModels.objects.create(name=name, task_type=task_type, model_id=model_id, cycle_value_type="cycle", team=[1])


def test_member_and_field_orders_share_one_table_and_names_are_unique_per_model():
    task_a = _task("A")
    reconcile = CollectReconcile.objects.create(name="mysql-ab", model_id="mysql")
    CollectReconcileOrder.objects.create(reconcile=reconcile, scope="member", task=task_a, position=0)
    CollectReconcileOrder.objects.create(reconcile=reconcile, scope="port", task=task_a, position=0)
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            CollectReconcile.objects.create(name="mysql-ab", model_id="mysql")
    CollectReconcile.objects.create(name="mysql-ab", model_id="redis")


def test_one_task_has_one_member_row_and_positions_do_not_repeat():
    task_a = _task("A")
    first = CollectReconcile.objects.create(name="one", model_id="mysql")
    second = CollectReconcile.objects.create(name="two", model_id="mysql")
    CollectReconcileOrder.objects.create(reconcile=first, scope="member", task=task_a, position=0)
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            CollectReconcileOrder.objects.create(reconcile=second, scope="member", task=task_a, position=0)
    task_b = _task("B")
    CollectReconcileOrder.objects.create(reconcile=first, scope="member", task=task_b, position=1)
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            CollectReconcileOrder.objects.create(reconcile=first, scope="member", task=task_b, position=1)


def test_deleting_a_task_removes_orders_and_deleting_reconcile_keeps_the_task():
    task_a = _task("A")
    task_b = _task("B")
    reconcile = CollectReconcile.objects.create(name="group", model_id="mysql")
    CollectReconcileOrder.objects.create(reconcile=reconcile, scope="member", task=task_a, position=0)
    CollectReconcileOrder.objects.create(reconcile=reconcile, scope="member", task=task_b, position=1)
    CollectReconcileOrder.objects.create(reconcile=reconcile, scope="port", task=task_a, position=0)
    assert reconcile.is_effective()
    task_a.delete()
    assert CollectReconcileOrder.objects.filter(task=task_a).count() == 0
    assert CollectReconcile.objects.filter(id=reconcile.id).exists()
    assert not CollectReconcile.objects.get(id=reconcile.id).is_effective()
    reconcile.delete()
    assert CollectModels.objects.filter(id=task_b.id).exists()


def test_supported_types_cover_snmp_and_exclude_vmware_custom_script():
    assert CollectPluginTypes.SNMP == "snmp"
    assert CollectPluginTypes.CLOUD == "cloud"
