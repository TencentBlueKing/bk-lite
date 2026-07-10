"""cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService 辅助逻辑测试。

聚焦未覆盖的纯逻辑与序列化封装（仅 mock NodeMgmt RPC 边界）：
- 计数/分桶规范化：_safe_count / _normalize_detail_bucket / _sanitize_raw_data_item；
- 展示规范化：_normalize_display_message（含 legacy 字段/success 推导）、
  _normalize_display_detail（raw_data 派生）、_has_display_data；
- 杂项纯函数：_build_cycle / _normalize_org_ids / _safe_int / _extract_nodes /
  _group_nodes_by_region / _system_code / _task_name / _build_scan_cycle /
  _collect_status_to_text / _normalize_sync_snapshot / _should_repush... ；
- RPC 封装：_cloud_region_name_map / _fetch_non_container_nodes / _pick_access_point；
- DB 序列化：serialize_task / serialize_run（None 与有值）/ get_task 建档。
"""
import pydantic.root_model  # noqa

import types

import pytest

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig, NodeMgmtSyncRun
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService as S


class TestPureHelpers:
    pytestmark = pytest.mark.unit

    def test_safe_count(self):
        assert S._safe_count("3") == 3
        assert S._safe_count(None) == 0
        assert S._safe_count("bad") == 0

    def test_safe_int(self):
        assert S._safe_int("9") == 9
        assert S._safe_int(None) is None
        assert S._safe_int("x") is None

    def test_build_cycle(self):
        assert S._build_cycle(5) == "*/5 * * * *"

    def test_normalize_org_ids_去重排序跳过非法(self):
        assert S._normalize_org_ids([3, "1", "x", 1, None]) == [1, 3]
        assert S._normalize_org_ids(None) == []

    def test_extract_nodes(self):
        assert S._extract_nodes({"nodes": [{"a": 1}, "skip"]}) == [{"a": 1}]
        assert S._extract_nodes([{"b": 2}, 5]) == [{"b": 2}]
        assert S._extract_nodes("bad") == []

    def test_group_nodes_by_region(self):
        nodes = [
            {"cloud_region_id": 1, "id": "a"},
            {"cloud_region_id": 1, "id": "b"},
            {"cloud_region_id": "", "id": "c"},
        ]
        grouped = S._group_nodes_by_region(nodes)
        assert set(grouped.keys()) == {1}
        assert len(grouped[1]) == 2

    def test_system_code_task_name(self):
        assert S._system_code(7) == "node_mgmt_sync_host_collect_7"
        assert S._task_name("华东", 7) == "节点管理主机自动采集-华东"
        assert S._task_name("", 7) == "节点管理主机自动采集-7"

    def test_build_scan_cycle(self):
        assert S._build_scan_cycle(30) == {"value_type": "cycle", "value": 30}

    def test_collect_status_to_text(self):
        assert S._collect_status_to_text(CollectRunStatusType.SUCCESS) == "success"
        assert S._collect_status_to_text(CollectRunStatusType.ERROR) == "error"
        assert S._collect_status_to_text(999) == "unknown"

    def test_sanitize_raw_data_item_默认model_id(self):
        out = S._sanitize_raw_data_item({"inst_name": "h1", "ip": "1.1.1.1"})
        assert out["model_id"] == "host"
        assert out["inst_name"] == "h1"
        # 仅保留白名单字段
        assert "secret" not in S._sanitize_raw_data_item({"secret": "x", "id": 1})

    def test_normalize_detail_bucket(self):
        # dict 形态
        out = S._normalize_detail_bucket({"data": [{"id": 1}, "raw"]})
        assert out["count"] == 2
        # list 形态
        out2 = S._normalize_detail_bucket([{"id": 2}])
        assert out2["count"] == 1
        # 非法形态
        assert S._normalize_detail_bucket(None) == {"data": [], "count": 0}


class TestNormalizeDisplay:
    pytestmark = pytest.mark.unit

    def test_message_legacy字段与success推导(self):
        summary = {
            "all": 10,
            "add_count": 4,
            "add_error": 1,
            "update": 2,
            "conflict_count": 3,
            "message": "ok",
        }
        msg = S._normalize_display_message(summary)
        assert msg["all"] == 10
        assert msg["add"] == 4
        assert msg["add_error"] == 1
        # success = add - add_error
        assert msg["add_success"] == 3
        assert msg["association"] == 3
        assert msg["message"] == "ok"

    def test_message_显式success优先(self):
        msg = S._normalize_display_message({"add": 5, "add_error": 1, "add_success": 9})
        assert msg["add_success"] == 9

    def test_message_非dict返回空结构(self):
        msg = S._normalize_display_message("bad")
        assert msg["all"] == 0

    def test_detail_raw_data派生自其他桶(self):
        detail = {
            "add": {"data": [{"id": 1}], "count": 1},
            "update": [{"id": 2}],
            "association": {"data": [{"id": 3}]},
        }
        out = S._normalize_display_detail(detail)
        # relation 取自 association 别名
        assert out["relation"]["count"] == 1
        # raw_data 为空 -> 派生 add+update+delete+relation
        assert out["raw_data"]["count"] == 3

    def test_detail_显式raw_data不派生(self):
        detail = {
            "add": {"data": [{"id": 1}]},
            "raw_data": {"data": [{"id": 9}, {"id": 10}]},
        }
        out = S._normalize_display_detail(detail)
        assert out["raw_data"]["count"] == 2

    def test_detail_todo保留列表(self):
        out = S._normalize_display_detail({"todo": [{"x": 1}]})
        assert out["todo"] == [{"x": 1}]
        out2 = S._normalize_display_detail({"todo": "bad"})
        assert out2["todo"] == []

    def test_has_display_data(self):
        assert S._has_display_data({"add": {"count": 1}}) is True
        assert S._has_display_data({"todo": [1]}) is True
        assert S._has_display_data({"add": {"count": 0}}) is False
        assert S._has_display_data(None) is False


class TestSnapshotAndRepush:
    pytestmark = pytest.mark.unit

    def test_normalize_sync_snapshot_排序稳定(self):
        payload = {"b": [{"id": "2"}, {"id": "1"}], "a": 1}
        out = S._normalize_sync_snapshot(payload)
        # key 排序
        assert list(out.keys()) == ["a", "b"]
        # 同构 dict 列表按 id 排序
        assert out["b"][0]["id"] == "1"

    def test_normalize_sync_snapshot_混合列表不排序(self):
        out = S._normalize_sync_snapshot([{"id": "1"}, "raw"])
        assert out == [{"id": "1"}, "raw"]

    def test_should_repush_检测变更(self):
        old = types.SimpleNamespace(instances=[{"id": "1"}], access_point=[])
        same = types.SimpleNamespace(instances=[{"id": "1"}], access_point=[])
        diff = types.SimpleNamespace(instances=[{"id": "2"}], access_point=[])
        assert S._should_repush_collect_task_node_params(old, same) is False
        assert S._should_repush_collect_task_node_params(old, diff) is True


class TestRpcWrappers:
    pytestmark = pytest.mark.unit

    def test_cloud_region_name_map(self, mocker):
        rpc = mocker.MagicMock()
        rpc.cloud_region_list.return_value = [
            {"id": 1, "name": " 华东 "},
            {"id": "x", "name": "bad"},  # 非法 id 跳过
            "notdict",
        ]
        mocker.patch.object(S, "_node_mgmt_client", return_value=rpc)
        out = S._cloud_region_name_map()
        assert out == {1: "华东"}

    def test_fetch_non_container_nodes_过滤无云区域(self, mocker):
        rpc = mocker.MagicMock()
        rpc.cloud_region_list.return_value = [{"id": 1, "name": "华东"}]
        rpc.node_list.return_value = {
            "nodes": [
                {"id": "n1", "name": "host1", "ip": "1.1.1.1", "cloud_region_id": 1,
                 "operating_system": "linux", "organization": [10]},
                {"id": "n2", "name": "host2", "ip": "2.2.2.2"},  # 无云区域被跳过
            ]
        }
        mocker.patch.object(S, "_node_mgmt_client", return_value=rpc)
        out = S._fetch_non_container_nodes()
        assert len(out) == 1
        node = out[0]
        assert node["id"] == "n1"
        assert node["cloud_region_name"] == "华东"
        assert node["os_type"] == "linux"
        assert node["organization_ids"] == [10]
        assert node["model_id"] == "host"

    def test_pick_access_point_无容器节点返回None(self, mocker):
        rpc = mocker.MagicMock()
        rpc.cloud_region_list.return_value = [{"id": 1, "name": "华东"}]
        rpc.node_list.return_value = {"nodes": []}
        mocker.patch.object(S, "_node_mgmt_client", return_value=rpc)
        assert S._pick_access_point(1) is None

    def test_pick_access_point_选最新updated_at(self, mocker):
        rpc = mocker.MagicMock()
        rpc.cloud_region_list.return_value = [{"id": 1, "name": "华东"}]
        rpc.node_list.return_value = {
            "nodes": [
                {"id": "c1", "name": "old", "updated_at": "2026-01-01"},
                {"id": "c2", "name": "new", "updated_at": "2026-06-01"},
            ]
        }
        mocker.patch.object(S, "_node_mgmt_client", return_value=rpc)
        ap = S._pick_access_point(1)
        assert ap["id"] == "c2"
        assert ap["cloud"] == 1
        assert ap["cloud_name"] == "华东"


class TestDbSerialization:
    pytestmark = pytest.mark.django_db

    def test_get_task_创建内置(self):
        task = S.get_task()
        assert task.is_builtin is True
        assert task.name == S.TASK_NAME
        # 幂等：第二次返回同一条
        assert S.get_task().id == task.id

    def test_serialize_task_字段完整(self):
        task = NodeMgmtSyncConfig.objects.create(
            name="同步", is_builtin=True, auto_sync_enabled=True,
            auto_collect_enabled=False, sync_interval_minutes=5,
            collect_interval_minutes=30,
        )
        out = S.serialize_task(task)
        assert out["id"] == task.id
        assert out["auto_collect_enabled"] is False
        assert out["sync_interval_minutes"] == 5
        assert out["last_sync_at"] is None

    def test_serialize_run_none默认结构(self):
        out = S.serialize_run(None)
        assert out["id"] is None
        assert out["status"] is None
        assert out["message"]["all"] == 0
        assert out["detail"]["add"]["count"] == 0

    def test_serialize_run_有值(self):
        task = S.get_task()
        run = NodeMgmtSyncRun.objects.create(
            task=task,
            run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
            status=NodeMgmtSyncRun.STATUS_SUCCESS,
            summary_json={"all": 3, "add": 2, "add_error": 0},
            detail_json={"add": {"data": [{"id": 1}]}},
            error_message="",
        )
        out = S.serialize_run(run)
        assert out["id"] == run.id
        assert out["run_type"] == "sync"
        assert out["status"] == "success"
        assert out["message"]["all"] == 3
        assert out["message"]["add_success"] == 2
        assert out["detail"]["add"]["count"] == 1

    def test_get_latest_run_payload_无记录(self):
        out = S.get_latest_run_payload(NodeMgmtSyncRun.RUN_TYPE_COLLECT)
        assert out["id"] is None

    def test_mark_run_failed_写入失败状态(self):
        task = S.get_task()
        run = NodeMgmtSyncRun.objects.create(
            task=task,
            run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
            status=NodeMgmtSyncRun.STATUS_RUNNING,
        )
        S._mark_run_failed(run, RuntimeError("接口超时"))
        run.refresh_from_db()
        assert run.status == NodeMgmtSyncRun.STATUS_FAILED
        assert "采集失败" in run.error_message
        assert "接口超时" in run.error_message
        assert run.finished_at is not None
