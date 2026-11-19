"""验证 NATS 同步入口的已有连接清理，避免将旁路线程问题误修到监听主线程。"""

import asyncio
import threading

import pytest
from asgiref.sync import sync_to_async
from django.apps.registry import Apps
from django.db import connections, models

from nats_client.handlers import nats_handler
from nats_client.registry import default_registry


class Catalog(models.Model):
    oid = models.IntegerField(primary_key=True)

    class Meta:
        apps = Apps()
        app_label = "nats_lifecycle_tests"
        managed = False
        db_table = "pg_class"


@pytest.mark.integration
@pytest.mark.parametrize("fails", [False, True])
def test_nats_sync_handler_releases_own_pg_connection_each_round(monkeypatch, django_db_blocker, fails):
    if connections["default"].vendor != "postgresql":
        pytest.skip("需要 PostgreSQL 验证连接生命周期")
    alias = "nats_lifecycle_test"
    config = connections["default"].settings_dict.copy()
    config["CONN_MAX_AGE"] = 0
    monkeypatch.setitem(connections.settings, alias, config)
    key = "test.connection_lifecycle"
    drivers = []
    worker_ids = []
    failure = ValueError("handler failed")
    result = {"result": True, "data": [1]}

    def handler(value):
        assert value == 7
        worker_ids.append(threading.get_ident())
        assert Catalog.objects.using(alias).exists()
        drivers.append(connections[alias].connection)
        if fails:
            raise failure
        return result

    monkeypatch.setitem(default_registry.registry, key, {"func": handler})

    async def exercise():
        try:
            for _ in range(3):
                if fails:
                    with pytest.raises(ValueError) as raised:
                        await nats_handler(key, {"args": [7]})
                    assert raised.value is failure
                else:
                    assert await nats_handler(key, {"args": [7]}) is result
                # 与 handler 同一存活线程，检查包装器已释放连接而非等待 GC。
                worker_id, closed = await sync_to_async(lambda: (threading.get_ident(), connections[alias].connection is None))()
                assert worker_id == worker_ids[-1]
                assert closed
                assert drivers[-1].closed
        finally:
            await cleanup_worker()

    async def cleanup_worker():
        # 在线程中解析连接对象，不能把主线程 wrapper 传给工作线程。
        await sync_to_async(lambda: connections[alias].close())()

    with django_db_blocker.unblock():
        main_db = connections[alias]
        try:
            assert Catalog.objects.using(alias).exists()
            main_driver = main_db.connection
            asyncio.run(exercise())
            assert main_db.connection is main_driver and not main_driver.closed
            assert len(drivers) == 3
        finally:
            main_db.close()
            del connections[alias]
