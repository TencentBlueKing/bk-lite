"""K3S 衍生实例发现隔离契约。"""

import pytest

from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
from apps.monitor.tasks.services.sync_instance import SyncInstance

pytestmark = pytest.mark.django_db


def _vm_result(*metrics):
    return {
        "data": {
            "result": [
                {"metric": metric, "value": [1, "1"]}
                for metric in metrics
            ]
        }
    }


def _create_objects():
    cluster = MonitorObject.objects.create(
        name="K3SCluster",
        level="base",
        default_metric='count(kube_node_info{instance_type="k3s"}) by (instance_id)',
        instance_id_keys=["instance_id"],
    )
    node = MonitorObject.objects.create(
        name="K3SNode",
        level="derivative",
        parent=cluster,
        default_metric='kube_node_info{instance_type="k3s"}',
        instance_id_keys=["instance_id", "node"],
    )
    pod = MonitorObject.objects.create(
        name="K3SPod",
        level="derivative",
        parent=cluster,
        default_metric='kube_pod_info{instance_type="k3s"}',
        instance_id_keys=["instance_id", "pod"],
    )
    return cluster, node, pod


def test_discovers_only_k3s_children_and_is_idempotent(mocker):
    cluster, node, pod = _create_objects()
    MonitorInstance.objects.create(
        id="('c1',)",
        name="c1",
        monitor_object=cluster,
        auto=False,
    )
    query = mocker.patch(
        "apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI.query"
    )

    def query_result(promql, **_kwargs):
        if 'instance_type="k3s"' not in promql:
            return _vm_result(
                {"instance_type": "k8s", "instance_id": "c1", "node": "n-k8s"},
                {"instance_type": "k8s", "instance_id": "c1", "pod": "p-k8s"},
            )
        if "kube_node_info" in promql:
            return _vm_result(
                {"instance_type": "k3s", "instance_id": "c1", "node": "n1"}
            )
        if "kube_pod_info" in promql:
            return _vm_result(
                {"instance_type": "k3s", "instance_id": "c1", "pod": "p1"}
            )
        return _vm_result()

    query.side_effect = query_result

    SyncInstance().run()
    SyncInstance().run()

    assert MonitorInstance.objects.filter(
        id="('c1', 'n1')", monitor_object=node
    ).count() == 1
    assert MonitorInstance.objects.filter(
        id="('c1', 'p1')", monitor_object=pod
    ).count() == 1
    assert not MonitorInstance.objects.filter(name__contains="k8s").exists()


def test_broken_plugin_query_does_not_block_k3s_or_deactivate_its_instances(
    mocker,
):
    broken = MonitorObject.objects.create(
        name="BrokenBeforeK3S",
        level="base",
        default_metric="broken_query",
        instance_id_keys=["instance_id"],
    )
    broken_instance = MonitorInstance.objects.create(
        id="('keep-active',)",
        name="keep-active",
        monitor_object=broken,
        auto=True,
        is_active=True,
    )
    cluster, node, pod = _create_objects()
    MonitorInstance.objects.create(
        id="('c1',)",
        name="c1",
        monitor_object=cluster,
        auto=False,
    )
    query = mocker.patch(
        "apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI.query"
    )

    def query_result(promql, **_kwargs):
        if promql == "broken_query":
            raise RuntimeError("invalid plugin query")
        if "kube_node_info" in promql:
            return _vm_result(
                {"instance_type": "k3s", "instance_id": "c1", "node": "n1"}
            )
        if "kube_pod_info" in promql:
            return _vm_result(
                {"instance_type": "k3s", "instance_id": "c1", "pod": "p1"}
            )
        return _vm_result()

    query.side_effect = query_result

    SyncInstance().run()

    assert MonitorInstance.objects.filter(
        id="('c1', 'n1')", monitor_object=node
    ).exists()
    assert MonitorInstance.objects.filter(
        id="('c1', 'p1')", monitor_object=pod
    ).exists()
    broken_instance.refresh_from_db()
    assert broken_instance.is_active is True


@pytest.mark.parametrize("is_deleted", [False, True])
def test_does_not_create_orphan_children_without_active_parent(mocker, is_deleted):
    cluster, node, pod = _create_objects()
    if is_deleted:
        MonitorInstance.objects.create(
            id="('c1',)",
            name="c1",
            monitor_object=cluster,
            auto=False,
            is_deleted=True,
        )
    query = mocker.patch(
        "apps.monitor.tasks.services.sync_instance.VictoriaMetricsAPI.query"
    )
    query.side_effect = lambda promql, **_kwargs: (
        _vm_result(
            {"instance_type": "k3s", "instance_id": "c1", "node": "n1"}
        )
        if "kube_node_info" in promql
        else _vm_result(
            {"instance_type": "k3s", "instance_id": "c1", "pod": "p1"}
        )
        if "kube_pod_info" in promql
        else _vm_result()
    )

    SyncInstance().run()

    assert not MonitorInstance.objects.filter(monitor_object__in=[node, pod]).exists()
