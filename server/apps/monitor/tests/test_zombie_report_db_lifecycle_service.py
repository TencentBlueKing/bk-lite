"""真实 PG 验证报表旁路线程回收连接，不依赖线程退出或垃圾回收。"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.apps.registry import Apps
from django.db import connections, models
from django.db.backends.signals import connection_created

from apps.log.nats import log as log_api
from apps.monitor.nats import monitor as monitor_api
from nats_client.handlers import nats_handler
from nats_client.registry import default_registry

catalog_apps = Apps()


class Namespace(models.Model):
    oid = models.IntegerField(primary_key=True)

    class Meta:
        apps = catalog_apps
        app_label = "zombie_connection_tests"
        managed = False
        db_table = "pg_namespace"


class Catalog(models.Model):
    oid = models.IntegerField(primary_key=True)
    collect_type = models.ForeignKey(Namespace, db_column="relnamespace", on_delete=models.DO_NOTHING)

    class Meta:
        apps = catalog_apps
        app_label = "zombie_connection_tests"
        managed = False
        db_table = "pg_class"


@pytest.fixture
def pg_connections(monkeypatch, django_db_blocker):
    if connections["default"].vendor != "postgresql":
        pytest.skip("需要 PostgreSQL 验证实际连接回收")
    alias = "zombie_report_lifecycle"
    config = connections["default"].settings_dict.copy()
    config["CONN_MAX_AGE"] = 0
    monkeypatch.setitem(connections.settings, alias, config)
    drivers = []
    main_thread = threading.get_ident()

    def observe(sender, connection, **kwargs):
        if connection.alias == alias and threading.get_ident() != main_thread:
            # 保留驱动引用，避免 GC 替代应有的显式 close，让缺陷稳定可测。
            drivers.append(connection.connection)

    connection_created.connect(observe, weak=False)
    with django_db_blocker.unblock():
        main_db = connections[alias]
        try:
            assert Catalog.objects.using(alias).exists()
            yield alias, drivers, main_db
        finally:
            connection_created.disconnect(observe)
            for driver in drivers:
                driver.close()
            main_db.close()
            del connections[alias]


@pytest.mark.integration
@pytest.mark.parametrize("fails", [False, True])
def test_report_nats_rounds_release_child_connections(monkeypatch, pg_connections, fails):
    alias, drivers, main_db = pg_connections
    main_driver = main_db.connection
    host = {"inst_uuid": "u1", "monitor_id": "m1", "host_name": "test", "ip": "127.0.0.1", "os_type": "1", "node_id": "n1"}
    monkeypatch.setattr(monitor_api, "_get_nats_actor_scope", lambda _: (None, 1, False, frozenset({1}), False, None))
    monkeypatch.setattr(monitor_api, "_get_authorized_monitor_instances", lambda *args: ({"m1": object()}, None))
    monkeypatch.setattr(monitor_api, "load_selected_hosts", lambda *args: [host])
    monkeypatch.setattr(monitor_api, "_query_zombie_vm_metrics", lambda *args: {})
    # 替换权限数据来源，保留真实日志接口的 QuerySet 求值和 select_related。
    monkeypatch.setattr(log_api, "_authorized_log_instances", lambda _: Catalog.objects.using(alias).filter(oid=-1))
    if fails:

        def fail_merge(*args):
            raise ValueError("merge failed")

        monkeypatch.setattr(log_api, "merge_login_counts", fail_merge)
    key = next(key for key, item in default_registry.registry.items() if item["func"] is monitor_api.get_zombie_host_report)

    async def invoke():
        return await nats_handler(key, {"kwargs": {"inst_uuids": ["u1"], "time": 10080, "user_info": {"user": "test", "team": 1}}})

    for round_number in range(1, 4):
        result = asyncio.run(invoke())
        assert result["result"] is not fails
        if fails:
            assert result["message"] == "成功登录计数失败"
        assert len(drivers) == round_number
        assert all(driver.closed for driver in drivers)
        assert main_db.connection is main_driver and not main_driver.closed


@pytest.mark.integration
@pytest.mark.parametrize("error", [RuntimeError("query failed"), KeyboardInterrupt()])
def test_worker_preserves_exception_and_releases_connection(monkeypatch, pg_connections, error):
    alias, drivers, main_db = pg_connections

    def query(*args):
        assert Catalog.objects.using(alias).exists()
        raise error

    monkeypatch.setattr(monitor_api, "count_successful_logins", query)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(monitor_api._query_zombie_logins, [], [], {})
        with pytest.raises(type(error)) as raised:
            future.result()
        assert raised.value is error
        # 工作线程尚存活时验证释放，不能靠线程池退出。
        assert len(drivers) == 1 and drivers[0].closed
        executor.submit(lambda: connections[alias].close()).result()
    assert not main_db.connection.closed


@pytest.mark.integration
@pytest.mark.parametrize("max_age", [3600, None])
def test_worker_respects_healthy_persistent_connections(monkeypatch, pg_connections, max_age):
    alias, drivers, main_db = pg_connections
    monkeypatch.setitem(connections.settings[alias], "CONN_MAX_AGE", max_age)
    result = {"result": True, "data": []}

    def query(*args):
        assert Catalog.objects.using(alias).exists()
        return result

    monkeypatch.setattr(monitor_api, "count_successful_logins", query)
    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            for _ in range(2):
                assert executor.submit(monitor_api._query_zombie_logins, [], [], {}).result() is result
                assert len(drivers) == 1 and not drivers[0].closed
        finally:
            executor.submit(lambda: connections[alias].close()).result()
    assert not main_db.connection.closed
