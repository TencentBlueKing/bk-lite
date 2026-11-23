"""采集和接口当前值：同一套过滤，查询出表，数量出一行。"""

import asyncio
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings

from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject, MonitorObjectType
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.collection_query import query_collection_rows
from apps.monitor.services.generic_query import GenericQueryError
from apps.monitor.services.interface_current import _rate_text, query_interface_current_rows

pytestmark = pytest.mark.django_db


def _object(name, type_id=None, **kwargs):
    monitor_type = None
    if type_id:
        monitor_type = MonitorObjectType.objects.create(id=type_id, name=kwargs.pop("type_name", type_id), order=1)
    return MonitorObject.objects.create(
        name=name,
        level="base",
        type=monitor_type,
        instance_id_keys=["instance_id"],
        **kwargs,
    )


def _instance(obj, raw_id, *, name="", active=True):
    return MonitorInstance.objects.create(
        id=str((raw_id,)),
        name=name or raw_id,
        monitor_object=obj,
        is_active=active,
        ip="10.0.0.8",
    )


def _plugin(obj, name, query):
    plugin = MonitorPlugin.objects.create(
        name=name,
        collector="collector",
        collect_type="snmp",
        status_query=query,
    )
    plugin.monitor_object.add(obj)
    return plugin


def _config(instance, plugin):
    CollectConfig.objects.create(
        id=f"cfg-{instance.id}-{plugin.id}",
        monitor_instance=instance,
        monitor_plugin=plugin,
        collector=plugin.collector,
        collect_type=plugin.collect_type,
        config_type=plugin.name,
        file_type="yaml",
    )


class _VM:
    def __init__(self, rows_by_marker):
        self.rows_by_marker = rows_by_marker

    def query(self, query, step=None):
        for marker, rows in self.rows_by_marker.items():
            if marker in query:
                return {"status": "success", "data": {"result": rows}}
        return {"status": "success", "data": {"result": []}}


def _sample(raw_id, stamp):
    return {"metric": {"instance_id": raw_id}, "value": [0, str(stamp)]}


def test_collection_rolls_plugins_into_one_row_and_sorts_by_last_sample():
    obj = _object("collect-host", "ctype-os", type_name="操作系统")
    fresh = _instance(obj, "web-1", name="web")
    stale = _instance(obj, "db-1", name="db")
    manual = _instance(obj, "manual-1", name="manual")
    alive = _plugin(obj, "collect-alive", "up{plugin='alive'}")
    dead = _plugin(obj, "collect-dead", "up{plugin='dead'}")
    _config(fresh, alive)
    _config(stale, alive)
    _config(stale, dead)
    now = time.time()
    vm = _VM(
        {
            "alive": [_sample("web-1", now), _sample("db-1", now - 700), _sample("manual-1", now - 30)],
            "dead": [],
        }
    )

    with override_settings(TIME_ZONE="Asia/Shanghai", USE_TZ=True):
        rows = query_collection_rows([fresh, stale, manual], vm_api=vm, order_by="last_sample_at", order_dir="desc")

    by_name = {row["name"]: row for row in rows}
    assert by_name["web"]["monitor_object_type"] == "操作系统"
    assert by_name["web"]["monitor_object_id"] == str(obj.id)
    assert by_name["web"]["monitor_object"] == "collect-host"
    assert by_name["web"]["monitor_object_name"] == "collect-host"
    assert by_name["web"]["collect_mode"] == "自动"
    assert by_name["web"]["collect_status"] == "正常"
    assert by_name["web"]["report_status"] == "正常"
    expected_sample = datetime.fromtimestamp(now, tz=timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    assert by_name["web"]["last_sample_at"] == expected_sample
    assert by_name["db"]["collect_status"] == "失联"
    assert by_name["db"]["report_status"] == "失联"
    assert by_name["db"]["collect_mode"] == "自动"
    assert by_name["manual"]["collect_mode"] == "手动"
    assert by_name["manual"]["collect_status"] == "正常"
    assert [row["name"] for row in rows] == ["web", "manual", "db"]
    offline = query_collection_rows([fresh, stale, manual], collect_status="offline", vm_api=vm)
    assert [row["name"] for row in offline] == ["db"]


def test_collection_count_ignores_the_unpaged_row_cap(monkeypatch):
    obj = _object("collect-count")
    items = [_instance(obj, f"n-{index}") for index in range(3)]
    monkeypatch.setattr("apps.monitor.services.collection_query.INSTANCE_LIST_MAX", 1)
    with pytest.raises(GenericQueryError, match="1"):
        query_collection_rows(items, vm_api=_VM({}))
    counted = query_collection_rows(items, vm_api=_VM({}), bounded=False)
    assert len(counted) == 3


def test_collection_skips_unconfigured_plugins_and_keeps_manual_instances(monkeypatch):
    obj = _object("collect-scope")
    host = _instance(obj, "alivehost", name="host")
    branded = _instance(obj, "deadonly", name="branded")
    manual = _instance(obj, "manualbox", name="manual")
    alive = _plugin(obj, "scope-alive", "up{plugin='alive'}")
    dead = _plugin(obj, "scope-dead", "up{plugin='dead'}")
    _plugin(obj, "scope-unused", "up{plugin='unusedplug'}")
    _config(host, alive)
    _config(branded, dead)
    calls = []
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    class _RecordingVM:
        def query(self, query, step=None):
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            try:
                time.sleep(0.05)
                calls.append(query)
                return {"status": "success", "data": {"result": []}}
            finally:
                with lock:
                    state["active"] -= 1

    query_collection_rows([host, branded, manual], vm_api=_RecordingVM())

    alive_queries = [query for query in calls if "plugin='alive'" in query]
    dead_queries = [query for query in calls if "plugin='dead'" in query]
    assert alive_queries and dead_queries
    assert state["peak"] >= 2
    assert all("unusedplug" not in query for query in calls)
    assert all("alivehost" in query and "manualbox" in query and "deadonly" not in query for query in alive_queries)
    assert all("deadonly" in query and "manualbox" in query and "alivehost" not in query for query in dead_queries)

    monkeypatch.setattr("apps.monitor.services.collection_query._MATCHER_BUDGET", 1)
    calls.clear()
    query_collection_rows([host, branded, manual], vm_api=_RecordingVM())
    assert len([query for query in calls if "plugin='alive'" in query]) >= 2


def test_collection_stops_vm_reads_after_the_request_deadline():
    obj = _object("collect-deadline")
    host = _instance(obj, "hostbox", name="host")
    plugin = _plugin(obj, "deadline-alive", "up{plugin='alive'}")
    _config(host, plugin)
    calls = []

    class _RecordingVM:
        def query(self, query, step=None):
            calls.append(query)
            return {"status": "success", "data": {"result": []}}

    with pytest.raises(GenericQueryError, match="采集查询超时"):
        query_collection_rows([host], vm_api=_RecordingVM(), deadline=time.monotonic() - 1)

    assert calls == []


def test_collection_handler_does_not_hold_the_shared_nats_thread(monkeypatch):
    from django.conf import settings

    from apps.monitor.nats import generic_query as handlers
    from nats_client.handlers import nats_handler
    from nats_client.registry import default_registry

    class _EmptyQueryset:
        def select_related(self, *args, **kwargs):
            del args, kwargs
            return self

        def distinct(self):
            return self

        def __iter__(self):
            return iter(())

    collection_entered = threading.Event()
    other_entered = threading.Event()
    monkeypatch.setattr(handlers, "_scoped_monitor_instances", lambda *args, **kwargs: _EmptyQueryset())

    def slow_rows(*args, **kwargs):
        del args, kwargs
        collection_entered.set()
        assert other_entered.wait(2), "其他 handler 在采集查询占住线程时没有开始"
        return {"items": [], "count": 0, "page": 1, "page_size": 10}

    def other_handler(*args, **kwargs):
        del args, kwargs
        assert collection_entered.wait(2), "采集查询没有进入工作线程"
        other_entered.set()
        return {"result": True, "data": [], "message": ""}

    monkeypatch.setattr(handlers, "query_collection_rows", slow_rows)
    namespace = settings.NATS_NAMESPACE
    collection_key = f"{namespace}.query_monitor_collection"
    other_key = f"{namespace}.query_monitor_instance_counts"
    assert default_registry.registry[collection_key]["func"]._nats_thread_sensitive is False
    assert default_registry.registry[f"{namespace}.query_monitor_collection_counts"]["func"]._nats_thread_sensitive is False
    monkeypatch.setitem(default_registry.registry[other_key], "func", other_handler)

    async def exercise():
        await asyncio.gather(
            nats_handler(collection_key, {"kwargs": {"user_info": {"user": "ada", "team": 1}, "page": 1, "page_size": 10}}),
            nats_handler(other_key, {"kwargs": {"user_info": {"user": "ada", "team": 1}}}),
        )

    asyncio.run(exercise())


def _vector(rows):
    return {
        "status": "success",
        "data": {
            "result": [
                {
                    "metric": {"instance_id": instance_id, "ifDescr": if_name},
                    "value": [0, value],
                }
                for instance_id, if_name, value in rows
            ]
        },
    }


class _InterfaceVM:
    def query(self, query, step=None):
        assert "{" in query and "instance_id=~" not in query
        if query.startswith("interface_ifOperStatus"):
            return _vector([("sw-1", "Gi0/1", "2"), ("sw-1", "Gi0/2", "5"), ("sw-1", "Gi0/3", "1"), ("other", "Gi9", "2")])
        if "ifHCInOctets" in query:
            return _vector([("sw-1", "Gi0/1", "9")])
        if "interface_ifInOctets" in query:
            return _vector([("sw-1", "Gi0/1", "1")])
        if "ifInErrors" in query:
            return _vector([("sw-1", "Gi0/3", "0.4")])
        if "ifOutDiscards" in query:
            return _vector([("sw-1", "Gi0/2", "0.2")])
        return {"status": "success", "data": {"result": []}}


def test_interface_rate_text_scales_bytes_per_second():
    assert _rate_text(None) is None
    assert _rate_text(0) == "0 B/s"
    assert _rate_text(9) == "9 B/s"
    assert _rate_text(220000) == "220 KB/s"
    assert _rate_text(1800000) == "1.8 MB/s"
    assert _rate_text(1250000) == "1.25 MB/s"


def test_interface_current_keeps_authorized_rows_and_splits_down_from_errors():
    obj = _object("collect-switch", display_name="交换机")
    switch = _instance(obj, "sw-1", name="core-sw")
    vm = _InterfaceVM()

    rows = query_interface_current_rows([switch], vm_api=vm)
    by_name = {row["if_name"]: row for row in rows}
    assert set(by_name) == {"Gi0/1", "Gi0/2", "Gi0/3"}
    assert by_name["Gi0/1"]["oper_status"] == "Down"
    assert by_name["Gi0/1"]["in_rate"] == "9 B/s"
    assert by_name["Gi0/1"]["monitor_object_name"] == "交换机"
    assert by_name["Gi0/2"]["oper_status"] == "Dormant"
    assert by_name["Gi0/3"]["oper_status"] == "Up"
    down = query_interface_current_rows([switch], interface_match="down", vm_api=vm)
    assert [row["if_name"] for row in down] == ["Gi0/1"]
    errors = query_interface_current_rows([switch], interface_match="error", order_by="error_rate", order_dir="desc", vm_api=vm)
    assert [row["if_name"] for row in errors] == ["Gi0/3"]
    discards = query_interface_current_rows([switch], interface_match="discard", vm_api=vm)
    assert [row["if_name"] for row in discards] == ["Gi0/2"]
    up = query_interface_current_rows([switch], interface_match="up", vm_api=vm)
    assert [row["if_name"] for row in up] == ["Gi0/3"]
    ranked = query_interface_current_rows([switch], order_by="in_rate", order_dir="desc", vm_api=vm)
    assert ranked[0]["if_name"] == "Gi0/1"


def test_collection_and_interface_handlers_share_category_scope(monkeypatch):
    from apps.monitor.nats.generic_query import query_interface_current_counts, query_monitor_collection, query_monitor_collection_counts

    network = MonitorObjectType.objects.create(id="ctype-net", name="网络设备", order=1)
    database = MonitorObjectType.objects.create(id="ctype-db", name="数据库", order=2)
    switch = MonitorObject.objects.create(name="handler-switch", level="base", type=network, instance_id_keys=["instance_id"])
    mysql = MonitorObject.objects.create(name="handler-mysql", level="base", type=database, instance_id_keys=["instance_id"])
    for obj, raw_id in ((switch, "sw-1"), (switch, "sw-2"), (mysql, "db-1")):
        item = _instance(obj, raw_id)
        MonitorInstanceOrganization.objects.create(monitor_instance=item, organization=1)
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_nats_actor_scope",
        lambda user_info: (user_info, 1, False, [1], True, None),
    )
    monkeypatch.setattr("apps.monitor.services.collection_query.VictoriaMetricsAPI", lambda: _VM({}))
    monkeypatch.setattr("apps.monitor.services.interface_current.VictoriaMetricsAPI", lambda: _InterfaceVM())
    user_info = {"user": "ada", "team": 1}

    counted = query_monitor_collection_counts(monitor_object_type_ids=[network.id], user_info=user_info)
    assert counted["result"] is True
    assert counted["data"] == [{"instance_count": 2}]
    listed = query_monitor_collection(
        monitor_object_type_ids=[network.id],
        page=1,
        page_size=1,
        user_info=user_info,
    )
    assert listed["data"]["count"] == 2
    assert len(listed["data"]["items"]) == 1
    mismatched = query_monitor_collection_counts(
        monitor_object_type_ids=[database.id],
        monitor_object_id=[str(switch.id)],
        user_info=user_info,
    )
    assert mismatched["result"] is False
    assert "对象不属于所选分类" in mismatched["message"]
    paged = query_monitor_collection_counts(page=1, page_size=10, user_info=user_info)
    assert paged["result"] is False
    assert "分页" in paged["message"]
    interfaces = query_interface_current_counts(monitor_object_type_ids=[network.id], interface_match="down", user_info=user_info)
    assert interfaces["result"] is True
    assert interfaces["data"] == [{"interface_count": 1}]
    missing = query_interface_current_counts(instance_ids=["missing"], user_info=user_info)
    assert missing["result"] is False
    assert missing["data"]["status"] == "forbidden"
