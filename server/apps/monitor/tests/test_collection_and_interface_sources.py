"""采集和接口当前值：同一套过滤，查询出表，数量出一行。"""

import asyncio
import logging
import re
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings

from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject, MonitorObjectType
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.collection_query import query_collection_count, query_collection_rows
from apps.monitor.services.generic_query import GenericQueryError
from apps.monitor.services.interface_current import _rate_text, query_interface_current_count, query_interface_current_rows

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


def test_collection_does_not_emit_an_unscopeable_status_query(caplog):
    obj = _object("collect-unscoped")
    host = _instance(obj, "hostbox", name="host")
    bare = _plugin(obj, "bare-up", "up")
    _config(host, bare)
    calls = []

    class _RecordingVM:
        def query(self, query, step=None):
            calls.append(query)
            return {"status": "success", "data": {"result": [_sample("hostbox", time.time())]}}

    with caplog.at_level(logging.WARNING, logger="monitor"):
        rows = query_collection_rows([host], vm_api=_RecordingVM())

    assert calls == []
    assert rows[0]["collect_status"] == "失联"
    warnings = [record for record in caplog.records if record.levelno >= logging.WARNING and record.name == "monitor"]
    assert len(warnings) == 1
    record = warnings[0]
    assert record.exc_info is None
    assert record.msg == (
        "event=collection_status_query_unscoped plugin_id=%s reason=%s failed_stage=%s error_type=%s"
    )
    assert record.args == (bare.id, "no_selector", "status_query_scope", "UnscopeableStatusQuery")
    formatted = logging.Formatter().format(record)
    assert "reason=no_selector" in formatted
    assert formatted.endswith("error_type=UnscopeableStatusQuery")
    assert "hostbox" not in formatted

    other = _object("collect-wide")
    scoped_host = _instance(other, "widebox", name="wide")
    wide = _plugin(other, "wide-up", 'up{instance_id=~".+"}')
    _config(scoped_host, wide)
    calls.clear()

    class _WideVM:
        def query(self, query, step=None):
            calls.append(query)
            return {"status": "success", "data": {"result": [_sample("widebox", time.time())]}}

    narrowed = query_collection_rows([scoped_host], vm_api=_WideVM())
    assert calls
    assert all("widebox" in query for query in calls)
    assert all(query != 'up{instance_id=~".+"}' for query in calls)
    assert narrowed[0]["collect_status"] == "正常"


def test_collection_scopes_only_instances_whose_identity_parses():
    obj = _object("collect-partial")
    obj.instance_id_keys = ["instance_id", "port"]
    obj.save(update_fields=["instance_id_keys"])
    good = MonitorInstance.objects.create(
        id=str(("goodhost", "1")),
        name="good",
        monitor_object=obj,
        is_active=True,
        ip="10.0.0.8",
    )
    bad = MonitorInstance.objects.create(
        id=str(("badhost",)),
        name="bad",
        monitor_object=obj,
        is_active=True,
        ip="10.0.0.9",
    )
    plugin = _plugin(obj, "partial-up", "up{plugin='partial'}")
    _config(good, plugin)
    _config(bad, plugin)
    calls = []

    class _RecordingVM:
        def query(self, query, step=None):
            calls.append(query)
            return {"status": "success", "data": {"result": []}}

    rows = query_collection_rows([good, bad], vm_api=_RecordingVM())
    by_name = {row["name"]: row for row in rows}
    assert calls
    assert all("goodhost" in query for query in calls)
    assert all("badhost" not in query for query in calls)
    assert all(query != "up{plugin='partial'}" for query in calls)
    assert by_name["good"]["collect_status"] == "失联"
    assert by_name["bad"]["collect_status"] == "失联"


def test_collection_page_with_name_sort_reads_status_only_for_that_page():
    obj = _object("collect-page")
    third = _instance(obj, "pagec", name="c")
    first = _instance(obj, "pagea", name="a")
    second = _instance(obj, "pageb", name="b")
    plugin = _plugin(obj, "page-up", "up{plugin='page'}")
    for item in (first, second, third):
        _config(item, plugin)
    calls = []

    class _RecordingVM:
        def query(self, query, step=None):
            calls.append(query)
            return {"status": "success", "data": {"result": [_sample("pagea", time.time())]}}

    page = query_collection_rows([third, first, second], page=1, page_size=1, vm_api=_RecordingVM())
    assert page["count"] == 3
    assert [row["name"] for row in page["items"]] == ["a"]
    assert len(page["items"]) == 1
    assert calls
    assert all("pagea" in query for query in calls)
    assert all("pageb" not in query and "pagec" not in query for query in calls)


def test_collection_offline_page_counts_every_match_not_the_page_length():
    obj = _object("collect-offline-page")
    early = _instance(obj, "offa", name="a")
    middle = _instance(obj, "offb", name="b")
    late = _instance(obj, "onc", name="c")
    plugin = _plugin(obj, "offline-up", "up{plugin='offline'}")
    for item in (early, middle, late):
        _config(item, plugin)
    calls = []

    class _RecordingVM:
        def query(self, query, step=None):
            calls.append(query)
            return {"status": "success", "data": {"result": [_sample("onc", time.time())]}}

    page = query_collection_rows(
        [early, middle, late],
        collect_status="offline",
        page=1,
        page_size=1,
        vm_api=_RecordingVM(),
    )
    assert page["count"] == 2
    assert len(page["items"]) == 1
    assert page["items"][0]["collect_status"] == "失联"
    sent = " ".join(calls)
    assert "offa" in sent and "offb" in sent and "onc" in sent
    assert query_collection_count([early, middle, late], collect_status="offline", vm_api=_RecordingVM()) == 2


def test_collection_open_count_skips_victoria_metrics_and_ignores_the_list_cap(monkeypatch):
    obj = _object("collect-open-count")
    items = [_instance(obj, f"open-{index}", name=f"n-{index}") for index in range(3)]
    calls = []

    class _RecordingVM:
        def query(self, query, step=None):
            calls.append(query)
            return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr("apps.monitor.services.collection_query.INSTANCE_LIST_MAX", 1)
    assert query_collection_count(items, vm_api=_RecordingVM()) == 3
    assert calls == []
    with pytest.raises(GenericQueryError, match="1"):
        query_collection_rows(items, vm_api=_RecordingVM())


def test_collection_manual_page_still_reads_plugins_configured_on_the_object():
    obj = _object("collect-manual-page")
    manual = _instance(obj, "manuala", name="a")
    configured = _instance(obj, "configuredz", name="z")
    plugin = _plugin(obj, "manual-up", "up{plugin='manualpage'}")
    _config(configured, plugin)
    calls = []
    now = time.time()

    class _RecordingVM:
        def query(self, query, step=None):
            calls.append(query)
            return {"status": "success", "data": {"result": [_sample("manuala", now)]}}

    page = query_collection_rows([manual, configured], page=1, page_size=1, vm_api=_RecordingVM())
    assert page["count"] == 2
    assert page["items"][0]["name"] == "a"
    assert page["items"][0]["collect_mode"] == "手动"
    assert page["items"][0]["last_sample_at"]
    assert calls
    assert all("manuala" in query and "configuredz" not in query for query in calls)


def test_collection_manual_status_stays_inside_the_request_scope():
    obj = _object("collect-manual-scope")
    manual = _instance(obj, "manualb", name="a")
    peer = _instance(obj, "peerb", name="m")
    outsider = _instance(obj, "outb", name="z")
    peer_plugin = _plugin(obj, "peer-up", "up{plugin='peerpage'}")
    outside_plugin = _plugin(obj, "out-up", "up{plugin='outpage'}")
    _config(peer, peer_plugin)
    _config(outsider, outside_plugin)
    calls = []
    now = time.time()

    class _RecordingVM:
        def query(self, query, step=None):
            calls.append(query)
            return {
                "status": "success",
                "data": {"result": [_sample("manualb", now), _sample("outb", now), _sample("peerb", now)]},
            }

    alone = query_collection_rows([manual], vm_api=_RecordingVM())
    assert alone[0]["collect_mode"] == "手动"
    assert alone[0]["collect_status"] == "正常"
    assert alone[0]["report_status"] == "失联"
    assert alone[0]["last_sample_at"] == ""
    assert calls == []
    assert query_collection_count([manual], report_status="unavailable", vm_api=_RecordingVM()) == 1

    calls.clear()
    page = query_collection_rows([manual, peer], page=1, page_size=1, vm_api=_RecordingVM())
    assert page["count"] == 2
    assert page["items"][0]["name"] == "a"
    assert page["items"][0]["collect_mode"] == "手动"
    assert page["items"][0]["collect_status"] == "正常"
    assert page["items"][0]["report_status"] == "正常"
    assert page["items"][0]["last_sample_at"]
    sent = " ".join(calls)
    assert "peerpage" in sent
    assert "manualb" in sent
    assert "outpage" not in sent
    assert "outb" not in sent
    assert "peerb" not in sent


def test_collection_past_deadline_with_no_jobs_fails():
    obj = _object("collect-empty-deadline")
    manual = _instance(obj, "quiet", name="quiet")
    calls = []

    class _RecordingVM:
        def query(self, query, step=None):
            calls.append(query)
            return {"status": "success", "data": {"result": []}}

    with pytest.raises(GenericQueryError, match="采集查询超时"):
        query_collection_rows([manual], vm_api=_RecordingVM(), deadline=time.monotonic() - 1)
    with pytest.raises(GenericQueryError, match="采集查询超时"):
        query_collection_count([manual], report_status="unavailable", vm_api=_RecordingVM(), deadline=time.monotonic() - 1)
    bare = _plugin(obj, "bare-up", "up")
    host = _instance(obj, "barehost", name="bare")
    _config(host, bare)
    with pytest.raises(GenericQueryError, match="采集查询超时"):
        query_collection_rows([host], vm_api=_RecordingVM(), deadline=time.monotonic() - 1)
    assert calls == []


def test_collection_requires_page_and_page_size_together():
    obj = _object("collect-page-pair")
    item = _instance(obj, "pair-1", name="pair")
    with pytest.raises(GenericQueryError, match="同时"):
        query_collection_rows([item], page=1, vm_api=_VM({}))


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
        assert 'instance_id=~"^(?:' in query
        assert "interface_ifHighSpeed" not in query
        assert "interface_ifSpeed{" not in query
        if "count by (instance_id)" in query and "== 2" in query:
            if "sw" in query:
                return {
                    "status": "success",
                    "data": {"result": [{"metric": {"instance_id": "sw-1"}, "value": [0, "1"]}]},
                }
            return {"status": "success", "data": {"result": []}}
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
    ordered = query_monitor_collection_counts(order_by="last_sample_at", order_dir="desc", user_info=user_info)
    assert ordered["result"] is False
    assert "排序" in ordered["message"]
    interfaces = query_interface_current_counts(monitor_object_type_ids=[network.id], interface_match="down", user_info=user_info)
    assert interfaces["result"] is True
    assert interfaces["data"] == [{"interface_count": 1}]
    missing = query_interface_current_counts(instance_ids=["missing"], user_info=user_info)
    assert missing["result"] is False
    assert missing["data"]["status"] == "forbidden"


def _recording_vm(responder):
    calls = []
    lock = threading.Lock()

    class _Recording:
        def query(self, query, step=None):
            with lock:
                calls.append(("query", query))
            return responder(query)

        def query_form(self, query, step=None):
            with lock:
                calls.append(("form", query))
            return responder(query)

    return _Recording(), calls


def test_interface_page_keeps_the_full_filtered_count():
    obj = _object("page-switch", display_name="交换机")
    switch = _instance(obj, "swpage", name="core")

    def responder(query):
        assert 'instance_id=~"^(?:' in query
        if query.startswith("interface_ifOperStatus"):
            return _vector([("swpage", "Gi0/1", "1"), ("swpage", "Gi0/2", "2"), ("swpage", "Gi0/3", "1")])
        if "ifHCInOctets" in query:
            return _vector([("swpage", "Gi0/1", "1"), ("swpage", "Gi0/2", "900"), ("swpage", "Gi0/3", "50")])
        return {"status": "success", "data": {"result": []}}

    vm, calls = _recording_vm(responder)
    page = query_interface_current_rows(
        [switch],
        order_by="in_rate",
        order_dir="desc",
        page=1,
        page_size=1,
        vm_api=vm,
    )
    assert page["count"] == 3
    assert [row["if_name"] for row in page["items"]] == ["Gi0/2"]
    assert page["items"][0]["in_rate"] == "900 B/s"
    assert all(kind == "query" for kind, _query in calls)


def _count_vector(rows):
    return {
        "status": "success",
        "data": {
            "result": [
                {"metric": {"instance_id": instance_id}, "value": [0, str(count)]}
                for instance_id, count in rows
            ]
        },
    }


def test_interface_count_reads_only_the_match_metrics():
    obj = _object("count-switch")
    switch = _instance(obj, "swcount", name="core")

    def responder(query):
        assert "count by (instance_id)" in query
        if "interface_ifOperStatus" in query and "== 2" in query:
            assert "ifHCInOctets" not in query
            assert "ifInErrors" not in query
            return _count_vector([("swcount", 1)])
        if "ifInErrors" in query or "ifOutErrors" in query:
            assert "interface_ifOperStatus" not in query
            assert "ifHCInOctets" not in query
            assert "ifInErrors" in query and "ifOutErrors" in query
            return _count_vector([("swcount", 1)])
        if "ifInDiscards" in query or "ifOutDiscards" in query:
            return _count_vector([("swcount", 1)])
        return {"status": "success", "data": {"result": []}}

    down_vm, down_calls = _recording_vm(responder)
    assert query_interface_current_count([switch], interface_match="down", vm_api=down_vm) == 1
    assert down_calls
    assert all("interface_ifOperStatus" in query and "== 2" in query for _kind, query in down_calls)
    assert 'label_replace(' in down_calls[0][1]
    assert 'ifDescr!~"^[[:space:]]*$"' in down_calls[0][1]

    error_vm, error_calls = _recording_vm(responder)
    assert query_interface_current_count([switch], interface_match="error", vm_api=error_vm) == 1
    assert error_calls
    assert all("ifInErrors" in query and "ifOutErrors" in query for _kind, query in error_calls)

    empty_vm, empty_calls = _recording_vm(responder)
    assert query_interface_current_count([], vm_api=empty_vm) == 0
    assert empty_calls == []


def test_interface_snapshot_keeps_32bit_only_and_skips_speed(monkeypatch):
    obj = _object("identity-switch")
    switch = _instance(obj, "swid", name="core")

    def responder(query):
        if "interface_ifHighSpeed" in query or "interface_ifSpeed{" in query:
            return _vector([("swid", "Speed0", "1000")])
        if query.startswith("rate(interface_ifInOctets"):
            return _vector([("swid", "Gi0/9", "1000")])
        return {"status": "success", "data": {"result": []}}

    vm, calls = _recording_vm(responder)
    rows = query_interface_current_rows([switch], vm_api=vm)
    assert [row["if_name"] for row in rows] == ["Gi0/9"]
    assert rows[0]["in_rate"] == "1 KB/s"
    assert all("interface_ifHighSpeed" not in query and "interface_ifSpeed{" not in query for _kind, query in calls)

    monkeypatch.setattr("apps.monitor.services.interface_current._SELECTOR_BUDGET", 1)
    left = _instance(obj, "alpha", name="alpha-box")
    right = _instance(obj, "beta", name="beta-box")

    def chunked(query):
        if not query.startswith("interface_ifOperStatus"):
            return {"status": "success", "data": {"result": []}}
        rows = []
        if "alpha" in query:
            rows.append(("alpha", "Gi0/1", "1"))
        if "beta" in query:
            rows.append(("beta", "Gi0/2", "1"))
        return _vector(rows)

    chunk_vm, chunk_calls = _recording_vm(chunked)
    paged = query_interface_current_rows([left, right], page=1, page_size=1, vm_api=chunk_vm)
    status_queries = [query for _kind, query in chunk_calls if query.startswith("interface_ifOperStatus")]
    assert len(status_queries) == 2
    assert all("alpha" in query or "beta" in query for query in status_queries)
    assert paged["count"] == 2
    assert [row["if_name"] for row in paged["items"]] == ["Gi0/1"]


def test_interface_long_selector_uses_query_form(monkeypatch):
    obj = _object("form-switch")
    switch = _instance(obj, "swform", name="core")
    monkeypatch.setattr("apps.monitor.services.interface_current._LONG_QUERY", 0)

    def responder(query):
        if query.startswith("interface_ifOperStatus"):
            return _vector([("swform", "Gi0/1", "2")])
        return {"status": "success", "data": {"result": []}}

    vm, calls = _recording_vm(responder)
    rows = query_interface_current_rows([switch], interface_match="down", vm_api=vm)
    assert [row["if_name"] for row in rows] == ["Gi0/1"]
    assert calls
    assert all(kind == "form" for kind, _query in calls)


def test_interface_snapshot_queries_run_concurrently():
    obj = _object("concurrent-switch")
    switch = _instance(obj, "swcon", name="core")
    state = {"active": 0, "peak": 0}
    lock = threading.Lock()

    class _Slow:
        def query(self, query, step=None):
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            try:
                time.sleep(0.05)
                return {"status": "success", "data": {"result": []}}
            finally:
                with lock:
                    state["active"] -= 1

    query_interface_current_rows([switch], vm_api=_Slow())
    assert state["peak"] >= 2


def test_interface_metric_failure_fails_the_whole_snapshot():
    obj = _object("fail-switch")
    switch = _instance(obj, "swfail", name="core")

    class _Broken:
        def query(self, query, step=None):
            if "ifHCInOctets" in query:
                raise RuntimeError("vm down")
            return {"status": "success", "data": {"result": []}}

    with pytest.raises(GenericQueryError, match="接口指标查询失败"):
        query_interface_current_rows([switch], vm_api=_Broken())


def test_interface_count_fans_out_one_vm_label_to_each_owner():
    obj = _object("fanout-switch")
    left = MonitorInstance.objects.create(
        id=str(("swfan", "a")),
        name="left",
        monitor_object=obj,
        is_active=True,
        ip="10.0.0.8",
    )
    right = MonitorInstance.objects.create(
        id=str(("swfan", "b")),
        name="right",
        monitor_object=obj,
        is_active=True,
        ip="10.0.0.9",
    )

    def responder(query):
        assert "count by (instance_id)" in query
        assert "== 2" in query
        assert "swfan" in query
        return _count_vector([("swfan", 1)])

    vm, _calls = _recording_vm(responder)
    assert query_interface_current_count([left, right], interface_match="down", vm_api=vm) == 2


def test_interface_handler_does_not_hold_the_shared_nats_thread(monkeypatch):
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

    interface_entered = threading.Event()
    other_entered = threading.Event()
    monkeypatch.setattr(handlers, "_scoped_monitor_instances", lambda *args, **kwargs: _EmptyQueryset())

    def slow_rows(*args, **kwargs):
        del args, kwargs
        interface_entered.set()
        assert other_entered.wait(2), "其他 handler 在接口查询占住线程时没有开始"
        return []

    def other_handler(*args, **kwargs):
        del args, kwargs
        assert interface_entered.wait(2), "接口查询没有进入工作线程"
        other_entered.set()
        return {"result": True, "data": [], "message": ""}

    monkeypatch.setattr(handlers, "query_interface_current_rows", slow_rows)
    namespace = settings.NATS_NAMESPACE
    interface_key = f"{namespace}.query_interface_current"
    other_key = f"{namespace}.query_monitor_instance_counts"
    assert default_registry.registry[interface_key]["func"]._nats_thread_sensitive is False
    assert default_registry.registry[f"{namespace}.query_interface_current_counts"]["func"]._nats_thread_sensitive is False
    monkeypatch.setitem(default_registry.registry[other_key], "func", other_handler)

    async def exercise():
        await asyncio.gather(
            nats_handler(interface_key, {"kwargs": {"user_info": {"user": "ada", "team": 1}, "page": 1, "page_size": 10}}),
            nats_handler(other_key, {"kwargs": {"user_info": {"user": "ada", "team": 1}}}),
        )

    asyncio.run(exercise())


def test_interface_down_page_counts_every_match_and_rates_only_that_page():
    obj = _object("down-page-switch", display_name="交换机")
    switch = _instance(obj, "swdown", name="core")

    def responder(query):
        if "count by (instance_id)" in query:
            raise AssertionError("list query must not use the count aggregate")
        if query.startswith("interface_ifOperStatus"):
            assert "ifDescr=~" not in query
            return _vector(
                [
                    ("swdown", "Eth3", "2"),
                    ("swdown", "Eth1", "2"),
                    ("swdown", "Eth2", "2"),
                    ("swdown", "Eth9", "1"),
                ]
            )
        if "Octets" in query or "Errors" in query or "Discards" in query:
            assert "Eth1" in query
            assert "Eth2" not in query
            assert "Eth3" not in query
            assert "Eth9" not in query
            if "ifHCInOctets" in query:
                return _vector([("swdown", "Eth1", "12")])
        return {"status": "success", "data": {"result": []}}

    vm, calls = _recording_vm(responder)
    page = query_interface_current_rows([switch], interface_match="down", page=1, page_size=1, vm_api=vm)
    assert page["count"] == 3
    assert len(page["items"]) == 1
    assert page["items"][0]["if_name"] == "Eth1"
    assert page["items"][0]["oper_status"] == "Down"
    assert page["items"][0]["in_rate"] == "12 B/s"
    rate_queries = [query for _kind, query in calls if "Octets" in query or "Errors" in query or "Discards" in query]
    assert rate_queries
    assert all("Eth1" in query and "Eth2" not in query for query in rate_queries)


def test_interface_unpaged_cap_fails_before_display_rates(monkeypatch):
    obj = _object("cap-switch")
    switch = _instance(obj, "swcap", name="core")

    def responder(query):
        if query.startswith("interface_ifOperStatus"):
            return _vector([("swcap", "Gi0/1", "2"), ("swcap", "Gi0/2", "2")])
        return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr("apps.monitor.services.interface_current.INSTANCE_LIST_MAX", 1)
    vm, calls = _recording_vm(responder)
    with pytest.raises(GenericQueryError, match="1"):
        query_interface_current_rows([switch], interface_match="down", vm_api=vm)
    assert any(query.startswith("interface_ifOperStatus") for _kind, query in calls)
    assert all("Octets" not in query and "Errors" not in query and "Discards" not in query for _kind, query in calls)
    counted, count_calls = _recording_vm(
        lambda query: _count_vector([("swcap", 2)]) if "count by (instance_id)" in query else responder(query)
    )
    assert query_interface_current_count([switch], interface_match="down", vm_api=counted) == 2
    assert count_calls


def test_interface_rate_sort_still_ranks_the_full_match_before_paging():
    obj = _object("rank-switch")
    switch = _instance(obj, "swrank", name="core")

    def responder(query):
        if query.startswith("interface_ifOperStatus"):
            return _vector([("swrank", "Gi0/1", "1"), ("swrank", "Gi0/2", "1"), ("swrank", "Gi0/3", "1")])
        if "ifHCInOctets" in query:
            assert "ifDescr=~" not in query
            return _vector([("swrank", "Gi0/1", "1"), ("swrank", "Gi0/2", "900"), ("swrank", "Gi0/3", "50")])
        return {"status": "success", "data": {"result": []}}

    vm, _calls = _recording_vm(responder)
    page = query_interface_current_rows(
        [switch],
        order_by="in_rate",
        order_dir="desc",
        page=2,
        page_size=1,
        vm_api=vm,
    )
    assert page["count"] == 3
    assert [row["if_name"] for row in page["items"]] == ["Gi0/3"]
    assert page["items"][0]["in_rate"] == "50 B/s"


def test_interface_list_and_count_stop_on_deadline_without_a_partial_result(monkeypatch, caplog):
    obj = _object("deadline-switch")
    left = _instance(obj, "alpha", name="alpha")
    right = _instance(obj, "beta", name="beta")
    calls = []

    class _VM:
        def query(self, query, step=None):
            calls.append(query)
            time.sleep(0.05)
            return _count_vector([("alpha", 4)])

    with caplog.at_level(logging.WARNING, logger="monitor"):
        with pytest.raises(GenericQueryError, match="接口查询超时"):
            query_interface_current_rows([left], vm_api=_VM(), deadline=time.monotonic() - 1)
    assert calls == []
    deadline_logs = [
        record
        for record in caplog.records
        if record.msg == "event=interface_query_deadline_exceeded failed_stage=%s error_type=%s"
    ]
    assert deadline_logs
    assert deadline_logs[0].exc_info is None
    assert deadline_logs[0].args == ("vm_read", "DeadlineExceeded")
    formatted = logging.Formatter().format(deadline_logs[0])
    assert "failed_stage=vm_read" in formatted
    assert formatted.endswith("error_type=DeadlineExceeded")
    assert "alpha" not in formatted

    monkeypatch.setattr("apps.monitor.services.interface_current._SELECTOR_BUDGET", 1)
    calls.clear()
    with pytest.raises(GenericQueryError, match="接口查询超时"):
        query_interface_current_count([left, right], interface_match="down", vm_api=_VM(), deadline=time.monotonic() + 0.01)
    assert len(calls) == 1


def _if_descr_pattern(query):
    found = re.search(r'ifDescr=~"((?:\\.|[^"])*)"', query)
    assert found, query
    body = found.group(1)
    chars = []
    index = 0
    while index < len(body):
        if body[index] == "\\" and index + 1 < len(body):
            chars.append(body[index + 1])
            index += 2
        else:
            chars.append(body[index])
            index += 1
    return "".join(chars)


def test_interface_error_page_hydrates_display_when_if_descr_has_surrounding_space():
    obj = _object("pad-switch")
    switch = _instance(obj, "swpad", name="core")

    def matches(query, label):
        return re.search(_if_descr_pattern(query), label) is not None

    def responder(query):
        if "ifInErrors" in query or "ifOutErrors" in query:
            assert "ifDescr=~" not in query
            return _vector([("swpad", " eth0", "3")])
        if "ifDescr=~" in query:
            assert matches(query, " eth0")
            assert matches(query, "eth0 ")
            assert matches(query, "eth0")
            assert not matches(query, "eth0x")
            assert not matches(query, "xeth0")
            if query.startswith("interface_ifOperStatus"):
                return _vector([("swpad", " eth0", "2")])
            if "ifHCInOctets" in query:
                return _vector([("swpad", " eth0", "12")])
        return {"status": "success", "data": {"result": []}}

    vm, _calls = _recording_vm(responder)
    page = query_interface_current_rows([switch], interface_match="error", page=1, page_size=1, vm_api=vm)
    assert page["count"] == 1
    assert page["items"][0]["if_name"] == "eth0"
    assert page["items"][0]["oper_status"] == "Down"
    assert page["items"][0]["in_rate"] == "12 B/s"
    assert page["items"][0]["in_errors"] == 3


def test_interface_count_fails_closed_on_a_non_success_payload(monkeypatch, caplog):
    obj = _object("count-fail-switch")
    left = _instance(obj, "alpha", name="alpha")
    right = _instance(obj, "beta", name="beta")
    calls = []

    class _VM:
        def query(self, query, step=None):
            calls.append(query)
            if len(calls) == 1:
                return {"status": "error", "data": {"result": []}}
            return _count_vector([("beta", 4)])

    monkeypatch.setattr("apps.monitor.services.interface_current._SELECTOR_BUDGET", 1)
    with pytest.raises(GenericQueryError, match="接口指标查询失败"):
        query_interface_current_count([left, right], interface_match="down", vm_api=_VM())
    assert len(calls) == 1

    calls.clear()

    class _Later:
        def query(self, query, step=None):
            calls.append(query)
            if len(calls) == 1:
                return _count_vector([("alpha", 4)])
            return {"status": "error", "error": "SECRET-VM-BODY"}

    with caplog.at_level(logging.ERROR, logger="monitor"):
        with pytest.raises(GenericQueryError, match="接口指标查询失败") as raised:
            query_interface_current_count([left, right], interface_match="down", vm_api=_Later())
    assert len(calls) == 2
    assert str(raised.value) == "接口指标查询失败"
    formatted = "\n".join(logging.Formatter().format(record) for record in caplog.records)
    assert "SECRET-VM-BODY" not in formatted
    assert "SECRET-VM-BODY" not in str(raised.value)


def test_interface_count_requires_no_page_or_sort():
    from apps.monitor.nats.generic_query import query_interface_current_counts

    network = MonitorObjectType.objects.create(id="ctype-net-count", name="网络设备", order=1)
    switch = MonitorObject.objects.create(name="count-sort-switch", level="base", type=network, instance_id_keys=["instance_id"])
    item = _instance(switch, "swsort")
    MonitorInstanceOrganization.objects.create(monitor_instance=item, organization=1)
    sorted_count = query_interface_current_counts(
        monitor_object_id=[str(switch.id)],
        order_by="if_name",
        order_dir="asc",
        user_info={"user": "ada", "team": 1},
    )
    assert sorted_count["result"] is False
    assert "排序" in sorted_count["message"]
