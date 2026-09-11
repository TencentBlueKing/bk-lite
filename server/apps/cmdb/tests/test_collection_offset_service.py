"""错峰保存契约：真实 ORM + 最终节点配置，外部下发单独替换。"""
import copy
import uuid
from types import SimpleNamespace

import pytest
import toml
from django.db import transaction

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.services.collection_offset_service import CollectionOffsetService

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def new_task(model_id="host", **overrides):
    data = dict(
        name=f"offset-{uuid.uuid4().hex}",
        model_id=model_id,
        task_type="host" if model_id == "host" else "snmp",
        driver_type="job" if model_id == "host" else "protocol",
        is_interval=True,
        cycle_value_type="cycle",
        cycle_value="30",
        team=[1],
        params={},
        credential={},
        access_point=[{"id": "node-1"}],
        instances=[{"ip_addr": "10.0.0.1"}],
    )
    data.update(overrides)
    return CollectModels.objects.create(**data)


def save_offset(task, previous=None):
    with transaction.atomic(), CollectionOffsetService.serialize(task):
        CollectionOffsetService.apply(task, previous=previous)
    task.refresh_from_db()
    return task


def test_new_host_avoids_legacy_task_and_renders_persisted_offset():
    legacy = new_task()
    current = save_offset(new_task(params={"ip_precheck": True}))
    assert 0 < current.params["collection_offset_seconds"] < 1800
    assert current.params["ip_precheck"] is True
    assert current.cycle_value == "30"
    source = toml.loads(NodeParamsFactory.get_node_params(current).push_params()[0]["content"])["inputs"]["prometheus"][0]
    assert source["collection_offset"] == f'{current.params["collection_offset_seconds"]}s'
    legacy.refresh_from_db()
    assert legacy.params == {}


def test_network_channels_are_allocated_together():
    current = save_offset(new_task("network", params={"has_network_topo": True, "topology_interval_minutes": 30}))
    assert current.params["collection_offset_seconds"] != current.params["topology_collection_offset_seconds"]
    assert current.cycle_value == "30"


def test_unrelated_edit_preserves_offset_and_legacy_is_not_enrolled():
    legacy = new_task()
    save_offset(legacy, copy.deepcopy(legacy))
    assert legacy.params == {}
    current = save_offset(new_task())
    previous = copy.deepcopy(current)
    current.name = "renamed"
    current.save()
    save_offset(current, previous)
    assert current.params == previous.params


def test_unsupported_plugin_is_unchanged():
    current = save_offset(new_task("redis", params={"other": 1}))
    assert current.params == {"other": 1}


def test_collect_create_ignores_client_offset_and_pushes_saved_phase(mocker, django_capture_on_commit_callbacks):
    from apps.cmdb.serializers.collect_serializer import CollectModelSerializer
    from apps.cmdb.services.collect_service import CollectModelService

    new_task()
    payload = dict(
        name="new-host",
        task_type="host",
        driver_type="job",
        model_id="host",
        timeout=60,
        input_method=0,
        team=[1],
        scan_cycle={"value_type": "cycle", "value": "30"},
        access_point=[{"id": "node-1", "cloud": 1}],
        ip_range="10.0.0.2",
        credential={},
        params={"collection_offset_seconds": 0, "ip_precheck": True},
    )
    request = SimpleNamespace(data=payload, user=SimpleNamespace(username="admin", group_list=[{"id": 1, "name": "Default"}]), COOKIES={})
    view = SimpleNamespace(
        get_serializer=lambda *a, **kw: CollectModelSerializer(*a, context={"request": request}, **kw),
        perform_create=lambda serializer: serializer.save(),
    )
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    mocker.patch.object(CollectModelService, "schedule_first_collection_if_needed", return_value=None)
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    mocker.patch("apps.core.utils.serializers.get_permission_rules", return_value={"team": [1]})
    # RPC 是外部接口，保留真实节点渲染。
    pushed = mocker.patch("apps.cmdb.services.collect_service.NodeMgmt")
    with django_capture_on_commit_callbacks(execute=True):
        task_id = CollectModelService.create(request, view)
    saved = CollectModels.objects.get(pk=task_id)
    assert 0 < saved.params["collection_offset_seconds"] < 1800
    nodes = pushed.return_value.batch_add_node_child_config.call_args.args[0]
    source = toml.loads(nodes[0]["content"])["inputs"]["prometheus"][0]
    assert source["interval"] == "1800s"
    assert source["collection_offset"] == f'{saved.params["collection_offset_seconds"]}s'


@pytest.mark.parametrize("change", ["cycle", "access_point", "resume"])
def test_managed_schedule_change_keeps_valid_offset_and_other_tasks(change):
    other = new_task()
    current = save_offset(new_task())
    previous = copy.deepcopy(current)
    if change == "cycle":
        current.cycle_value = "1"
    elif change == "access_point":
        current.access_point = [{"id": "node-2"}]
    else:
        previous.is_interval = False
    current.save()
    save_offset(current, previous)
    assert 0 <= current.params["collection_offset_seconds"] < int(current.cycle_value) * 60
    other.refresh_from_db()
    assert other.params == {}


def test_enable_topology_allocates_only_new_channel():
    current = save_offset(new_task("network", params={"has_network_topo": False}))
    previous = copy.deepcopy(current)
    current.params.update(has_network_topo=True, topology_interval_minutes=30)
    current.save()
    save_offset(current, previous)
    assert current.params["collection_offset_seconds"] == previous.params["collection_offset_seconds"]
    assert current.params["topology_collection_offset_seconds"] != current.params["collection_offset_seconds"]


def test_disabled_topology_does_not_take_a_slot():
    legacy = new_task("network", params={"has_network_topo": False, "topology_collection_offset_seconds": 900})
    current = save_offset(new_task())
    assert current.params["collection_offset_seconds"] == 900
    legacy.refresh_from_db()
    assert legacy.params["topology_collection_offset_seconds"] == 900


def test_failed_transaction_rolls_back_offset_and_releases_write_lock():
    from apps.cmdb.models.operation import CmdbUniqueWriteLock

    current = new_task()
    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic(), CollectionOffsetService.serialize(current):
            CollectionOffsetService.apply(current)
            raise RuntimeError("rollback")
    current.refresh_from_db()
    assert current.params == {}
    assert not CmdbUniqueWriteLock.objects.filter(pk=CollectionOffsetService.LOCK_KEY).exists()
    save_offset(current)
    assert "collection_offset_seconds" in current.params


def test_lock_competition_does_not_save_duplicate_offset():
    from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
    from apps.core.exceptions.base_app_exception import BaseAppException

    current = new_task()
    with transaction.atomic(), CollectionOffsetService.serialize(current):
        with pytest.raises(BaseAppException):
            with transaction.atomic(), CollectionOffsetService.serialize(current):
                CollectionOffsetService.apply(current)
        assert UniqueWriteLockService.acquire(CollectionOffsetService.LOCK_KEY, owner_token="competitor") is False
    current.refresh_from_db()
    assert current.params == {}
    save_offset(current)
    assert "collection_offset_seconds" in current.params


@pytest.fixture
def collect_api(mocker):
    from apps.cmdb.serializers.collect_serializer import CollectModelSerializer
    from apps.cmdb.services.collect_service import CollectModelService

    request = SimpleNamespace(data={}, user=SimpleNamespace(username="admin"), COOKIES={"current_team": "1"})
    selected = {"id": None}
    view = SimpleNamespace(
        get_serializer=lambda *args, **kwargs: CollectModelSerializer(*args, context={"request": request}, **kwargs),
        get_object=lambda: CollectModels.objects.get(pk=selected["id"]),
        perform_create=lambda serializer: serializer.save(),
        perform_update=lambda serializer: serializer.save(),
        get_has_permission=lambda *args, **kwargs: True,
        delete_rules=lambda *args, **kwargs: None,
    )
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    mocker.patch("apps.core.utils.serializers.get_permission_rules", return_value={"team": [1]})
    mocker.patch.object(CollectModelService, "schedule_first_collection_if_needed", return_value=None)
    mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
    rpc = mocker.patch("apps.cmdb.services.collect_service.NodeMgmt").return_value
    mocker.patch("apps.cmdb.services.network_collection_reconcile.NodeMgmt", return_value=rpc)

    def payload(model="host", **updates):
        values = dict(
            name=f"api-{uuid.uuid4().hex}",
            task_type="host" if model == "host" else "snmp",
            driver_type="job" if model == "host" else "protocol",
            model_id=model,
            timeout=60,
            input_method=0,
            team=[1],
            scan_cycle={"value_type": "cycle", "value": "30"},
            access_point=[{"id": "node-1", "cloud": 1}],
            ip_range="10.0.0.1-10.0.0.10",
            credential={"username": "fixture", "password": "test-only"},
            params={},
        )
        values.update(updates)
        return values

    return SimpleNamespace(service=CollectModelService, request=request, view=view, selected=selected, rpc=rpc, payload=payload)


def test_edit_cannot_overwrite_or_erase_server_owned_offset(collect_api, django_capture_on_commit_callbacks):
    api = collect_api
    current = save_offset(new_task())
    saved_offset = current.params["collection_offset_seconds"]
    api.selected["id"] = current.id
    for params in ({"collection_offset_seconds": 1740, "custom": True}, {"custom": False}):
        api.request.data = api.payload(name=current.name, params=params)
        with django_capture_on_commit_callbacks(execute=True):
            api.service.update(api.request, api.view)
        current.refresh_from_db()
        assert current.params["collection_offset_seconds"] == saved_offset
        assert current.params["custom"] == params["custom"]


def test_saved_offset_survives_post_commit_failure_and_retry(collect_api, django_capture_on_commit_callbacks):
    from apps.core.exceptions.base_app_exception import BaseAppException

    api = collect_api
    new_task()
    api.request.data = api.payload()
    api.rpc.batch_add_node_child_config.side_effect = RuntimeError("test delivery failure")
    with pytest.raises(BaseAppException, match="已保存"):
        with django_capture_on_commit_callbacks(execute=True):
            api.service.create(api.request, api.view)
    current = CollectModels.objects.get(name=api.request.data["name"])
    offset = current.params["collection_offset_seconds"]
    assert offset > 0
    api.selected["id"] = current.id
    api.rpc.batch_add_node_child_config.side_effect = None
    with django_capture_on_commit_callbacks(execute=True):
        api.service.update(api.request, api.view)
    current.refresh_from_db()
    assert current.params["collection_offset_seconds"] == offset
    pushed = api.rpc.batch_add_node_child_config.call_args.args[0]
    assert f'collection_offset = "{offset}s"' in pushed[0]["content"]


def test_permission_is_checked_again_after_acquiring_lock(collect_api):
    from apps.core.exceptions.base_app_exception import BaseAppException

    api = collect_api
    current = save_offset(new_task())
    api.selected["id"] = current.id
    api.request.data = api.payload()
    api.view.get_has_permission = lambda *args, **kwargs: False
    with pytest.raises(BaseAppException, match="权限"):
        api.service.update(api.request, api.view)
    current.refresh_from_db()
    assert current.name != api.request.data["name"]
    api.rpc.batch_add_node_child_config.assert_not_called()


def test_two_channel_save_pushes_matching_ids_intervals_and_offsets(collect_api, django_capture_on_commit_callbacks):
    api = collect_api
    api.request.data = api.payload("network", params={"has_network_topo": True, "topology_interval_minutes": 150})
    with django_capture_on_commit_callbacks(execute=True):
        task_id = api.service.create(api.request, api.view)
    current = CollectModels.objects.get(pk=task_id)
    nodes = api.rpc.batch_add_node_child_config.call_args.args[0]
    assert [node["id"] for node in nodes] == [f"cmdb_{task_id}", f"cmdb_{task_id}_topology"]
    for node, interval, key in zip(nodes, (1800, 9000), ("collection_offset_seconds", "topology_collection_offset_seconds")):
        source = toml.loads(node["content"])["inputs"]["prometheus"][0]
        assert source["interval"] == f"{interval}s"
        assert source["collection_offset"] == f"{current.params[key]}s"


def test_lock_contention_rolls_back_create_before_external_effects(collect_api, django_capture_on_commit_callbacks):
    from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
    from apps.core.exceptions.base_app_exception import BaseAppException

    api = collect_api
    api.request.data = api.payload()
    with UniqueWriteLockService.hold([CollectionOffsetService.LOCK_KEY]):
        with pytest.raises(BaseAppException):
            with django_capture_on_commit_callbacks(execute=True):
                api.service.create(api.request, api.view)
    assert not CollectModels.objects.filter(name=api.request.data["name"]).exists()
    api.rpc.batch_add_node_child_config.assert_not_called()


def test_registered_future_plugin_reuses_allocation_and_rendering(monkeypatch):
    from apps.cmdb.node_configs.base import BaseNodeParams
    from apps.cmdb.services import collection_offset_policy as policy

    class FutureNodeParams(BaseNodeParams):
        supported_model_id = "offset_test_future"
        plugin_name = "offset_test_future_info"

        def set_credential(self):
            return {}

        def env_config(self):
            return {}

    monkeypatch.setattr(
        policy,
        "OFFSET_CHANNELS",
        (*policy.OFFSET_CHANNELS, policy.OffsetChannel("offset_test_future", "offset_test_future_info", "device", "collection_offset_seconds")),
    )
    try:
        new_task()
        current = save_offset(new_task("offset_test_future"))
        source = toml.loads(FutureNodeParams(current).push_params()[0]["content"])["inputs"]["prometheus"][0]
        assert source["collection_offset"] == f'{current.params["collection_offset_seconds"]}s'
        assert current.params["collection_offset_seconds"] > 0
    finally:
        BaseNodeParams._registry.pop(("offset_test_future", None), None)
        BaseNodeParams.PLUGIN_MAP.pop(("offset_test_future", None), None)


def test_legacy_edit_ignores_client_attempt_to_enable_offset(collect_api, django_capture_on_commit_callbacks):
    api = collect_api
    current = new_task()
    api.selected["id"] = current.id
    api.request.data = api.payload(name=current.name, params={"collection_offset_seconds": 420, "custom": True})
    with django_capture_on_commit_callbacks(execute=True):
        api.service.update(api.request, api.view)
    current.refresh_from_db()
    assert "collection_offset_seconds" not in current.params
    assert current.params["custom"] is True


def test_read_after_lock_uses_latest_offset(collect_api):
    api = collect_api
    current = save_offset(new_task())
    stale = copy.deepcopy(current)
    current.params["collection_offset_seconds"] = 600
    current.save(update_fields=["params"])
    calls = []

    def get_object():
        calls.append(1)
        return stale if len(calls) == 1 else CollectModels.objects.get(pk=current.id)

    api.view.get_object = get_object
    api.request.data = api.payload(name=current.name, params={"custom": True})
    api.service.update(api.request, api.view)
    current.refresh_from_db()
    assert current.params["collection_offset_seconds"] == 600


def test_other_organizations_and_nodes_still_contribute_shared_load():
    new_task(team=[2], access_point=[{"id": "other-node"}])
    current = save_offset(new_task(team=[1]))
    assert current.params["collection_offset_seconds"] == 900


def test_node_sync_created_host_gets_offset_and_refresh_preserves_it(mocker):
    from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig
    from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

    new_task()
    config = NodeMgmtSyncConfig.objects.create(auto_collect_enabled=True)
    mocker.patch.object(NodeMgmtSyncService, "get_task", return_value=config)
    params = dict(
        cloud_region_id=7, cloud_region_name="区域7", access_point={"id": "ap-7"}, team=[1], instances=[{"ip_addr": "10.0.0.1"}], interval_minutes=30
    )
    created = NodeMgmtSyncService._ensure_region_collect_task(**params)
    offset = created.params["collection_offset_seconds"]
    assert 0 < offset < 1800
    params["instances"] = [{"ip_addr": "10.0.0.2"}]
    refreshed = NodeMgmtSyncService._ensure_region_collect_task(**params)
    assert refreshed.id == created.id
    assert refreshed.params["collection_offset_seconds"] == offset


@pytest.mark.django_db(transaction=True)
def test_competing_transactions_never_commit_same_available_phase():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import DatabaseError, close_old_connections

    from apps.core.exceptions.base_app_exception import BaseAppException

    barrier = Barrier(2)

    def create_competing():
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            try:
                with transaction.atomic(), CollectionOffsetService.serialize({"model_id": "host"}):
                    task = new_task()
                    CollectionOffsetService.apply(task)
                    return task.id
            except (DatabaseError, BaseAppException):
                # SQLite 的写竞争可拒绝一个事务；失败事务必须完整回滚，然后重试。
                return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(create_competing) for _ in range(2)]
        ids = [future.result(timeout=10) for future in futures]
    # SQLite 允许竞争的双方均回滚；任何已提交任务都必须完整，重试后仍应分散。
    assert CollectModels.objects.count() == sum(task_id is not None for task_id in ids)
    for task_id in ids:
        if task_id is None:
            with transaction.atomic(), CollectionOffsetService.serialize({"model_id": "host"}):
                CollectionOffsetService.apply(new_task())
    offsets = [task.params["collection_offset_seconds"] for task in CollectModels.objects.all()]
    assert len(offsets) == 2
    assert len(set(offsets)) == 2
