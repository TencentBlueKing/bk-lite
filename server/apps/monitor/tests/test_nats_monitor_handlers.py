"""nats.monitor 注册处理器规格测试（直接调用处理器函数）。

外部权限/VM 边界 mock；DB 走真实模型断言查询结果。
"""

import threading
import time
from types import SimpleNamespace

import pytest
from django.conf import settings

from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject, MonitorObjectType
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyOrganization
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.nats import monitor as nm
from apps.monitor.nats.contracts import MONITOR_NATS_HANDLER_NAMES
from apps.monitor.services.metrics import MetricsQueryBudgetExceeded
from nats_client.registry import default_registry

pytestmark = pytest.mark.django_db


EXPECTED_MONITOR_NATS_HANDLER_NAMES = frozenset(
    {
        "create_metric",
        "create_metric_group",
        "create_monitor_object",
        "create_monitor_object_type",
        "create_monitor_plugin",
        "create_monitor_policy",
        "delete_monitor_policy",
        "get_host_instance_list",
        "get_host_metric_range",
        "get_host_resource_snapshot",
        "get_host_resource_top",
        "get_monitor_statistics",
        "get_network_device_resource_top",
        "monitor_ingest_from_source",
        "monitor_instance_metrics",
        "monitor_metrics",
        "monitor_object_instance_count",
        "monitor_object_instances",
        "monitor_objects",
        "query_latest_active_alerts",
        "query_latest_interface_metrics",
        "query_monitor_alert_segments",
        "query_monitor_data_by_metric",
        "query_metric_range_scoped",
        "search_monitor_policies",
    }
)
MONITOR_NATS_PERMISSION_HANDLER_NAMES = frozenset(
    {
        "get_monitor_module_data",
        "get_monitor_module_list",
    }
)


@pytest.fixture(autouse=True)
def authorized_current_team_scope(mocker):
    """既有 handler 规格默认提供一个经 Task1 RPC 认证的当前组织。"""
    return mocker.patch(
        "apps.monitor.nats.monitor.SystemMgmt.get_authorized_groups_scoped",
        side_effect=lambda actor_context, include_children=False: {
            "result": True,
            "data": [actor_context["current_team"]],
            "is_superuser": False,
        },
    )


@pytest.mark.unit
def test_monitor_nats_handler_contract_lists_all_existing_handlers():
    assert MONITOR_NATS_HANDLER_NAMES == EXPECTED_MONITOR_NATS_HANDLER_NAMES


@pytest.mark.unit
def test_monitor_nats_handler_contract_matches_runtime_registry():
    runtime_handler_names = {
        registration["name"]
        for registration in default_registry.registry.values()
        if registration["func"].__module__.startswith("apps.monitor.nats.")
    }
    expected_subjects = {f"{settings.NATS_NAMESPACE}.{handler_name}" for handler_name in MONITOR_NATS_HANDLER_NAMES}

    assert runtime_handler_names - MONITOR_NATS_PERMISSION_HANDLER_NAMES == MONITOR_NATS_HANDLER_NAMES
    assert expected_subjects <= default_registry.registry.keys()


class TestMonitorObjectsHandler:
    def test_returns_all_objects(self):
        MonitorObject.objects.create(name="NMObj1", level="base")
        MonitorObject.objects.create(name="NMObj2", level="base")
        out = nm.monitor_objects()
        assert out["result"] is True
        names = {o["name"] for o in out["data"]}
        assert {"NMObj1", "NMObj2"} <= names


class TestMonitorObjectInstanceCount:
    def test_counts_per_object(self):
        obj = MonitorObject.objects.create(name="NMCntObj", level="base")
        MonitorInstance.objects.create(id="('a',)", name="a", monitor_object=obj)
        MonitorInstance.objects.create(id="('b',)", name="b", monitor_object=obj)
        MonitorInstance.objects.create(id="('c',)", name="c", monitor_object=obj, is_deleted=True)
        out = nm.monitor_object_instance_count()
        assert out["data"]["NMCntObj"] == 2


class TestMonitorMetricsHandler:
    def test_missing_object(self):
        out = nm.monitor_metrics(999999)
        assert out["result"] is False

    def test_returns_metrics(self):
        obj = MonitorObject.objects.create(name="NMMObj", level="base")
        plugin = MonitorPlugin.objects.create(name="NMMPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        Metric.objects.create(
            monitor_object=obj,
            monitor_plugin=plugin,
            metric_group=group,
            name="cpu",
            display_name="CPU",
            description="d",
        )
        out = nm.monitor_metrics(obj.id, user_info={"locale": "en"})
        assert out["result"] is True
        assert any(m["name"] == "cpu" for m in out["data"])
        assert next(m for m in out["data"] if m["name"] == "cpu")["monitor_plugin_name"] == "NMMPlugin"


class TestMonitorObjectInstancesHandler:
    def test_missing_object(self):
        out = nm.monitor_object_instances(999999, user_info={})
        assert out["result"] is False

    def test_missing_user_info_returns_error(self):
        obj = MonitorObject.objects.create(name="NMIObj", level="base")
        out = nm.monitor_object_instances(obj.id, user_info={})
        assert out["result"] is False
        assert "缺少用户" in out["message"]

    def test_returns_authorized_instances(self, mocker):
        obj = MonitorObject.objects.create(name="NMIObj2", level="base")
        MonitorInstance.objects.create(
            id="('h1',)",
            name="h1",
            monitor_object=obj,
            is_active=True,
            is_deleted=False,
        )
        mocker.patch(
            "apps.monitor.nats.monitor.get_permission_rules",
            return_value={"team": [1], "instance": [{"id": "('h1',)", "permission": ["View"]}]},
        )
        # permission_filter 返回全部（团队匹配走 id_key/team_key），简单返回原 qs
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )
        out = nm.monitor_object_instances(
            obj.id,
            user_info={"user": SimpleNamespace(username="u", domain="domain.com"), "team": 1},
        )
        assert out["result"] is True
        assert out["data"][0]["id"] == "('h1',)"
        assert out["data"][0]["permission"] == ["View"]


class TestHostResourceTop:
    def test_returns_ranked_rows_for_metric_type(self, mocker):
        instance = SimpleNamespace(id="host-1", name="host-1", ip="10.0.0.1", interval=300)
        mocker.patch(
            "apps.monitor.nats.monitor._get_nats_actor_scope",
            return_value=(None, 1, False, frozenset({1}), False, None),
        )
        mocker.patch(
            "apps.monitor.nats.monitor._get_authorized_monitor_instances",
            return_value=({"host-1": instance}, None),
        )
        vm = mocker.patch("apps.monitor.nats.monitor.VictoriaMetricsAPI")
        vm.return_value.query.return_value = {
            "status": "success",
            "data": {"result": [{"metric": {"instance_id": "host-1"}, "value": [time.time(), "58"]}]},
        }

        out = nm.get_host_resource_top("cpu", user_info={"user": "u", "team": 1})

        assert out["result"] is True
        assert out["data"][0]["usage_percent"] == 42.0

    def test_rejects_invalid_metric_type_without_query(self, mocker):
        vm = mocker.patch("apps.monitor.nats.monitor.VictoriaMetricsAPI")

        out = nm.get_host_resource_top("network", user_info={"user": "u", "team": 1})

        assert out["result"] is False
        vm.assert_not_called()


class TestQueryMetricRangeScoped:
    def test_success(self, mocker):
        service = mocker.patch("apps.monitor.nats.monitor.AuthorizedMetricQueryService")
        service.return_value.query_range.return_value = {
            "status": "success",
            "data": {"result": [{"values": [[1, "10"], [2, "20"]]}]},
        }
        out = nm.query_metric_range_scoped(
            8,
            42,
            ["host-1"],
            ["2026-01-01T00:00:00.000Z", "2026-01-01T00:10:00.000Z"],
            user_info={"user": "viewer", "domain": "domain.com", "team": 1},
        )

        assert out["result"] is True
        assert out["data"] == [{"name": 1, "value": "10"}, {"name": 2, "value": "20"}]
        service.return_value.query_range.assert_called_once()

    def test_failure(self, mocker):
        service = mocker.patch("apps.monitor.nats.monitor.AuthorizedMetricQueryService")
        service.return_value.query_range.return_value = {"status": "error", "message": "down"}
        out = nm.query_metric_range_scoped(
            8,
            42,
            ["host-1"],
            ["2026-01-01T00:00:00.000Z", "2026-01-01T00:10:00.000Z"],
            user_info={"user": "viewer", "domain": "domain.com", "team": 1},
        )
        assert out["result"] is False

    @pytest.mark.integration
    @pytest.mark.parametrize(
        "time_range",
        [
            ["2026-01-01 00:00:00", "2026-01-01T00:10:00Z"],
            ["2026-01-01T00:00:00Z"],
        ],
    )
    def test_invalid_time_range_returns_error_without_query(self, mocker, time_range):
        service = mocker.patch("apps.monitor.nats.monitor.AuthorizedMetricQueryService")

        result = nm.query_metric_range_scoped(8, 42, ["host-1"], time_range)

        assert result["result"] is False
        assert result["data"] == []
        assert "time range" in result["message"]
        service.assert_not_called()

    def test_budget_error_returns_stable_nats_contract(self, mocker):
        error = MetricsQueryBudgetExceeded(
            data={
                "code": "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED",
                "reason": "points_per_series",
                "limits": {"points_per_series": 10000},
                "actual": {"points_per_series": 20000},
            }
        )
        service = mocker.patch("apps.monitor.nats.monitor.AuthorizedMetricQueryService")
        service.return_value.query_range.side_effect = error

        result = nm.query_metric_range_scoped(
            8,
            42,
            ["host-1"],
            ["2026-01-01T00:00:00.000Z", "2026-01-02T00:00:00.000Z"],
            step="1s",
            user_info={"user": "viewer", "domain": "domain.com", "team": 1},
        )

        assert result == {
            "result": False,
            "data": [],
            "message": "指标范围查询超过服务端预算，请缩短时间范围、减少实例或增大查询步长",
            "code": "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED",
            "budget": error.data,
        }


class TestQueryMonitorDataByMetric:
    def _setup(self):
        obj = MonitorObject.objects.create(name="QMDObj", level="base")
        plugin = MonitorPlugin.objects.create(name="QMDPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        metric = Metric.objects.create(
            monitor_object=obj,
            monitor_plugin=plugin,
            metric_group=group,
            name="cpu",
            query="cpu{__$labels__}",
            instance_id_keys=["instance_id"],
            dimensions=[],
        )
        return obj, metric

    def test_missing_required_field(self):
        out = nm.query_monitor_data_by_metric({"monitor_obj_id": 1})
        assert out["result"] is False
        assert "缺少必要参数" in out["message"]

    def test_instance_ids_must_be_list(self):
        out = nm.query_monitor_data_by_metric(
            {"monitor_obj_id": 1, "metric": "cpu", "start": 1, "end": 2, "instance_ids": "x"},
        )
        assert out["result"] is False
        assert "instance_ids" in out["message"]

    def test_missing_user_info(self):
        out = nm.query_monitor_data_by_metric(
            {"monitor_obj_id": 1, "metric": "cpu", "start": 1, "end": 2, "instance_ids": ["host-1"]},
            user_info={},
        )
        assert out["result"] is False

    def test_empty_instance_ids_fail_closed(self, mocker):
        vm = mocker.patch("apps.monitor.nats.monitor.Metrics.get_metrics_range")
        out = nm.query_monitor_data_by_metric(
            {"monitor_obj_id": 1, "metric": "cpu", "start": 1, "end": 2, "instance_ids": []},
            user_info={"user": "viewer", "team": 1},
        )
        assert out["result"] is False
        assert "instance_ids" in out["message"]
        vm.assert_not_called()

    def test_object_or_metric_not_found(self, mocker):
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        out = nm.query_monitor_data_by_metric(
            {"monitor_obj_id": 999999, "metric": "cpu", "start": 1, "end": 2, "instance_ids": ["host-1"]},
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )
        assert out["result"] is False
        assert "不存在" in out["message"]

    def test_success_returns_filtered_data(self, mocker):
        obj, metric = self._setup()
        MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj, is_deleted=False)
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )
        mocker.patch(
            "apps.monitor.nats.monitor.Metrics.get_metrics_range",
            return_value={
                "data": {
                    "result": [
                        {"metric": {"instance_id": "('h1',)"}, "values": [[0, "1"]]},
                        {"metric": {"instance_id": "('other',)"}, "values": [[0, "2"]]},
                    ]
                }
            },
        )
        out = nm.query_monitor_data_by_metric(
            {"monitor_obj_id": obj.id, "metric": "cpu", "start": 1, "end": 2, "instance_ids": ["('h1',)"]},
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )
        assert out["result"] is True
        ids = {d["metric"]["instance_id"] for d in out["data"]["data"]["result"]}
        # 只保留有权限实例 ('h1',)
        assert ids == {"('h1',)"}

    def test_budget_error_keeps_structured_failure(self, mocker):
        obj, _ = self._setup()
        MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj, is_deleted=False)
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )
        error = MetricsQueryBudgetExceeded(
            data={
                "code": "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED",
                "reason": "total_points",
                "limits": {"total_points": 500000},
                "actual": {"total_points": 500001},
            }
        )
        mocker.patch(
            "apps.monitor.nats.monitor.Metrics.get_metrics_range",
            side_effect=error,
        )

        result = nm.query_monitor_data_by_metric(
            {"monitor_obj_id": obj.id, "metric": "cpu", "start": 1, "end": 2, "instance_ids": ["('h1',)"]},
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )

        assert result["result"] is False
        assert result["code"] == "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED"
        assert result["budget"] == error.data

    def test_merged_plugin_result_checks_shared_fill_budget(self, mocker):
        obj, _ = self._setup()
        MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj, is_deleted=False)
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )
        get_metrics_range = mocker.patch(
            "apps.monitor.nats.monitor.Metrics.get_metrics_range",
            return_value={
                "status": "success",
                "data": {
                    "result": [
                        {"metric": {"instance_id": "('h1',)"}, "values": [[0, "1"]]},
                    ]
                },
            },
        )
        error = MetricsQueryBudgetExceeded(
            data={
                "code": "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED",
                "reason": "total_points",
                "limits": {"total_points": 500000},
                "actual": {"total_points": 500001},
            }
        )
        enforce_fill_budget = mocker.patch(
            "apps.monitor.nats.monitor.Metrics.enforce_fill_budget",
            side_effect=error,
        )

        result = nm.query_monitor_data_by_metric(
            {"monitor_obj_id": obj.id, "metric": "cpu", "start": 1, "end": 2, "instance_ids": ["('h1',)"]},
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )

        assert result["code"] == "MONITOR_RANGE_QUERY_BUDGET_EXCEEDED"
        assert get_metrics_range.call_args.kwargs["fill_missing"] is False
        enforce_fill_budget.assert_called_once()

    def test_same_metric_name_queries_all_plugins_and_returns_plugin_metadata(
        self,
        mocker,
    ):
        obj, first_metric = self._setup()
        first_metric.query = "plugin_a_cpu{__$labels__}"
        first_metric.save(update_fields=["query"])

        second_plugin = MonitorPlugin.objects.create(
            name="QMDPluginB",
            display_name="Plugin B",
            template_id="qmd-plugin-b",
            template_type="api",
            collector="telegraf",
            collect_type="http",
        )
        second_group = MetricGroup.objects.create(
            monitor_object=obj,
            monitor_plugin=second_plugin,
            name="g",
        )
        second_metric = Metric.objects.create(
            monitor_object=obj,
            monitor_plugin=second_plugin,
            metric_group=second_group,
            name="cpu",
            query="plugin_b_cpu{__$labels__}",
            instance_id_keys=["instance_id"],
            dimensions=[],
        )
        MonitorInstance.objects.create(
            id="('h1',)",
            name="h1",
            monitor_object=obj,
            is_deleted=False,
        )
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )

        def query_metric(query, *args, **kwargs):
            source = "plugin_a" if query.startswith("plugin_a_cpu") else "plugin_b"
            return {
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {"instance_id": "h1", "source": source},
                            "values": [[0, "1"]],
                        }
                    ],
                },
            }

        get_metrics_range = mocker.patch(
            "apps.monitor.nats.monitor.Metrics.get_metrics_range",
            side_effect=query_metric,
        )

        out = nm.query_monitor_data_by_metric(
            {"monitor_obj_id": obj.id, "metric": "cpu", "start": 1, "end": 2, "instance_ids": ["('h1',)"]},
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )

        assert out["result"] is True
        rows = out["data"]["data"]["result"]
        assert len(rows) == 2
        assert get_metrics_range.call_count == 2
        assert {row["metric_id"] for row in rows} == {first_metric.id, second_metric.id}
        plugins = {row["metric"]["source"]: row["monitor_plugin"] for row in rows}
        assert plugins["plugin_a"]["name"] == "QMDPlugin"
        assert plugins["plugin_b"] == {
            "id": second_plugin.id,
            "name": "QMDPluginB",
            "display_name": "Plugin B",
            "template_id": "qmd-plugin-b",
            "template_type": "api",
            "collector": "telegraf",
            "collect_type": "http",
        }


class TestMonitorInstanceMetrics:
    def test_missing_field(self):
        out = nm.monitor_instance_metrics({"monitor_obj_id": 1})
        assert out["result"] is False
        assert "缺少必要参数" in out["message"]

    def test_page_size_too_large(self):
        out = nm.monitor_instance_metrics(
            {"monitor_obj_id": 1, "instance_id": "('h1',)", "page_size": 1000},
        )
        assert out["result"] is False
        assert "page_size" in out["message"]

    def test_missing_user_info(self):
        out = nm.monitor_instance_metrics(
            {"monitor_obj_id": 1, "instance_id": "('h1',)"},
            user_info={},
        )
        assert out["result"] is False

    def test_success_lists_metrics(self, mocker):
        obj = MonitorObject.objects.create(name="MIMObj", level="base")
        plugin = MonitorPlugin.objects.create(name="MIMPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        Metric.objects.create(
            monitor_object=obj,
            monitor_plugin=plugin,
            metric_group=group,
            name="cpu",
            display_name="CPU",
            unit="percent",
            data_type="Number",
        )
        MonitorInstance.objects.create(
            id="('h1',)",
            name="h1",
            monitor_object=obj,
            is_active=True,
            is_deleted=False,
        )
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )
        out = nm.monitor_instance_metrics(
            {"monitor_obj_id": obj.id, "instance_id": "('h1',)"},
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )
        assert out["result"] is True
        assert out["data"]["count"] == 1
        assert out["data"]["items"][0]["metric"] == "cpu"

    def test_only_with_data_limits_vm_queries_to_current_page(self, mocker):
        obj = MonitorObject.objects.create(name="MIMObjPaged", level="base")
        plugin = MonitorPlugin.objects.create(name="MIMPluginPaged")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        for index, name in enumerate(["cpu", "mem", "disk"], start=1):
            Metric.objects.create(
                monitor_object=obj,
                monitor_plugin=plugin,
                metric_group=group,
                name=name,
                display_name=name.upper(),
                query=f'{name}{{instance_id="$instance_id"}}',
                sort_order=index,
            )
        MonitorInstance.objects.create(
            id="('h1',)",
            name="h1",
            monitor_object=obj,
            is_active=True,
            is_deleted=False,
        )
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )
        vm = mocker.patch("apps.monitor.nats.monitor.VictoriaMetricsAPI")
        vm.return_value.query_range.return_value = {"status": "success", "data": {"result": [{"values": [[1, "1"]]}]}}

        out = nm.monitor_instance_metrics(
            {
                "monitor_obj_id": obj.id,
                "instance_id": "('h1',)",
                "only_with_data": True,
                "page": 1,
                "page_size": 1,
            },
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )

        assert out["result"] is True
        assert out["data"]["count"] == 3
        assert [item["metric"] for item in out["data"]["items"]] == ["cpu"]
        assert vm.return_value.query_range.call_count == 1

    def test_only_with_data_queries_page_concurrently_and_preserves_order(self, mocker):
        obj = MonitorObject.objects.create(name="MIMObjConcurrent", level="base")
        plugin = MonitorPlugin.objects.create(name="MIMPluginConcurrent")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        for index in range(10):
            Metric.objects.create(
                monitor_object=obj,
                monitor_plugin=plugin,
                metric_group=group,
                name=f"metric_{index}",
                display_name=f"Metric {index}",
                query=f'metric_{index % 5}{{instance_id="$instance_id"}}',
                sort_order=index,
            )
        MonitorInstance.objects.create(
            id="('h1',)",
            name="h1",
            monitor_object=obj,
            is_active=True,
            is_deleted=False,
        )
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )

        lock = threading.Lock()
        active = 0
        peak_active = 0

        def query_range(query, *args):
            nonlocal active, peak_active
            with lock:
                active += 1
                peak_active = max(peak_active, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            if query.startswith("metric_4{"):
                raise RuntimeError("one metric unavailable")
            return {"status": "success", "data": {"result": [{"values": [[1, "1"]]}]}}

        vm = mocker.patch("apps.monitor.nats.monitor.VictoriaMetricsAPI")
        vm.return_value.query_range.side_effect = query_range

        out = nm.monitor_instance_metrics(
            {
                "monitor_obj_id": obj.id,
                "instance_id": "('h1',)",
                "only_with_data": True,
                "page": 1,
                "page_size": 10,
            },
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )

        assert out["result"] is True
        assert [item["metric"] for item in out["data"]["items"]] == [
            "metric_0",
            "metric_1",
            "metric_2",
            "metric_3",
            "metric_5",
            "metric_6",
            "metric_7",
            "metric_8",
        ]
        assert vm.return_value.query_range.call_count == 5
        assert 1 < peak_active <= 8

    def test_only_with_data_isolates_malformed_vm_response(self, mocker):
        obj = MonitorObject.objects.create(name="MIMObjMalformed", level="base")
        plugin = MonitorPlugin.objects.create(name="MIMPluginMalformed")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        Metric.objects.create(
            monitor_object=obj,
            monitor_plugin=plugin,
            metric_group=group,
            name="malformed",
            query='malformed{instance_id="$instance_id"}',
            sort_order=1,
        )
        Metric.objects.create(
            monitor_object=obj,
            monitor_plugin=plugin,
            metric_group=group,
            name="healthy",
            query='healthy{instance_id="$instance_id"}',
            sort_order=2,
        )
        MonitorInstance.objects.create(
            id="('h1',)",
            name="h1",
            monitor_object=obj,
            is_active=True,
            is_deleted=False,
        )
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )
        vm = mocker.patch("apps.monitor.nats.monitor.VictoriaMetricsAPI")
        vm.return_value.query_range.side_effect = lambda query, *args: (
            None if query.startswith("malformed{") else {"status": "success", "data": {"result": [{}]}}
        )

        out = nm.monitor_instance_metrics(
            {
                "monitor_obj_id": obj.id,
                "instance_id": "('h1',)",
                "only_with_data": True,
            },
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )

        assert out["result"] is True
        assert [item["metric"] for item in out["data"]["items"]] == ["healthy"]

    def test_instance_not_authorized(self, mocker):
        obj = MonitorObject.objects.create(name="MIMObj2", level="base")
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.none(),
        )
        out = nm.monitor_instance_metrics(
            {"monitor_obj_id": obj.id, "instance_id": "('missing',)"},
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )
        assert out["result"] is False


class TestQueryMonitorAlertSegments:
    def test_missing_field(self):
        out = nm.query_monitor_alert_segments({"monitor_obj_id": 1})
        assert out["result"] is False
        assert "缺少必要参数" in out["message"]

    def test_start_after_end(self):
        out = nm.query_monitor_alert_segments(
            {
                "monitor_obj_id": 1,
                "start": "2026-01-02 00:00:00",
                "end": "2026-01-01 00:00:00",
            },
            user_info={},
        )
        assert out["result"] is False
        assert "时间" in out["message"]

    def test_no_authorized_instances_returns_empty(self, mocker):
        obj = MonitorObject.objects.create(name="QMASObj", level="base")
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.none(),
        )
        out = nm.query_monitor_alert_segments(
            {
                "monitor_obj_id": obj.id,
                "start": "2026-01-01 00:00:00",
                "end": "2026-01-02 00:00:00",
            },
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )
        assert out["result"] is True
        assert out["data"]["count"] == 0

    def test_returns_alert_segments(self, mocker):
        from datetime import datetime, timezone

        from apps.monitor.models import MonitorAlert

        obj = MonitorObject.objects.create(name="QMASObj2", level="base")
        instance = MonitorInstance.objects.create(
            id="('h1',)",
            name="h1",
            monitor_object=obj,
            is_active=True,
            is_deleted=False,
        )
        MonitorInstanceOrganization.objects.create(
            monitor_instance=instance,
            organization=1,
        )
        policy = MonitorPolicy.objects.create(
            monitor_object=obj,
            name="segment-policy",
            algorithm="max",
            query_condition={},
            source={},
            group_by=[],
        )
        PolicyOrganization.objects.create(policy=policy, organization=1)
        MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id="('h1',)",
            status="new",
            level="critical",
            start_event_time=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
        )
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.get_permissions_rules",
            return_value={"data": {"all": {"team": [1]}}, "team": [1]},
        )
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )
        out = nm.query_monitor_alert_segments(
            {
                "monitor_obj_id": obj.id,
                "start": "2026-01-01 00:00:00",
                "end": "2026-01-02 00:00:00",
            },
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )
        assert out["result"] is True
        assert out["data"]["count"] == 1

    def test_paginates_before_building_segments(self, mocker):
        from datetime import datetime, timezone

        from apps.monitor.models import MonitorAlert

        obj = MonitorObject.objects.create(name="QMASObj3", level="base")
        instance = MonitorInstance.objects.create(
            id="('h1',)",
            name="h1",
            monitor_object=obj,
            is_active=True,
            is_deleted=False,
        )
        MonitorInstanceOrganization.objects.create(
            monitor_instance=instance,
            organization=1,
        )
        policies = []
        for idx, hour in enumerate([12, 11, 10], start=1):
            policy = MonitorPolicy.objects.create(
                monitor_object=obj,
                name=f"paged-segment-policy-{idx}",
                algorithm="max",
                query_condition={},
                source={},
                group_by=[],
            )
            PolicyOrganization.objects.create(policy=policy, organization=1)
            policies.append(policy)
            MonitorAlert.objects.create(
                policy_id=policy.id,
                monitor_instance_id="('h1',)",
                status="new",
                level="critical",
                start_event_time=datetime(2026, 1, 1, hour, tzinfo=timezone.utc),
            )
        mocker.patch("apps.monitor.nats.monitor.get_permission_rules", return_value={"team": [1]})
        mocker.patch(
            "apps.monitor.nats.monitor.get_permissions_rules",
            return_value={"data": {"all": {"team": [1]}}, "team": [1]},
        )
        mocker.patch(
            "apps.monitor.nats.monitor.permission_filter",
            side_effect=lambda model, perm, **kw: model.objects.all(),
        )
        build_segment = mocker.patch(
            "apps.monitor.nats.monitor._build_monitor_alert_segment",
            side_effect=nm._build_monitor_alert_segment,
        )

        out = nm.query_monitor_alert_segments(
            {
                "monitor_obj_id": obj.id,
                "start": "2026-01-01 00:00:00",
                "end": "2026-01-02 00:00:00",
                "page": 2,
                "page_size": 1,
            },
            user_info={"user": SimpleNamespace(username="u", domain="d"), "team": 1},
        )

        assert out["result"] is True
        assert out["data"]["count"] == 3
        assert out["data"]["page"] == 2
        assert out["data"]["page_size"] == 1
        assert len(out["data"]["items"]) == 1
        assert out["data"]["items"][0]["policy_id"] == policies[1].id
        assert build_segment.call_count == 1


class TestBuildMonitorAlertSegment:
    def test_computes_duration(self):
        from datetime import datetime, timezone

        alert = SimpleNamespace(
            id=1,
            policy_id=2,
            monitor_instance_id="('h1',)",
            monitor_instance_name="主机1",
            metric_instance_id="m1",
            level="critical",
            value=9.0,
            status="recovered",
            content="c",
            dimensions={},
            alert_type="alert",
            start_event_time=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_event_time=datetime(2026, 1, 1, 0, 5, 0, tzinfo=timezone.utc),
            created_at=None,
            updated_at=None,
        )
        seg = nm._build_monitor_alert_segment(alert)
        assert seg["duration_seconds"] == 300
        assert seg["id"] == 1 and seg["level"] == "critical"


class TestNatsPermissionContext:
    @pytest.mark.parametrize("team", [None, True, 1.0, "01", 0, -1])
    def test_invalid_current_team_fails_closed(self, team):
        _, _, _, error = nm._get_nats_permission_context(
            {
                "user": SimpleNamespace(username="u", domain="domain.com"),
                "team": team,
            },
            "policy",
        )

        assert error["result"] is False
        assert error["data"] == {}

    def test_string_actor_uses_explicit_domain(self, mocker):
        get_permissions = mocker.patch(
            "apps.monitor.nats.monitor.get_permissions_rules",
            return_value={"data": {}, "team": [1]},
        )

        _, scope_ids, _, error = nm._get_nats_permission_context(
            {
                "user": "tenant-user",
                "domain": "tenant.example",
                "team": 1,
                "include_children": False,
            },
            "policy",
        )

        assert error is None
        assert scope_ids == frozenset({1})
        actor = get_permissions.call_args.args[0]
        assert actor.username == "tenant-user"
        assert actor.domain == "tenant.example"


class TestGetMonitorStatistics:
    def test_superuser_counts_stay_in_current_team(self, mocker):
        obj = MonitorObject.objects.create(name="StatObj", level="base", is_visible=True)
        MonitorObjectType.objects.create(id="stattype", name="t")
        active = MonitorInstance.objects.create(id="('i1',)", name="i1", monitor_object=obj, is_active=True)
        inactive = MonitorInstance.objects.create(id="('i2',)", name="i2", monitor_object=obj, is_active=False)
        MonitorInstanceOrganization.objects.create(monitor_instance=active, organization=1)
        MonitorInstanceOrganization.objects.create(monitor_instance=inactive, organization=1)
        MonitorPlugin.objects.create(name="StatPlugin", is_pre=True)
        policy = MonitorPolicy.objects.create(
            monitor_object=obj,
            name="sp",
            algorithm="max",
            query_condition={},
            source={},
            group_by=[],
            enable=True,
            threshold=[{"method": ">", "value": 1, "level": "warning"}],
        )
        PolicyOrganization.objects.create(policy=policy, organization=1)
        mocker.patch(
            "apps.monitor.nats.monitor.get_permissions_rules",
            return_value={"data": {"all": {"team": [1]}}, "team": [1]},
        )

        out = nm.get_monitor_statistics(
            user_info={
                "user": SimpleNamespace(username="admin", domain="domain.com"),
                "team": 1,
                "is_superuser": True,
                "include_children": False,
            }
        )
        assert out["result"] is True
        data = out["data"]
        assert data["monitor_object_total"] >= 1
        assert data["monitor_instance_total"] == 2
        assert data["monitor_instance_active"] == 1
        assert data["monitor_instance_inactive"] == 1
        assert data["plugin_total"] >= 1
        assert data["policy_total"] == 1
        assert data["policy_enabled"] == 1
        assert data["policy_threshold"] == 1

    def test_missing_team_fails_closed(self):
        obj = MonitorObject.objects.create(name="StatObj2", level="base")
        MonitorInstance.objects.create(id="('z1',)", name="z1", monitor_object=obj)
        out = nm.get_monitor_statistics(user_info={"is_superuser": False, "team": None})
        assert out["result"] is False
        assert out["data"] == {}
