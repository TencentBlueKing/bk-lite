"""cmdb.services.collect_service.CollectModelService 静态/类方法测试。

聚焦未覆盖的纯逻辑与边界封装：
- _safe_int / _get_snapshot_item / _snapshot_task；
- 云区域元数据解析链 _resolve_host_cloud_meta（含按节点反查、按云ID查名，mock NodeMgmt）；
- enrich_host_cloud_snapshot_payload（变更检测、非 host 跳过、实例回填）；
- repair_host_cloud_snapshot（host 判定、persist 分支）；
- format_update_credential（dict 合并 / list 池合并 / regions / None / 格式错误）；
- is_schedule_config_changed；_normalize_cloud_regions；
- list_regions（成功 / 失败分支，mock Stargazer）；
- schedule_delayed_sync_if_needed（阈值/类型/非法值分支，mock transaction.on_commit）。
仅 mock 真实外部边界：NodeMgmt RPC、Stargazer RPC、transaction.on_commit。
"""
import pydantic.root_model  # noqa

import types

import pytest

from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.services.collect_service import CollectModelService
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit


def fake_instance(**kw):
    """轻量假实例：仅承载属性访问，避免 DB。"""
    obj = types.SimpleNamespace()
    for k, v in kw.items():
        setattr(obj, k, v)
    return obj


def collect_payload(**overrides):
    payload = {
        "name": "task1",
        "task_type": CollectPluginTypes.HOST,
        "driver_type": "snmp",
        "model_id": "host",
        "timeout": 60,
        "input_method": 0,
        "team": [1],
        "scan_cycle": {"value_type": "cycle", "value": "5"},
        "access_point": [{"id": "node-1", "cloud": 1, "cloud_name": "default"}],
        "credential": {"username": "root"},
    }
    payload.update(overrides)
    return payload


def collect_instance(**overrides):
    base = {
        "id": 1,
        "name": "task1",
        "task_type": CollectPluginTypes.HOST,
        "driver_type": "snmp",
        "model_id": "host",
        "timeout": 60,
        "input_method": 0,
        "team": [1],
        "scan_cycle": "*/5 * * * *",
        "cycle_value_type": "cycle",
        "cycle_value": "5",
        "is_interval": True,
        "is_k8s": False,
        "credential": {},
        "decrypt_credentials": {"username": "root"},
        "params": {},
        "instances": [],
        "access_point": [{"id": "node-1", "cloud": 1, "cloud_name": "default"}],
        "delete": lambda: None,
    }
    base.update(overrides)
    return fake_instance(**base)


class FakeSerializer:
    def __init__(self, instance):
        self.instance = instance

    def is_valid(self, raise_exception=False):
        return True


class FakeCollectView:
    def __init__(self, instance):
        self.instance = instance
        self.delete_rules = lambda *args, **kwargs: None

    def get_serializer(self, *args, **kwargs):
        if args and args[0] is self.instance:
            return FakeSerializer(self.instance)
        return FakeSerializer(self.instance)

    def perform_create(self, serializer):
        serializer.instance = self.instance

    def perform_update(self, serializer):
        serializer.instance = self.instance

    def get_object(self):
        return self.instance


def fake_request(data):
    return fake_instance(data=data, user=fake_instance(username="tester"), COOKIES={})


class FakeAtomic:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def patch_transaction_callbacks(mocker):
    callbacks = []
    mocker.patch("apps.cmdb.services.collect_service.transaction.atomic", return_value=FakeAtomic())
    mocker.patch("apps.cmdb.services.collect_service.transaction.on_commit", side_effect=callbacks.append)
    return callbacks


class TestPrimitives:
    def test_safe_int(self):
        assert CollectModelService._safe_int("5") == 5
        assert CollectModelService._safe_int(None) is None
        assert CollectModelService._safe_int("abc") is None

    def test_get_snapshot_item(self):
        assert CollectModelService._get_snapshot_item({"a": 1}) == {"a": 1}
        assert CollectModelService._get_snapshot_item([{"b": 2}]) == {"b": 2}
        assert CollectModelService._get_snapshot_item([]) == {}
        assert CollectModelService._get_snapshot_item("x") == {}
        assert CollectModelService._get_snapshot_item(["notdict"]) == {}

    def test_snapshot_task_空与正常(self):
        assert CollectModelService._snapshot_task(None) == {}
        inst = fake_instance(id=1, name="t", task_type="host", exec_time=None)
        snap = CollectModelService._snapshot_task(inst)
        assert snap["id"] == 1
        assert snap["name"] == "t"
        assert snap["exec_time"] is None

    def test_snapshot_task_exec_time_isoformat(self):
        from datetime import datetime

        inst = fake_instance(id=1, name="t", exec_time=datetime(2026, 1, 2, 3, 4, 5))
        snap = CollectModelService._snapshot_task(inst)
        assert snap["exec_time"] == "2026-01-02T03:04:05"

    def test_should_sync_node_params(self):
        assert CollectModelService.should_sync_node_params(fake_instance(is_k8s=False))
        assert not CollectModelService.should_sync_node_params(fake_instance(is_k8s=True))


class TestResolveCloudMeta:
    def test_task_cloud优先_非access_point模式(self):
        cloud, name = CollectModelService._resolve_host_cloud_meta(
            params={"cloud": 7, "cloud_name": "区域7"},
            access_point=[{"cloud": 9, "cloud_name": "区域9"}],
            instances=[],
            prefer_access_point=False,
        )
        assert cloud == 7
        assert name == "区域7"

    def test_access_point优先模式(self):
        cloud, name = CollectModelService._resolve_host_cloud_meta(
            params={"cloud": 7, "cloud_name": "区域7"},
            access_point=[{"cloud": 9, "cloud_name": "区域9"}],
            instances=[],
            prefer_access_point=True,
        )
        assert cloud == 9
        assert name == "区域9"

    def test_access_point优先但无ap云_回退task(self):
        cloud, name = CollectModelService._resolve_host_cloud_meta(
            params={"cloud": 7, "cloud_name": "区域7"},
            access_point=[{}],
            instances=[],
            prefer_access_point=True,
        )
        assert cloud == 7
        assert name == "区域7"

    def test_无云时按节点反查(self, mocker):
        rpc = mocker.MagicMock()
        rpc.get_nodes_by_ids.return_value = [{"cloud_region_id": "3"}]
        mocker.patch.object(CollectModelService, "_node_mgmt_client", return_value=rpc)
        cloud, name = CollectModelService._resolve_host_cloud_meta(
            params={},
            access_point=[{"id": "node-1"}],
            instances=[],
            prefer_access_point=False,
        )
        assert cloud == 3
        rpc.get_nodes_by_ids.assert_called_once_with(["node-1"])

    def test_无云名时按云id查名(self, mocker):
        rpc = mocker.MagicMock()
        rpc.cloud_region_list.return_value = [{"id": 5, "name": "云五"}]
        mocker.patch.object(CollectModelService, "_node_mgmt_client", return_value=rpc)
        cloud, name = CollectModelService._resolve_host_cloud_meta(
            params={"cloud": 5},
            access_point=[],
            instances=[],
            prefer_access_point=False,
        )
        assert cloud == 5
        assert name == "云五"

    def test_节点反查空结果返回None(self, mocker):
        rpc = mocker.MagicMock()
        rpc.get_nodes_by_ids.return_value = []
        rpc.cloud_region_list.return_value = []
        mocker.patch.object(CollectModelService, "_node_mgmt_client", return_value=rpc)
        cloud, name = CollectModelService._resolve_host_cloud_meta(
            params={},
            access_point=[{"id": "x"}],
            instances=[],
        )
        assert cloud is None
        assert name == ""


class TestEnrichSnapshot:
    def test_非host跳过(self):
        data = {"task_type": CollectPluginTypes.K8S, "params": {}}
        assert CollectModelService.enrich_host_cloud_snapshot_payload(data) is False

    def test_host回填云信息到params和实例(self, mocker):
        mocker.patch.object(
            CollectModelService,
            "_resolve_host_cloud_meta",
            return_value=(11, "区域11"),
        )
        data = {
            "task_type": CollectPluginTypes.HOST,
            "params": {},
            "instances": [{"inst_name": "h1"}, "skip-non-dict"],
            "access_point": [],
        }
        changed = CollectModelService.enrich_host_cloud_snapshot_payload(data)
        assert changed is True
        assert data["params"]["cloud"] == 11
        assert data["params"]["cloud_name"] == "区域11"
        assert data["instances"][0]["cloud"] == 11
        assert data["instances"][0]["cloud_name"] == "区域11"

    def test_host已有相同云信息_无变化(self, mocker):
        mocker.patch.object(
            CollectModelService,
            "_resolve_host_cloud_meta",
            return_value=(11, "区域11"),
        )
        data = {
            "task_type": CollectPluginTypes.HOST,
            "params": {"cloud": 11, "cloud_name": "区域11"},
            "instances": [],
        }
        assert CollectModelService.enrich_host_cloud_snapshot_payload(data) is False


class TestRepairSnapshot:
    def test_非host返回False(self):
        inst = fake_instance(is_host=False)
        assert CollectModelService.repair_host_cloud_snapshot(inst) is False

    def test_host有变化_persist_false不落库(self, mocker):
        mocker.patch.object(
            CollectModelService,
            "enrich_host_cloud_snapshot_payload",
            return_value=True,
        )
        save_calls = []
        inst = fake_instance(
            is_host=True,
            task_type=CollectPluginTypes.HOST,
            access_point=[],
            instances=[{"inst_name": "h"}],
            params={"cloud": 1},
            save=lambda **kw: save_calls.append(kw),
        )
        ok = CollectModelService.repair_host_cloud_snapshot(inst, persist=False)
        assert ok is True
        assert save_calls == []

    def test_host有变化_persist落库(self, mocker):
        mocker.patch.object(
            CollectModelService,
            "enrich_host_cloud_snapshot_payload",
            return_value=True,
        )
        save_calls = []
        inst = fake_instance(
            is_host=True,
            task_type=CollectPluginTypes.HOST,
            access_point=[],
            instances=[],
            params={},
            save=lambda **kw: save_calls.append(kw),
        )
        ok = CollectModelService.repair_host_cloud_snapshot(inst, persist=True)
        assert ok is True
        assert save_calls and save_calls[0]["update_fields"] == ["params", "instances"]

    def test_host无enrich变化_走二次解析无变化返回False(self, mocker):
        mocker.patch.object(
            CollectModelService,
            "enrich_host_cloud_snapshot_payload",
            return_value=False,
        )
        mocker.patch.object(
            CollectModelService,
            "_resolve_host_cloud_meta",
            return_value=(None, ""),
        )
        inst = fake_instance(
            is_host=True,
            task_type=CollectPluginTypes.HOST,
            access_point=[],
            instances=[],
            params={},
            save=lambda **kw: None,
        )
        assert CollectModelService.repair_host_cloud_snapshot(inst) is False


class TestFormatUpdateCredential:
    def test_空凭据非k8s_报错(self):
        inst = fake_instance(is_k8s=False, decrypt_credentials={}, task_type=CollectPluginTypes.HOST)
        with pytest.raises(BaseAppException, match="采集凭据不能为空"):
            CollectModelService.format_update_credential(inst, {"credential": None})

    def test_ip任务允许空凭据并沿用旧值(self):
        inst = fake_instance(is_k8s=False, decrypt_credentials={}, task_type=CollectPluginTypes.IP)
        data = {"credential": None}
        CollectModelService.format_update_credential(inst, data)
        assert data["credential"] == {}

    def test_仅改regions_用旧凭据(self):
        inst = fake_instance(
            is_k8s=False, decrypt_credentials={"user": "admin", "pwd": "x"}
        )
        data = {"credential": {"regions": ["cn-north"]}}
        CollectModelService.format_update_credential(inst, data)
        assert data["credential"]["user"] == "admin"
        assert data["credential"]["regions"] == ["cn-north"]

    def test_regions与其他字段共存(self):
        inst = fake_instance(is_k8s=False, decrypt_credentials={"user": "old"})
        data = {"credential": {"user": "new", "regions": ["r1"]}}
        CollectModelService.format_update_credential(inst, data)
        assert data["credential"]["user"] == "new"
        assert data["credential"]["regions"] == ["r1"]

    def test_credential为None_用旧凭据(self):
        inst = fake_instance(is_k8s=True, decrypt_credentials={"token": "t"})
        data = {"credential": None}
        CollectModelService.format_update_credential(inst, data)
        assert data["credential"] == {"token": "t"}

    def test_dict合并旧新(self):
        inst = fake_instance(
            is_k8s=False, decrypt_credentials={"user": "old", "pwd": "p"}
        )
        data = {"credential": {"user": "new"}}
        CollectModelService.format_update_credential(inst, data)
        assert data["credential"] == {"user": "new", "pwd": "p"}

    def test_list池合并保留旧项字段(self):
        inst = fake_instance(
            is_k8s=False,
            decrypt_credentials=[
                {"credential_id": "c1", "user": "u1", "pwd": "secret"}
            ],
        )
        data = {"credential": [{"credential_id": "c1", "user": "u1-new"}]}
        CollectModelService.format_update_credential(inst, data)
        merged = data["credential"][0]
        assert merged["user"] == "u1-new"
        assert merged["pwd"] == "secret"

    def test_list池含非dict项_报错(self):
        inst = fake_instance(is_k8s=False, decrypt_credentials=[])
        data = {"credential": ["notdict"]}
        with pytest.raises(BaseAppException, match="采集凭据格式错误"):
            CollectModelService.format_update_credential(inst, data)


class TestScheduleAndMisc:
    def test_is_schedule_config_changed(self):
        old = fake_instance(
            is_interval=True, cycle_value_type="cycle", cycle_value="5", scan_cycle="a"
        )
        same = fake_instance(
            is_interval=True, cycle_value_type="cycle", cycle_value="5", scan_cycle="a"
        )
        diff = fake_instance(
            is_interval=True, cycle_value_type="cycle", cycle_value="20", scan_cycle="a"
        )
        assert CollectModelService.is_schedule_config_changed(old, same) is False
        assert CollectModelService.is_schedule_config_changed(old, diff) is True

    def test_normalize_cloud_regions_非qcloud原样(self):
        regions = [{"a": 1}]
        assert CollectModelService._normalize_cloud_regions("aws", regions) is regions

    def test_normalize_cloud_regions_qcloud补字段(self):
        out = CollectModelService._normalize_cloud_regions(
            "qcloud", [{"Region": "ap-1", "RegionName": "广州"}]
        )
        assert out[0]["resource_name"] == "广州"
        assert out[0]["resource_id"] == "ap-1"

    def test_schedule_delayed_sync_非interval跳过(self, mocker):
        on_commit = mocker.patch(
            "apps.cmdb.services.collect_service.transaction.on_commit"
        )
        CollectModelService.schedule_delayed_sync_if_needed(
            fake_instance(cycle_value_type="cycle", cycle_value="20", id=1),
            is_interval=False,
        )
        on_commit.assert_not_called()

    def test_schedule_delayed_sync_非cycle类型跳过(self, mocker):
        on_commit = mocker.patch(
            "apps.cmdb.services.collect_service.transaction.on_commit"
        )
        CollectModelService.schedule_delayed_sync_if_needed(
            fake_instance(cycle_value_type="timing", cycle_value="20", id=1),
            is_interval=True,
        )
        on_commit.assert_not_called()

    def test_schedule_delayed_sync_非法值跳过(self, mocker):
        on_commit = mocker.patch(
            "apps.cmdb.services.collect_service.transaction.on_commit"
        )
        CollectModelService.schedule_delayed_sync_if_needed(
            fake_instance(cycle_value_type="cycle", cycle_value="abc", id=1),
            is_interval=True,
        )
        on_commit.assert_not_called()

    def test_schedule_delayed_sync_低于阈值跳过(self, mocker):
        on_commit = mocker.patch(
            "apps.cmdb.services.collect_service.transaction.on_commit"
        )
        CollectModelService.schedule_delayed_sync_if_needed(
            fake_instance(cycle_value_type="cycle", cycle_value="5", id=1),
            is_interval=True,
        )
        on_commit.assert_not_called()

    def test_schedule_delayed_sync_达阈值注册on_commit(self, mocker):
        on_commit = mocker.patch(
            "apps.cmdb.services.collect_service.transaction.on_commit"
        )
        CollectModelService.schedule_delayed_sync_if_needed(
            fake_instance(cycle_value_type="cycle", cycle_value="20", id=1),
            is_interval=True,
        )
        on_commit.assert_called_once()


def test_exec_task_passes_execution_token_to_sync_collect_task(settings, mocker):
    settings.DEBUG = True
    called = {}

    class FakeTask:
        id = 7
        name = "manual"
        model_id = "host"
        exec_status = CollectRunStatusType.SUCCESS
        exec_time = None
        format_data = {"old": True}
        collect_data = {"old": True}
        collect_digest = {"message": "old"}
        task_id = ""

        def save(self):
            called["saved_status"] = self.exec_status
            called["saved_task_id"] = self.task_id

    task = FakeTask()
    mocker.patch.object(CollectModelService, "repair_host_cloud_snapshot")
    mocker.patch(
        "apps.cmdb.services.collect_service.sync_collect_task",
        side_effect=lambda task_id, execution_id=None: called.update(
            {"sync_task_id": task_id, "sync_execution_id": execution_id}
        ),
    )
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")

    CollectModelService.exec_task(task, operator="tester")

    assert called["saved_status"] == CollectRunStatusType.RUNNING
    assert called["saved_task_id"]
    assert called["sync_task_id"] == task.id
    assert called["sync_execution_id"] == called["saved_task_id"]


class TestListRegions:
    def test_成功路径(self, mocker):
        sg = mocker.MagicMock()
        sg.list_regions.return_value = {
            "success": True,
            "regions": {"success": True, "result": [{"Region": "ap-1"}]},
        }
        mocker.patch(
            "apps.cmdb.services.collect_service.Stargazer", return_value=sg
        )
        out = CollectModelService.list_regions(
            {"model_id": "qcloud"}, "tencent"
        )
        assert out["success"] is True
        assert out["result"][0]["resource_id"] == "ap-1"

    def test_失败路径(self, mocker):
        sg = mocker.MagicMock()
        sg.list_regions.return_value = {
            "success": False,
            "regions": {"success": False, "result": [], "message": "鉴权失败"},
        }
        mocker.patch(
            "apps.cmdb.services.collect_service.Stargazer", return_value=sg
        )
        out = CollectModelService.list_regions({"model_id": "aws"}, "aws")
        assert out["success"] is False
        assert out["message"] == "鉴权失败"

    def test_format_params_基本结构(self):
        data = {
            "name": "task1",
            "task_type": "host",
            "driver_type": "snmp",
            "model_id": "host",
            "timeout": 60,
            "input_method": 0,
            "team": [1],
            "scan_cycle": {"value_type": "cycle", "value": "10"},
            "access_point": [{"id": "n1"}],
        }
        params, is_interval, scan_cycle = CollectModelService.format_params(data)
        assert params["name"] == "task1"
        assert params["is_interval"] is True
        assert params["cycle_value"] == "10"
        assert params["access_point"] == [{"id": "n1"}]
        assert is_interval is True
        assert scan_cycle == "*/10 * * * *"

    def test_format_params_close_无周期(self):
        data = {
            "name": "t",
            "task_type": "host",
            "driver_type": "d",
            "model_id": "host",
            "timeout": 1,
            "input_method": 0,
            "team": [1],
            "scan_cycle": {"value_type": "close", "value": ""},
        }
        params, is_interval, scan_cycle = CollectModelService.format_params(data)
        assert is_interval is False
        assert "scan_cycle" not in params

    def test_format_params_cycle_最小一分钟(self):
        data = {
            "name": "task1",
            "task_type": "host",
            "driver_type": "snmp",
            "model_id": "host",
            "timeout": 60,
            "input_method": 0,
            "team": [1],
            "scan_cycle": {"value_type": "cycle", "value": "1"},
        }
        params, is_interval, scan_cycle = CollectModelService.format_params(data)
        assert params["cycle_value"] == "1"
        assert is_interval is True
        assert scan_cycle == "*/1 * * * *"

    def test_format_params_cycle_小于一分钟报错(self):
        data = {
            "name": "task1",
            "task_type": "host",
            "driver_type": "snmp",
            "model_id": "host",
            "timeout": 60,
            "input_method": 0,
            "team": [1],
            "scan_cycle": {"value_type": "cycle", "value": "0"},
        }
        with pytest.raises(BaseAppException, match="周期任务最小执行间隔为1分钟"):
            CollectModelService.format_params(data)


class TestCollectCrudSideEffects:
    def test_create_事务内后续失败不提前同步外部副作用(self, mocker):
        patch_transaction_callbacks(mocker)
        instance = collect_instance()
        view = FakeCollectView(instance)
        request = fake_request(collect_payload())
        mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload", return_value=False)
        create_task = mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task")
        push_node_params = mocker.patch.object(CollectModelService, "push_butch_node_params")
        mocker.patch("apps.cmdb.services.collect_service.create_change_record", side_effect=RuntimeError("db failed"))

        with pytest.raises(RuntimeError, match="db failed"):
            CollectModelService.create(request, view)

        create_task.assert_not_called()
        push_node_params.assert_not_called()

    def test_create_事务提交后才同步外部副作用(self, mocker):
        callbacks = patch_transaction_callbacks(mocker)
        instance = collect_instance()
        view = FakeCollectView(instance)
        request = fake_request(collect_payload())
        mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload", return_value=False)
        mocker.patch("apps.cmdb.services.collect_service.create_change_record")
        create_task = mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task")
        push_node_params = mocker.patch.object(CollectModelService, "push_butch_node_params")

        assert CollectModelService.create(request, view) == instance.id

        assert len(callbacks) == 1
        create_task.assert_not_called()
        push_node_params.assert_not_called()
        callbacks[0]()
        create_task.assert_called_once()
        push_node_params.assert_called_once_with(instance)

    def test_update_事务内后续失败不提前同步外部副作用(self, mocker):
        patch_transaction_callbacks(mocker)
        instance = collect_instance()
        view = FakeCollectView(instance)
        request = fake_request(collect_payload())
        mocker.patch.object(CollectModelService, "has_permission")
        mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload", return_value=False)
        mocker.patch("apps.cmdb.services.collect_service.CollectHitStateService.clear_by_credential_ids", return_value=0)
        create_task = mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task")
        delete_task = mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task")
        delete_node_params = mocker.patch.object(CollectModelService, "delete_butch_node_params")
        push_node_params = mocker.patch.object(CollectModelService, "push_butch_node_params")
        mocker.patch("apps.cmdb.services.collect_service.create_change_record", side_effect=RuntimeError("db failed"))

        with pytest.raises(RuntimeError, match="db failed"):
            CollectModelService.update(request, view)

        create_task.assert_not_called()
        delete_task.assert_not_called()
        delete_node_params.assert_not_called()
        push_node_params.assert_not_called()

    def test_update_事务提交后才同步外部副作用(self, mocker):
        callbacks = patch_transaction_callbacks(mocker)
        instance = collect_instance()
        view = FakeCollectView(instance)
        request = fake_request(collect_payload())
        mocker.patch.object(CollectModelService, "has_permission")
        mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload", return_value=False)
        mocker.patch("apps.cmdb.services.collect_service.CollectHitStateService.clear_by_credential_ids", return_value=0)
        mocker.patch("apps.cmdb.services.collect_service.create_change_record")
        create_task = mocker.patch("apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task")
        delete_node_params = mocker.patch.object(CollectModelService, "delete_butch_node_params")
        push_node_params = mocker.patch.object(CollectModelService, "push_butch_node_params")

        assert CollectModelService.update(request, view) == instance.id

        assert len(callbacks) == 1
        create_task.assert_not_called()
        delete_node_params.assert_not_called()
        push_node_params.assert_not_called()
        callbacks[0]()
        create_task.assert_called_once()
        delete_node_params.assert_called_once()
        push_node_params.assert_called_once_with(instance)

    def test_destroy_外部清理失败时保留数据库删除入口可重试(self, mocker):
        patch_transaction_callbacks(mocker)
        delete_calls = []
        instance = collect_instance(delete=lambda: delete_calls.append("deleted"))
        view = FakeCollectView(instance)
        request = fake_request({})
        mocker.patch.object(CollectModelService, "has_permission")
        mocker.patch(
            "apps.cmdb.services.collect_service.CeleryUtils.delete_periodic_task",
            side_effect=RuntimeError("beat failed"),
        )

        with pytest.raises(BaseAppException, match="删除采集任务失败"):
            CollectModelService.destroy(request, view)

        assert delete_calls == []
