"""待重算名单排空：单轮最多 200 行，5 分钟 Celery 任务重算 ci_context。"""

import pytest

from apps.cmdb.models.ci_context import CmdbCiContext, CmdbCiContextPending
from apps.cmdb.services.ci_context import _enqueue_ci_context_drain as _real_enqueue_ci_context_drain
from apps.cmdb.services.ci_context import drain_ci_context_pending, schedule_ci_context_pending
from apps.cmdb.services.ci_context_policy import CONTEXT_APPLICATION
from apps.cmdb.tests.test_ci_context_recompute import MemoryGraph, edge, inst

pytestmark = pytest.mark.django_db

TASK_NAME = "apps.cmdb.tasks.ci_context.reconcile_ci_context_pending_task"


def _bind(monkeypatch, instances, edges):
    graph = MemoryGraph(instances)
    graph.edges = list(edges)
    monkeypatch.setattr("apps.cmdb.services.ci_context.GraphClient", lambda *args, **kwargs: graph)
    return graph


def _context(**overrides):
    data = dict(
        ci_uuid="host-1",
        context=CONTEXT_APPLICATION,
        root_uuid="app-wecenter",
        root_model="application",
        ci_model="host",
        ip_addr="10.0.0.1",
        organization=[1],
        layer=1,
        model_asst_id="application_run_host",
    )
    data.update(overrides)
    return CmdbCiContext.objects.create(**data)


def _silence_enqueue(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.ci_context._enqueue_ci_context_drain", lambda: None)


def test_reconcile_task_is_a_five_minute_background_singleton():
    from celery.schedules import crontab

    from apps.cmdb.config import CELERY_BEAT_SCHEDULE
    from apps.cmdb.tasks.ci_context import reconcile_ci_context_pending_task
    from apps.core.celery_runtime.manifest import TASK_ROUTES

    entry = CELERY_BEAT_SCHEDULE["reconcile_ci_context_pending_task"]
    assert entry["task"] == TASK_NAME
    assert entry["schedule"] == crontab(minute="*/5")
    assert reconcile_ci_context_pending_task.lock_expiry == 30 * 60
    assert reconcile_ci_context_pending_task.raise_on_duplicate is False
    assert TASK_ROUTES[TASK_NAME] == "background"


def test_drain_root_uuid_projects_wecenter_host(monkeypatch):
    system = inst("sys-1", "system")
    app = inst("app-wecenter", "application")
    host = inst("host-1", "host", ip="10.1.0.1", org=[7])
    _bind(
        monkeypatch,
        [system, app, host],
        [edge("contains", system, app), edge("run", app, host)],
    )
    CmdbCiContextPending.objects.create(root_uuid="app-wecenter")

    result = drain_ci_context_pending()

    assert result["root_uuids"] == 1
    assert result["model_asst_ids"] == 0
    assert result["ci_uuids"] == 0
    row = CmdbCiContext.objects.get(ci_uuid="host-1", root_uuid="app-wecenter", context=CONTEXT_APPLICATION)
    assert row.layer == 1
    assert row.model_asst_id == "application_run_host"
    assert row.ip_addr == "10.1.0.1"
    assert CmdbCiContextPending.objects.count() == 0


def test_drain_model_asst_projects_application_host(monkeypatch):
    app = inst("app-wecenter", "application")
    host = inst("host-1", "host", ip="10.1.0.1", org=[7])
    _bind(monkeypatch, [app, host], [edge("run", app, host, model_asst_id="application_run_host")])
    CmdbCiContextPending.objects.create(model_asst_id="application_run_host")

    result = drain_ci_context_pending()

    assert result["model_asst_ids"] == 1
    row = CmdbCiContext.objects.get(ci_uuid="host-1", root_uuid="app-wecenter", context=CONTEXT_APPLICATION)
    assert row.ci_model == "host"
    assert row.layer == 1
    assert CmdbCiContextPending.objects.count() == 0


def test_drain_ci_uuid_refreshes_ip(monkeypatch):
    app = inst("app-wecenter", "application")
    host = inst("host-1", "host", ip="10.9.9.9", org=[4])
    _bind(monkeypatch, [app, host], [edge("run", app, host)])
    row = _context(ip_addr="10.0.0.1", organization=[1])
    CmdbCiContextPending.objects.create(ci_uuid="host-1")

    result = drain_ci_context_pending()

    assert result["ci_uuids"] == 1
    row.refresh_from_db()
    assert row.ip_addr == "10.9.9.9"
    assert CmdbCiContextPending.objects.filter(ci_uuid="host-1").count() == 0


def test_drain_ci_uuid_of_new_layer2_finds_app_via_host_membership(monkeypatch):
    app = inst("app-wecenter", "application")
    host = inst("host-1", "host", ip="10.1.0.1", org=[7])
    mysql = inst("mysql-1", "mysql", ip="10.1.0.3", org=[8])
    _bind(
        monkeypatch,
        [app, host, mysql],
        [edge("run", app, host), edge("run", host, mysql)],
    )
    _context(ci_uuid="host-1", root_uuid="app-wecenter", ip_addr="10.1.0.1", organization=[7])
    CmdbCiContextPending.objects.create(ci_uuid="mysql-1")

    drain_ci_context_pending()

    row = CmdbCiContext.objects.get(ci_uuid="mysql-1", root_uuid="app-wecenter", context=CONTEXT_APPLICATION)
    assert row.layer == 2
    assert row.via_uuid == "host-1"
    assert row.model_asst_id == "host_run_mysql"
    assert row.ip_addr == "10.1.0.3"
    assert CmdbCiContextPending.objects.filter(ci_uuid="mysql-1").count() == 0


def test_drain_application_ci_updates_member_ip_and_parent_root(monkeypatch):
    parent = inst("app-parent", "application")
    child = inst("app-child", "application", ip="10.8.8.8", org=[3])
    _bind(monkeypatch, [parent, child], [edge("run", parent, child)])
    row = _context(
        ci_uuid="app-child",
        ci_model="application",
        root_uuid="app-parent",
        ip_addr="1.1.1.1",
        organization=[9],
        layer=2,
        via_uuid="stale-via",
        model_asst_id="stale",
    )
    CmdbCiContextPending.objects.create(ci_uuid="app-child")

    drain_ci_context_pending()

    row.refresh_from_db()
    assert row.ip_addr == "10.8.8.8"
    assert row.organization == [3]
    assert row.root_uuid == "app-parent"
    assert row.layer == 1
    assert not row.via_uuid
    assert CmdbCiContextPending.objects.filter(ci_uuid="app-child").count() == 0


def test_missing_ci_failed_recompute_retries_and_drops_layer2(monkeypatch):
    from apps.cmdb.services.ci_context import recompute_application as real_recompute

    app = inst("app-wecenter", "application")
    host = inst("host-1", "host", ip="10.1.0.1", org=[7])
    mysql = inst("mysql-1", "mysql", ip="10.1.0.3", org=[8])
    _bind(monkeypatch, [app, mysql], [edge("run", app, host)])
    host_row = _context(ci_uuid="host-1", root_uuid="app-wecenter", layer=1, via_uuid=None, ip_addr="10.1.0.1", organization=[7])
    mysql_row = _context(
        ci_uuid="mysql-1",
        ci_model="mysql",
        root_uuid="app-wecenter",
        layer=2,
        via_uuid="host-1",
        model_asst_id="host_run_mysql",
        ip_addr="10.1.0.3",
        organization=[8],
    )
    kept = _context(ci_uuid="host-keep", root_uuid="other-app", via_uuid=None)
    CmdbCiContextPending.objects.create(ci_uuid="host-1")

    calls = {"n": 0}

    def flaky(root_uuid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("graph down")
        return real_recompute(root_uuid)

    monkeypatch.setattr("apps.cmdb.services.ci_context.recompute_application", flaky)

    drain_ci_context_pending()

    assert CmdbCiContextPending.objects.filter(ci_uuid="host-1").exists()
    host_row.refresh_from_db()
    mysql_row.refresh_from_db()
    assert mysql_row.layer == 2
    assert mysql_row.via_uuid == "host-1"
    kept.refresh_from_db()
    assert kept.root_uuid == "other-app"

    drain_ci_context_pending()

    assert not CmdbCiContext.objects.filter(ci_uuid="host-1").exists()
    assert not CmdbCiContext.objects.filter(ci_uuid="mysql-1", root_uuid="app-wecenter").exists()
    assert CmdbCiContext.objects.filter(pk=kept.pk, ci_uuid="host-keep", root_uuid="other-app").exists()
    assert CmdbCiContextPending.objects.filter(ci_uuid="host-1").count() == 0


def test_drain_ci_uuid_drops_rows_when_instance_is_missing(monkeypatch):
    _bind(monkeypatch, [], [])
    _context(ci_uuid="host-missing", root_uuid="app-wecenter")
    _context(ci_uuid="host-missing", root_uuid="app-other")
    kept = _context(ci_uuid="host-keep", root_uuid="app-untouched")
    CmdbCiContextPending.objects.create(ci_uuid="host-missing")

    drain_ci_context_pending()

    assert not CmdbCiContext.objects.filter(ci_uuid="host-missing").exists()
    assert CmdbCiContext.objects.filter(pk=kept.pk, ci_uuid="host-keep", root_uuid="app-untouched").exists()
    assert CmdbCiContextPending.objects.count() == 0


def test_claim_deletes_pending_before_recompute_and_duplicate_schedule_drains_clean(monkeypatch):
    pending_during = []

    def spy(_root_uuid):
        pending_during.append(CmdbCiContextPending.objects.count())

    monkeypatch.setattr("apps.cmdb.services.ci_context.recompute_application", spy)
    _silence_enqueue(monkeypatch)
    schedule_ci_context_pending(root_uuids=["app-1"])
    schedule_ci_context_pending(root_uuids=["app-1"])
    assert CmdbCiContextPending.objects.count() == 1

    drain_ci_context_pending()

    assert pending_during == [0]
    assert CmdbCiContextPending.objects.count() == 0


def test_failed_root_is_restored_and_later_roots_still_run(monkeypatch):
    def flaky(root_uuid):
        if root_uuid == "app-bad":
            raise RuntimeError("graph down")

    monkeypatch.setattr("apps.cmdb.services.ci_context.recompute_application", flaky)
    CmdbCiContextPending.objects.bulk_create(
        [
            CmdbCiContextPending(root_uuid="app-bad"),
            CmdbCiContextPending(root_uuid="app-ok"),
        ]
    )

    result = drain_ci_context_pending()

    assert result["root_uuids"] == 1
    assert list(CmdbCiContextPending.objects.values_list("root_uuid", flat=True)) == ["app-bad"]


def test_drain_claims_at_most_200_rows(monkeypatch):
    CmdbCiContextPending.objects.bulk_create([CmdbCiContextPending(root_uuid=f"app-{index:04d}") for index in range(201)])
    calls = []
    monkeypatch.setattr("apps.cmdb.services.ci_context.recompute_application", lambda root_uuid: calls.append(root_uuid))

    result = drain_ci_context_pending()

    assert result["root_uuids"] == 200
    assert len(calls) == 200
    assert CmdbCiContextPending.objects.count() == 1
    assert CmdbCiContextPending.objects.get().root_uuid not in calls


def test_schedule_enqueues_drain_after_insert_and_skips_empty(monkeypatch):
    calls = []

    def mark():
        calls.append(CmdbCiContextPending.objects.count())

    monkeypatch.setattr("apps.cmdb.services.ci_context._enqueue_ci_context_drain", mark)

    schedule_ci_context_pending(root_uuids=["app-real"])

    assert calls == [1]
    assert CmdbCiContextPending.objects.filter(root_uuid="app-real").exists()

    schedule_ci_context_pending()
    schedule_ci_context_pending(root_uuids=["", None, "  "], model_asst_ids=[], ci_uuids=None)
    assert calls == [1]


def test_enqueue_swallows_delay_errors(monkeypatch):
    from apps.cmdb.tasks.ci_context import reconcile_ci_context_pending_task

    monkeypatch.setattr("apps.cmdb.services.ci_context._enqueue_ci_context_drain", _real_enqueue_ci_context_drain)
    calls = {"n": 0}

    def boom(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("broker down")

    monkeypatch.setattr(reconcile_ci_context_pending_task, "delay", boom)

    schedule_ci_context_pending(root_uuids=["app-real"])

    assert calls["n"] == 1
    assert CmdbCiContextPending.objects.filter(root_uuid="app-real").exists()
