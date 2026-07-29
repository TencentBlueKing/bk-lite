import pytest

from apps.cmdb.tests.e2e import pipeline


WinsphereCollectionPlugin = pytest.importorskip(
    "apps.cmdb_enterprise.collect.winsphere",
    reason="WinSphere 仅随企业采集扩展交付",
).WinsphereCollectionPlugin


def test_winsphere_snapshot_flows_through_all_inventory_models(monkeypatch):
    platform_id = "https://10.0.0.10:443"
    stargazer_payload = {
        "success": True,
        "snapshot_id": "snapshot-e2e",
        "snapshot_status": "complete",
        "result": {
            "winsphere": [
                {
                    "resource_id": platform_id,
                    "platform_id": platform_id,
                    "inst_name": platform_id,
                    "management_address": "10.0.0.10",
                    "https_port": "443",
                }
            ],
            "winsphere_host_pool": [
                {
                    "resource_id": "pool-1",
                    "platform_id": platform_id,
                    "inst_name": f"{platform_id}/资源池[pool-1]",
                }
            ],
            "winsphere_cluster": [
                {
                    "resource_id": "cluster-1",
                    "platform_id": platform_id,
                    "pool_id": "pool-1",
                    "inst_name": f"{platform_id}/集群[cluster-1]",
                }
            ],
            "winsphere_host": [
                {
                    "resource_id": "host-1",
                    "platform_id": platform_id,
                    "cluster_id": "cluster-1",
                    "inst_name": f"{platform_id}/主机[host-1]",
                    "memory_gib": "128.00",
                }
            ],
            "winsphere_vm": [
                {
                    "resource_id": "vm-1",
                    "platform_id": platform_id,
                    "host_id": "host-1",
                    "inst_name": f"{platform_id}/虚拟机[vm-1]",
                    "up_time_seconds": "3600",
                }
            ],
            "winsphere_storage_pool": [
                {
                    "resource_id": "storage-1",
                    "platform_id": platform_id,
                    "host_ids": "host-1",
                    "inst_name": f"{platform_id}/存储池[storage-1]",
                }
            ],
            "winsphere_vswitch": [
                {
                    "resource_id": "distributed:dvs-1",
                    "platform_id": platform_id,
                    "host_ids": "host-1",
                    "inst_name": f"{platform_id}/交换机[dvs-1]",
                }
            ],
            "winsphere_port_group": [
                {
                    "resource_id": "distributed:dvs-1:pg-1",
                    "platform_id": platform_id,
                    "switch_id": "distributed:dvs-1",
                    "inst_name": f"{platform_id}/端口组[pg-1]",
                }
            ],
        },
    }
    vm_response = pipeline.step2_push_to_vm(stargazer_payload, task_id=9400)

    class FakeTask:
        id = 9400
        params = {}
        instances = [{"inst_name": "winsphere-prod"}]

    monkeypatch.setattr(
        WinsphereCollectionPlugin,
        "get_collect_inst",
        lambda self: FakeTask(),
    )
    monkeypatch.setattr(
        WinsphereCollectionPlugin,
        "model_id",
        property(lambda self: "winsphere"),
    )
    monkeypatch.setattr(
        "apps.cmdb.collection.query_vm.Collection.query",
        lambda self, sql, timeout=60: vm_response,
    )
    monkeypatch.setattr(
        "apps.cmdb_enterprise.collect.new_objects.get_collection_plugin",
        lambda plug_type, model_id: WinsphereCollectionPlugin,
    )
    runner = WinsphereCollectionPlugin(
        inst_name="winsphere-prod",
        inst_id=10001,
        task_id=9400,
    )
    runner.run()
    result = runner.result

    assert set(result) == set(stargazer_payload["result"])
    assert result["winsphere"][0]["inst_name"] == "winsphere-prod"
    assert result["winsphere_host"][0]["memory_gib"] == 128.0
    assert result["winsphere_vm"][0]["up_time_seconds"] == 3600
    assert result["winsphere_port_group"][0]["assos"][0][
        "model_asst_id"
    ] == "winsphere_port_group_group_winsphere_vswitch"
