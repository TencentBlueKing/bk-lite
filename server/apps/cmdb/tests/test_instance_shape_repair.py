import json
import logging

import pytest
from django.core.cache import cache
from django.core.management import call_command

from apps.cmdb.constants.constants import ORGANIZATION
from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.models.repair_state import CmdbRepairState
from apps.cmdb.services.instance_shape_repair import (
    OUTCOME_CONFLICT,
    STAGE_DISPLAY_BACKFILL,
    STAGE_ORGANIZATION,
    STAGE_SCALAR,
    InstanceShapeRepair,
    defer_unique_rule,
)
from apps.cmdb.tasks.instance_shape_repair import repair_cmdb_instance_shape

pytestmark = pytest.mark.django_db


class _Graph:
    def __init__(self):
        self.organization_rows = []
        self.scalar_rows = []
        self.models = []
        self.instances = []
        self.model_queries = 0
        self.instance_queries = 0
        self.org_updates = []
        self.field_updates = []
        self.rule_writes = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def query_scalar_rows(self, statement, _params):
        if "n.model_id" in statement:
            rows = list(self.scalar_rows)
            self.scalar_rows = []
            return rows
        rows = list(self.organization_rows)
        self.organization_rows = []
        return rows

    def query_entity(self, label, _params, **_kwargs):
        if label == "model":
            self.model_queries += 1
            return list(self.models), len(self.models)
        self.instance_queries += 1
        page = list(self.instances)
        self.instances = []
        return page, len(page)

    def batch_update_node_properties(self, _label, node_ids, properties):
        self.org_updates.append((list(node_ids), properties))

    def batch_update_node_property_values(self, _label, field, values):
        self.field_updates.append((field, values))

    def set_entity_properties(self, *args, **_kwargs):
        self.rule_writes.append(args)


def _repair(graph, monkeypatch):
    monkeypatch.setattr("apps.cmdb.utils.base.get_default_group_id", lambda: [9])
    return InstanceShapeRepair(graph_client=lambda: graph, driver_name="falkordb")


def _finish_prefix():
    CmdbRepairState.objects.create(stage=STAGE_ORGANIZATION, completed=True)
    CmdbRepairState.objects.create(stage=STAGE_SCALAR, completed=True)


def _host_model(unique_rules):
    return {
        "_id": 10,
        "model_id": "host",
        "attrs": json.dumps(
            [
                {"attr_id": "ip_addr", "attr_name": "内网IP", "attr_type": "str", "is_required": True},
                {"attr_id": "cloud", "attr_name": "云区域", "attr_type": "str", "is_required": True},
                {"attr_id": "status", "attr_name": "状态", "attr_type": "enum", "is_required": False},
            ]
        ),
        "unique_rules": json.dumps(unique_rules),
    }


def test_organization_repair_fixes_missing_empty_and_integer_only(monkeypatch):
    graph = _Graph()
    graph.organization_rows = [
        {"id": 1, ORGANIZATION: 7},
        {"id": 2, ORGANIZATION: None},
        {"id": 3, ORGANIZATION: []},
        {"id": 4, ORGANIZATION: [3]},
        {"id": 5, ORGANIZATION: "9"},
        {"id": 6, ORGANIZATION: True},
    ]

    status = _repair(graph, monkeypatch).run()

    assert status == "done"
    assert graph.org_updates == [([1, 2, 3], {ORGANIZATION: [9]})]
    assert graph.model_queries == 1
    assert CmdbRepairState.objects.get(stage=STAGE_ORGANIZATION).completed is True
    assert CmdbRepairState.objects.get(stage=STAGE_SCALAR).completed is True


def test_full_organization_page_does_not_start_scalar_repair(monkeypatch):
    graph = _Graph()
    graph.organization_rows = [{"id": index, ORGANIZATION: 7} for index in range(1, 501)]

    def _models(*_args, **_kwargs):
        raise AssertionError("组织阶段未完成时不应查询模型或实例")

    graph.query_entity = _models
    status = _repair(graph, monkeypatch).run(budget=500)

    assert status == "continue"
    assert CmdbRepairState.objects.get(stage=STAGE_ORGANIZATION).completed is False
    assert not CmdbRepairState.objects.filter(stage=STAGE_SCALAR).exists()


def test_scalar_repair_wraps_non_list_values_after_organization_is_complete(monkeypatch):
    CmdbRepairState.objects.create(stage=STAGE_ORGANIZATION, completed=True)
    graph = _Graph()
    graph.models = [
        {
            "model_id": "host",
            "attrs": json.dumps(
                [
                    {"attr_id": "status", "attr_type": "enum"},
                    {"attr_id": "inst_name", "attr_type": "str"},
                ]
            ),
        }
    ]
    graph.scalar_rows = [
        {"id": 8, "status": "up"},
        {"id": 9, "status": ["ok"]},
        {"id": 10, "status": ""},
    ]

    status = _repair(graph, monkeypatch).run()

    assert status == "done"
    assert graph.field_updates == [("status", [{"id": 8, "value": ["up"]}])]
    assert CmdbRepairState.objects.get(stage=STAGE_SCALAR).completed is True


@pytest.fixture
def locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "instance-shape-repair",
        }
    }
    cache.clear()
    yield
    cache.clear()


def test_organization_budget_is_not_followed_by_scalar_in_the_same_run(monkeypatch):
    graph = _Graph()
    graph.organization_rows = [{"id": 1, ORGANIZATION: 7}]

    def _models(*_args, **_kwargs):
        raise AssertionError("本轮预算用完后不应开始标量阶段")

    graph.query_entity = _models
    status = _repair(graph, monkeypatch).run(budget=1)

    assert status == "continue"
    assert CmdbRepairState.objects.get(stage=STAGE_ORGANIZATION).completed is False
    assert not CmdbRepairState.objects.filter(stage=STAGE_SCALAR).exists()


def test_shape_repair_continue_schedules_one_second_later(monkeypatch, locmem_cache):
    queued = []
    monkeypatch.setattr(InstanceShapeRepair, "run", lambda self, budget=2000: "continue")
    monkeypatch.setattr(repair_cmdb_instance_shape, "apply_async", lambda **kwargs: queued.append(kwargs))

    result = repair_cmdb_instance_shape()

    assert result == {"status": "continue"}
    assert queued == [{"countdown": 1}]


def test_shape_repair_done_does_not_schedule_another_run(monkeypatch, locmem_cache):
    monkeypatch.setattr(InstanceShapeRepair, "run", lambda self, budget=2000: "done")
    monkeypatch.setattr(
        repair_cmdb_instance_shape,
        "apply_async",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("完成后不应再预约")),
    )

    assert repair_cmdb_instance_shape() == {"status": "done"}


def test_locked_shape_repair_does_not_run(monkeypatch, locmem_cache):
    monkeypatch.setattr(cache, "add", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        InstanceShapeRepair,
        "run",
        lambda self, budget=2000: (_ for _ in ()).throw(AssertionError("锁被占用时不应修复")),
    )

    assert repair_cmdb_instance_shape() == {"status": "locked"}


def test_expired_shape_lock_is_not_deleted_by_the_old_worker(locmem_cache):
    from apps.cmdb.tasks.instance_shape_repair import INSTANCE_SHAPE_REPAIR_LOCK, _release_shape_lock

    cache.set(INSTANCE_SHAPE_REPAIR_LOCK, "newer-token")
    _release_shape_lock("older-token")

    assert cache.get(INSTANCE_SHAPE_REPAIR_LOCK) == "newer-token"


def test_shape_repair_soft_timeout_keeps_secret_out_of_the_log(monkeypatch, locmem_cache, caplog):
    from celery.exceptions import SoftTimeLimitExceeded

    secret = "shape-repair-broker-secret"
    queued = []

    def _boom(self, budget=2000):
        raise SoftTimeLimitExceeded(secret)

    monkeypatch.setattr(InstanceShapeRepair, "run", _boom)
    monkeypatch.setattr(repair_cmdb_instance_shape, "apply_async", lambda **kwargs: queued.append(kwargs))

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        result = repair_cmdb_instance_shape()

    assert result == {"status": "retry", "reason": "soft_timeout"}
    assert queued == [{"countdown": 60}]
    records = [record for record in caplog.records if record.msg == "event=instance_shape_repair_soft_timeout failed_stage=repair error_type=%s"]
    assert len(records) == 1
    assert records[0].args == ("SoftTimeLimitExceeded",)
    assert records[0].getMessage() == "event=instance_shape_repair_soft_timeout failed_stage=repair error_type=SoftTimeLimitExceeded"
    assert secret not in records[0].getMessage()
    assert secret not in logging.Formatter().format(records[0])
    assert records[0].exc_info[0].__name__ == "SafeLogException"


def test_shape_repair_failure_log_owns_one_traceback(monkeypatch, locmem_cache, caplog):
    secret = "shape-repair-payload-secret"

    def _boom(self, budget=2000):
        raise RuntimeError(secret)

    monkeypatch.setattr(InstanceShapeRepair, "run", _boom)
    with caplog.at_level(logging.ERROR, logger="cmdb"):
        result = repair_cmdb_instance_shape()

    assert result == {"status": "retry", "reason": "repair_failed"}
    records = [record for record in caplog.records if record.msg == "event=instance_shape_repair_failed failed_stage=repair error_type=%s"]
    assert len(records) == 1
    assert records[0].args == ("RuntimeError",)
    assert records[0].getMessage() == "event=instance_shape_repair_failed failed_stage=repair error_type=RuntimeError"
    formatted = logging.Formatter().format(records[0])
    assert secret not in records[0].getMessage()
    assert secret not in formatted
    assert records[0].exc_info[2] is not None


def test_startup_enqueues_shape_repair_only_while_a_stage_is_open(monkeypatch):
    calls = []
    delays = []

    def _call(name, *_args, **_kwargs):
        calls.append(name)

    monkeypatch.setattr("apps.core.management.commands.batch_init.call_command", _call)
    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.ensure_display_field_backfill_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay", lambda **_kwargs: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task", lambda: None)
    monkeypatch.setattr("apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime.delay", lambda: None)
    monkeypatch.setattr(
        "apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape.delay",
        lambda: delays.append("shape"),
    )
    from apps.core.management.commands.batch_init import Command

    Command()._init_cmdb()
    assert "cmdb_migrate_scalar_to_list" not in calls
    assert delays == ["shape"]

    CmdbRepairState.objects.create(stage=STAGE_ORGANIZATION, completed=True)
    CmdbRepairState.objects.create(stage=STAGE_SCALAR, completed=True)
    Command()._init_cmdb()
    assert delays == ["shape"]

    defer_unique_rule("host", (("ip_addr",),))
    Command()._init_cmdb()
    assert delays == ["shape", "shape"]


def test_scalar_command_resets_stage_and_dry_run_does_not(monkeypatch):
    delays = []
    monkeypatch.setattr(
        "apps.cmdb.management.commands.cmdb_migrate_scalar_to_list.repair_cmdb_instance_shape.delay",
        lambda: delays.append("shape"),
    )
    CmdbRepairState.objects.create(stage=STAGE_SCALAR, completed=True, cursor="host|4")

    call_command("cmdb_migrate_scalar_to_list", "--dry-run")
    assert CmdbRepairState.objects.get(stage=STAGE_SCALAR).completed is True
    assert delays == []

    call_command("cmdb_migrate_scalar_to_list")
    row = CmdbRepairState.objects.get(stage=STAGE_SCALAR)
    assert row.completed is False
    assert row.cursor == ""
    assert delays == ["shape"]


def test_scalar_command_enqueue_failure_keeps_secret_out_of_the_log(monkeypatch, caplog):
    secret = "scalar-broker-secret"

    def _delay():
        raise ConnectionError(f"redis://:{secret}@broker/0")

    monkeypatch.setattr(
        "apps.cmdb.management.commands.cmdb_migrate_scalar_to_list.repair_cmdb_instance_shape.delay",
        _delay,
    )
    with caplog.at_level(logging.WARNING, logger="cmdb"):
        call_command("cmdb_migrate_scalar_to_list")

    assert CmdbRepairState.objects.get(stage=STAGE_SCALAR).completed is False
    records = [record for record in caplog.records if record.msg == "event=scalar_repair_enqueue_failed failed_stage=enqueue error_type=%s"]
    assert len(records) == 1
    assert records[0].args == ("ConnectionError",)
    assert records[0].getMessage() == "event=scalar_repair_enqueue_failed failed_stage=enqueue error_type=ConnectionError"
    assert secret not in records[0].getMessage()
    assert secret not in logging.Formatter().format(records[0])
    assert records[0].exc_info[2] is not None


def test_same_conflict_fingerprint_does_not_read_instances_again(monkeypatch, caplog):
    _finish_prefix()
    graph = _Graph()
    graph.models = [_host_model([])]
    graph.instances = [
        {"_id": 1, "ip_addr": "10.0.0.8", "cloud": "a"},
        {"_id": 2, "ip_addr": "10.0.0.8", "cloud": "a"},
    ]
    repair = _repair(graph, monkeypatch)
    defer_unique_rule("host", (("ip_addr", "cloud"),))

    with caplog.at_level(logging.WARNING, logger="cmdb"):
        assert repair.run() == "done"

    assert graph.instance_queries == 1
    assert "10.0.0.8" not in caplog.text
    row = CmdbRepairState.objects.get(stage="unique_rule:host")
    assert row.completed is True
    assert row.outcome == OUTCOME_CONFLICT
    assert graph.rule_writes == []

    graph.instances = [{"_id": 1, "ip_addr": "10.0.0.8", "cloud": "a"}, {"_id": 2, "ip_addr": "10.0.0.8", "cloud": "a"}]
    defer_unique_rule("host", (("ip_addr", "cloud"),))
    assert repair.run() == "done"
    assert graph.instance_queries == 1

    defer_unique_rule("host", (("ip_addr",),))
    row.refresh_from_db()
    assert row.completed is False
    graph.instances = [
        {"_id": 1, "ip_addr": "10.0.0.8"},
        {"_id": 2, "ip_addr": "10.0.0.8"},
    ]
    assert repair.run() == "done"
    assert graph.instance_queries == 2


def test_unique_rule_write_keeps_matching_rule_id(monkeypatch):
    _finish_prefix()
    graph = _Graph()
    graph.models = [_host_model([{"rule_id": "keep-me", "order": 1, "field_ids": ["ip_addr"]}])]
    repair = _repair(graph, monkeypatch)
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.invalidate_model_attrs",
        lambda _model_id: None,
    )
    defer_unique_rule("host", (("ip_addr",), ("cloud",)))

    assert repair.run() == "done"

    assert graph.instance_queries == 1
    written = json.loads(graph.rule_writes[0][2]["unique_rules"])
    assert written[0]["rule_id"] == "keep-me"
    assert written[0]["field_ids"] == ["ip_addr"]
    assert written[1]["field_ids"] == ["cloud"]
    assert CmdbRepairState.objects.get(stage="unique_rule:host").completed is True


def test_unchanged_field_group_is_not_saved(monkeypatch):
    group = FieldGroup.objects.create(
        model_id="host",
        group_name="网络",
        order=1,
        attr_orders=["ip"],
        created_by="system",
    )
    saved = []
    monkeypatch.setattr(FieldGroup, "save", lambda self, *args, **kwargs: saved.append(self.pk))

    class _Groups:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def query_entity(self, *_args, **_kwargs):
            attrs = [{"attr_id": "ip", "attr_group": "网络"}]
            return [{"_id": 1, "model_id": "host", "model_name": "主机", "attrs": json.dumps(attrs)}], 1

        def set_entity_properties(self, *_args, **_kwargs):
            raise AssertionError("分组未变化时不应回写模型")

    monkeypatch.setattr("apps.cmdb.management.commands.init_field_groups.GraphClient", lambda: _Groups())
    call_command("init_field_groups")

    assert saved == []
    group.refresh_from_db()
    assert group.attr_orders == ["ip"]


def test_models_only_display_init_does_not_preload_mappings(monkeypatch):
    from apps.cmdb.display_field.initializer import DisplayFieldInitializer

    initializer = DisplayFieldInitializer()
    monkeypatch.setattr(initializer, "_get_all_models", lambda: [{"model_id": "host", "_id": 1, "attrs": "[]"}])
    monkeypatch.setattr(initializer, "_add_display_fields_to_model", lambda _model: [])
    preloaded = []
    monkeypatch.setattr(initializer, "_preload_mappings", lambda _models: preloaded.append(True))

    initializer.initialize_all(instances=False)
    assert preloaded == []

    initializer.initialize_all(instances=True)
    assert preloaded == [True]


def test_new_display_field_marks_backfill_incomplete(monkeypatch):
    from apps.cmdb.display_field.initializer import DisplayFieldInitializer

    CmdbRepairState.objects.create(stage=STAGE_DISPLAY_BACKFILL, completed=True, cursor="")

    class _GraphClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def set_entity_properties(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr("apps.cmdb.display_field.initializer.GraphClient", lambda: _GraphClient())
    monkeypatch.setattr("apps.cmdb.display_field.cache.ExcludeFieldsCache.invalidate_model_attrs", lambda _model_id: None)
    DisplayFieldInitializer()._add_display_fields_to_model(
        {
            "_id": 3,
            "model_id": "host",
            "attrs": json.dumps([{"attr_id": "org", "attr_name": "组织", "attr_type": "organization", "attr_group": "g"}]),
        }
    )

    assert CmdbRepairState.objects.get(stage=STAGE_DISPLAY_BACKFILL).completed is False


def test_manual_display_backfill_marks_stage_complete(monkeypatch):
    class _Initializer:
        def initialize_all(self, *, instances):
            assert instances is True
            return {"success": True, "models_processed": 1, "instances_processed": 2, "errors": []}

    monkeypatch.setattr("apps.cmdb.management.commands.init_display_fields.DisplayFieldInitializer", _Initializer)
    call_command("init_display_fields")

    assert CmdbRepairState.objects.get(stage=STAGE_DISPLAY_BACKFILL).completed is True
