"""default_config 变化时刷新已有预置正文，未变化时不查节点配置。"""

import logging
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import connection
from django.db.models.signals import post_save
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.core.logger import SafeLogException
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.management.services.node_init.collector_init import import_collector
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import ChildConfig, Collector, CollectorConfiguration, CollectorDefaultBackfill, Node, NodeCollectorConfiguration
from apps.node_mgmt.services.collector_default_backfill import render_builtin_default_template
from apps.node_mgmt.services.collector_preset_refresh import COMPLETED_LOG, ETAG_FAILED_LOG, FAILED_LOG, INCONSISTENT_BINDING_LOG
from apps.node_mgmt.services.sidecar_cache import build_configuration_etag_cache_key
from apps.node_mgmt.signals import invalidate_configuration_render_etag
from apps.node_mgmt.tasks.collector_default_backfill import backfill_collector_default_configs

SECRET_SENTINEL = "password=PRESET-REFRESH-SECRET"
BODY_SENTINEL = "PRESET-BODY-SENTINEL"
CONFIG_TABLE = "node_mgmt_collectorconfiguration"
BINDING_TABLE = "node_mgmt_nodecollectorconfiguration"
CHILD_TABLE = "node_mgmt_childconfig"
VECTOR_PATH = Path(__file__).resolve().parents[1] / "support-files" / "collectors" / "Vector.json"
COLLECT_TYPE_PATH = Path(__file__).resolve().parents[2] / "log" / "support-files" / "plugins" / "Snmptrapd" / "network" / "collect_type.json"
SYSLOG_VRL = """.collector = "Vector"
.collect_type = "syslog"
.instance_id = "base"
.cloud_region_id = "${node.cloud_region}"
.received_at = now()
if !exists(.timestamp) {
  .timestamp = now()
}

raw_hostname = ""
if exists(.hostname) && is_string(.hostname) {
  raw_hostname = strip_whitespace(string!(.hostname))
}
if raw_hostname == "" {
  .hostname = ""
} else {
  .hostname = raw_hostname
}
"""
pytestmark = pytest.mark.django_db


@pytest.fixture
def locmem_cache(settings):
    """根 conftest 把缓存换成 DummyCache，get 永远是 None，测不到「没清」的 ETag。"""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "collector-preset-refresh",
        }
    }
    cache.clear()
    yield
    cache.clear()


def _region():
    return CloudRegion.objects.create(name=f"cr-preset-{uuid.uuid4().hex[:8]}")


def _node(region, suffix, **over):
    data = dict(
        id=f"node-preset-{suffix}",
        name=f"n-{suffix}",
        ip=f"10.8.0.{suffix}",
        operating_system="linux",
        cpu_architecture="x86_64",
        collector_configuration_directory="/opt/fusion-collectors",
        cloud_region=region,
    )
    data.update(over)
    return Node.objects.create(**data)


def _payload(collector_id="telegraf-linux-x64", **over):
    data = dict(
        id=collector_id,
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        cpu_architecture="x86_64",
        executable_path="/opt/fusion-collectors/bin/telegraf",
        execute_parameters="-c",
        controller_default_run=True,
        default_config={"nats": "interval = 10"},
        tags=[],
    )
    data.update(over)
    return data


def _pre_config(collector, node, template, *, name=None, is_pre=True):
    config = CollectorConfiguration.objects.create(
        name=name or f"{collector.name}-{node.id}-{uuid.uuid4().hex[:6]}",
        collector=collector,
        config_template=template,
        is_pre=is_pre,
        cloud_region=node.cloud_region,
    )
    if node is not None:
        config.nodes.add(node)
    return config


def _queries(captured, table):
    return [query for query in captured if table in query["sql"].lower()]


def _selects(captured, table):
    return [query for query in _queries(captured, table) if query["sql"].lstrip().lower().startswith("select")]


def _etag(node, config):
    return build_configuration_etag_cache_key(node.id, config.id)


def _snmp_trap_parse_block(add_config):
    start = add_config.index("[transforms.snmp_trap_parse]")
    end = add_config.index("[sinks.snmp_trap_nats]")
    return add_config[start:end]


def _remap_source(block):
    marker = "source = '''\n"
    start = block.index(marker) + len(marker)
    end = block.index("'''", start)
    return block[start:end]


def test_unchanged_default_config_does_not_query_configurations():
    region = _region()
    node = _node(region, 1)
    default_config = {"nats": "interval = 10", "add_config": ""}
    import_collector([_payload(default_config=default_config)])
    collector = Collector.objects.get(id="telegraf-linux-x64")
    config = _pre_config(collector, node, "hand-edited")

    with CaptureQueriesContext(connection) as same:
        assert import_collector([_payload(default_config={"nats": "interval = 10", "add_config": ""})]) is None
    assert _queries(same, CONFIG_TABLE) == []
    assert _queries(same, BINDING_TABLE) == []
    assert _queries(same, CHILD_TABLE) == []

    # 键顺序不同，字典仍然相等。
    reordered = _payload(default_config={"add_config": "", "nats": "interval = 10"})
    with CaptureQueriesContext(connection) as reordered_queries:
        assert import_collector([reordered]) is None
    assert _queries(reordered_queries, CONFIG_TABLE) == []

    with CaptureQueriesContext(connection) as renamed:
        renamed_payload = _payload(default_config={"add_config": "", "nats": "interval = 10"}, introduction="renamed")
        assert import_collector([renamed_payload]) is None
    assert _queries(renamed, CONFIG_TABLE) == []
    config.refresh_from_db()
    collector.refresh_from_db()
    assert config.config_template == "hand-edited"
    assert collector.introduction == "renamed"
    assert collector.default_config == default_config


def test_only_changed_collector_presets_are_rewritten(caplog):
    region = _region()
    changed_node = _node(region, 1, ip="10.66.66.66")
    other_node = _node(region, 2, ip="10.66.66.67")
    import_collector(
        [
            _payload(default_config={"nats": "old"}),
            _payload("vector-linux-x64", name="Vector", default_config={"nats": "vector-old"}),
        ]
    )
    changed = Collector.objects.get(id="telegraf-linux-x64")
    other = Collector.objects.get(id="vector-linux-x64")
    changed_config = _pre_config(changed, changed_node, "old")
    other_config = _pre_config(other, other_node, "vector-old")
    caplog.set_level(logging.DEBUG, logger="node")
    changed_payload = _payload(default_config={"nats": f"new {BODY_SENTINEL}"})
    unchanged_payload = _payload("vector-linux-x64", name="Vector", default_config={"nats": "vector-old"})

    with patch(
        "apps.node_mgmt.services.collector_default_backfill.RegionService.get_cloud_region_envconfig",
        return_value={"SIDECAR_INPUT_MODE": "nats", "NATS_PASSWORD": SECRET_SENTINEL},
    ) as envconfig:
        assert import_collector([changed_payload, unchanged_payload]) is None
    assert envconfig.called

    changed_config.refresh_from_db()
    other_config.refresh_from_db()
    assert changed_config.config_template == f"new {BODY_SENTINEL}"
    assert other_config.config_template == "vector-old"
    records = [record for record in caplog.records if record.msg == COMPLETED_LOG]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.INFO
    assert record.args[0] == changed.id
    assert record.args[1:4] == (1, 1, 0)
    assert isinstance(record.args[4], int)
    assert record.getMessage() == COMPLETED_LOG % record.args
    formatted = logging.Formatter().format(record)
    assert BODY_SENTINEL not in formatted
    assert SECRET_SENTINEL not in formatted
    assert changed_node.ip not in formatted
    assert BODY_SENTINEL not in caplog.text
    assert SECRET_SENTINEL not in caplog.text
    assert changed_node.ip not in caplog.text
    assert not any(item.levelno == logging.ERROR for item in caplog.records)


def test_container_preset_keeps_placeholders_and_skips_unchanged_host_custom_and_child():
    region = _region()
    host = _node(region, 1)
    container = _node(region, 2, ip="10.8.0.2", node_type=ControllerConstants.NODE_TYPE_CONTAINER)
    custom_node = _node(region, 3, ip="10.8.0.3")
    other_node = _node(region, 4, ip="10.8.0.4")
    old_default = {"nats": "base ${node.ip}", "add_config": "extra ${node.cloud_region}"}
    import_collector(
        [
            _payload(default_config=old_default),
            _payload("vector-linux-x64", name="Vector", default_config={"nats": "vector-old"}),
        ]
    )
    collector = Collector.objects.get(id="telegraf-linux-x64")
    other = Collector.objects.get(id="vector-linux-x64")
    host_config = _pre_config(collector, host, "base ${node.ip}")
    container_config = _pre_config(collector, container, "base ${node.ip}\nextra ${node.cloud_region}")
    custom = _pre_config(collector, custom_node, "user-kept", is_pre=False)
    child = ChildConfig.objects.create(
        collect_type="snmp_trap",
        config_type="file",
        content="child-kept",
        collector_config=container_config,
    )
    other_config = _pre_config(other, other_node, "vector-old")
    new_default = {"nats": "base ${node.ip}", "add_config": "extra2 ${node.cloud_region}"}
    vector_payload = _payload("vector-linux-x64", name="Vector", default_config={"nats": "vector-old"})

    with CaptureQueriesContext(connection) as captured:
        assert import_collector([_payload(default_config=new_default), vector_payload]) is None

    host_config.refresh_from_db()
    container_config.refresh_from_db()
    custom.refresh_from_db()
    child.refresh_from_db()
    other_config.refresh_from_db()
    assert host_config.config_template == "base ${node.ip}"
    assert container_config.config_template == "base ${node.ip}\nextra2 ${node.cloud_region}"
    assert "${node.ip}" in container_config.config_template
    assert "${node.cloud_region}" in container_config.config_template
    assert custom.config_template == "user-kept"
    assert custom.is_pre is False
    assert child.content == "child-kept"
    assert other_config.config_template == "vector-old"
    assert _queries(captured, CHILD_TABLE) == []
    assert host_config.cloud_region_id == region.id
    assert host_config.name
    assert host_config.env_config == {}


def test_hand_edited_preset_is_overwritten_and_identical_render_skips_etag(django_capture_on_commit_callbacks, locmem_cache):
    region = _region()
    edited_node = _node(region, 1)
    same_node = _node(region, 2, ip="10.8.0.2")
    import_collector([_payload(default_config={"nats": "v1"})])
    collector = Collector.objects.get(id="telegraf-linux-x64")
    edited = _pre_config(collector, edited_node, "hand-edited")
    same = _pre_config(collector, same_node, "v2")
    edited_before = (edited.cloud_region_id, edited.name, edited.is_pre, edited.env_config)
    edited_key = _etag(edited_node, edited)
    same_key = _etag(same_node, same)
    cache.set(edited_key, "edited-etag")
    cache.set(same_key, "same-etag")

    with django_capture_on_commit_callbacks(execute=True):
        assert import_collector([_payload(default_config={"nats": "v2"})]) is None

    edited.refresh_from_db()
    same.refresh_from_db()
    assert edited.config_template == "v2"
    assert (edited.cloud_region_id, edited.name, edited.is_pre, edited.env_config) == edited_before
    assert same.config_template == "v2"
    assert cache.get(edited_key) is None
    assert cache.get(same_key) == "same-etag"


def test_rewritten_preset_etag_is_cleared_without_post_save(django_capture_on_commit_callbacks, locmem_cache):
    region = _region()
    node = _node(region, 1)
    import_collector([_payload(default_config={"nats": "v1"})])
    collector = Collector.objects.get(id="telegraf-linux-x64")
    config = _pre_config(collector, node, "v1")
    key = _etag(node, config)
    cache.set(key, "etag-value")
    post_save.disconnect(invalidate_configuration_render_etag, sender=CollectorConfiguration)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            assert import_collector([_payload(default_config={"nats": "v2"})]) is None
        config.refresh_from_db()
        assert config.config_template == "v2"
        assert cache.get(key) is None
    finally:
        post_save.connect(invalidate_configuration_render_etag, sender=CollectorConfiguration)


def test_refresh_failure_keeps_old_default_config_and_retries(caplog):
    region = _region()
    bad_node = _node(region, 1)
    good_node = _node(region, 2, ip="10.8.0.2")
    bad_old = _payload("bad-collector", name="BadCollector", introduction="old-intro", default_config={"nats": "old-bad"})
    good_old = _payload("good-collector", name="GoodCollector", default_config={"nats": "old-good"})
    bad_new = _payload(
        "bad-collector",
        name="BadCollector",
        introduction="new-intro",
        default_config={"nats": f"new-bad {BODY_SENTINEL}"},
    )
    good_new = _payload("good-collector", name="GoodCollector", default_config={"nats": f"new-good {BODY_SENTINEL}"})
    import_collector([bad_old, good_old])
    bad = Collector.objects.get(id="bad-collector")
    good = Collector.objects.get(id="good-collector")
    bad_config = _pre_config(bad, bad_node, "old-bad")
    good_config = _pre_config(good, good_node, "old-good")
    error = RuntimeError(SECRET_SENTINEL)

    def render(collector, variables, *, is_container_node):
        if collector.id == "bad-collector":
            raise error
        return render_builtin_default_template(collector, variables, is_container_node=is_container_node)

    caplog.set_level(logging.DEBUG, logger="node")
    with patch("apps.node_mgmt.services.collector_preset_refresh.render_builtin_default_template", side_effect=render):
        assert import_collector([bad_new, good_new]) is None

    bad.refresh_from_db()
    good.refresh_from_db()
    bad_config.refresh_from_db()
    good_config.refresh_from_db()
    assert bad.default_config == {"nats": "old-bad"}
    assert bad.introduction == "new-intro"
    assert bad_config.config_template == "old-bad"
    assert good.default_config == {"nats": f"new-good {BODY_SENTINEL}"}
    assert good_config.config_template == f"new-good {BODY_SENTINEL}"
    assert error.args == (SECRET_SENTINEL,)
    error_records = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.msg == FAILED_LOG
    assert record.args == (bad.id, "render", "RuntimeError")
    assert record.getMessage() == FAILED_LOG % record.args
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[1].args == ("RuntimeError",)
    assert record.exc_info[2] is error.__traceback__
    formatted = logging.Formatter().format(record)
    assert SECRET_SENTINEL not in formatted
    assert BODY_SENTINEL not in formatted
    assert SECRET_SENTINEL not in caplog.text
    assert BODY_SENTINEL not in caplog.text

    caplog.clear()
    assert import_collector([bad_new, good_new]) is None
    bad.refresh_from_db()
    bad_config.refresh_from_db()
    good_config.refresh_from_db()
    assert bad.default_config == {"nats": f"new-bad {BODY_SENTINEL}"}
    assert bad_config.config_template == f"new-bad {BODY_SENTINEL}"
    assert good_config.config_template == f"new-good {BODY_SENTINEL}"
    assert not any(item.levelno == logging.ERROR for item in caplog.records)


def test_second_import_of_same_file_does_not_query_configurations():
    region = _region()
    node = _node(region, 1)
    import_collector([_payload(default_config={"nats": "v1"})])
    collector = Collector.objects.get(id="telegraf-linux-x64")
    config = _pre_config(collector, node, "v1")
    assert import_collector([_payload(default_config={"nats": "v2"})]) is None
    config.refresh_from_db()
    assert config.config_template == "v2"

    with CaptureQueriesContext(connection) as captured:
        assert import_collector([_payload(default_config={"nats": "v2"})]) is None
    assert _queries(captured, CONFIG_TABLE) == []
    assert _queries(captured, BINDING_TABLE) == []
    config.refresh_from_db()
    assert config.config_template == "v2"


def test_new_collector_still_writes_backfill_without_rewriting_other_presets():
    region = _region()
    node = _node(region, 1)
    other_node = _node(region, 2, ip="10.8.0.2")
    other = Collector.objects.create(
        id="vector-linux-x64",
        name="Vector",
        service_type="svc",
        node_operating_system="linux",
        cpu_architecture="x86_64",
        executable_path="/bin/vector",
        execute_parameters="-c",
        controller_default_run=True,
        default_config={"nats": "vector"},
        is_pre=True,
    )
    other_config = _pre_config(other, other_node, "vector-old")

    assert import_collector([_payload()]) is None
    assert CollectorDefaultBackfill.objects.filter(collector_id="telegraf-linux-x64", status="pending").count() == 1
    assert not CollectorConfiguration.objects.filter(collector_id="telegraf-linux-x64").exists()
    other_config.refresh_from_db()
    assert other_config.config_template == "vector-old"

    backfill_collector_default_configs()
    assert CollectorConfiguration.objects.filter(collector_id="telegraf-linux-x64", nodes=node, is_pre=True).exists()
    other_config.refresh_from_db()
    assert other_config.config_template == "vector-old"


def test_refresh_five_thousand_presets_queries_by_batch():
    region = _region()
    node = _node(region, 1)
    import_collector([_payload(default_config={"nats": "old"})])
    collector = Collector.objects.get(id="telegraf-linux-x64")
    now = timezone.now()
    CollectorConfiguration.objects.bulk_create(
        [
            CollectorConfiguration(
                id=f"c{index:05d}",
                name=f"pre-{index:05d}",
                collector=collector,
                config_template="old",
                is_pre=True,
                cloud_region=region,
                created_at=now,
                updated_at=now,
            )
            for index in range(5000)
        ],
        batch_size=200,
    )
    CollectorConfiguration.objects.create(
        id="custom-keep",
        name="custom-keep",
        collector=collector,
        config_template="custom-keep",
        is_pre=False,
        cloud_region=region,
    )
    NodeCollectorConfiguration.objects.bulk_create(
        [NodeCollectorConfiguration(node=node, collector_config_id=f"c{index:05d}") for index in range(5000)],
        batch_size=200,
    )

    started = time.perf_counter()
    with CaptureQueriesContext(connection) as captured:
        assert import_collector([_payload(default_config={"nats": "v2"})]) is None
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    config_selects = _selects(captured, CONFIG_TABLE)
    binding_selects = _selects(captured, BINDING_TABLE)
    print(f"preset_refresh_5000_elapsed_ms={elapsed_ms} " f"config_selects={len(config_selects)} binding_selects={len(binding_selects)}")
    assert len(config_selects) == 11
    assert 10 <= len(binding_selects) <= 30
    assert len(config_selects) + len(binding_selects) < 80
    assert _queries(captured, CHILD_TABLE) == []
    assert CollectorConfiguration.objects.filter(collector=collector, is_pre=True, config_template="v2").count() == 5000
    assert CollectorConfiguration.objects.get(id="custom-keep").config_template == "custom-keep"
    assert Collector.objects.get(id=collector.id).default_config == {"nats": "v2"}


def test_non_default_run_collector_updates_catalog_without_querying_presets():
    region = _region()
    node = _node(region, 1)
    import_collector([_payload(default_config={"nats": "old"})])
    collector = Collector.objects.get(id="telegraf-linux-x64")
    config = _pre_config(collector, node, "old")

    with CaptureQueriesContext(connection) as captured:
        assert import_collector([_payload(controller_default_run=False, default_config={"nats": "new"}, introduction="catalog-only")]) is None

    assert _queries(captured, CONFIG_TABLE) == []
    assert _queries(captured, BINDING_TABLE) == []
    collector.refresh_from_db()
    config.refresh_from_db()
    assert collector.controller_default_run is False
    assert collector.default_config == {"nats": "new"}
    assert collector.introduction == "catalog-only"
    assert config.config_template == "old"


def test_refresh_skips_unbound_inconsistent_and_non_container_targets(caplog, django_capture_on_commit_callbacks, locmem_cache):
    region = _region()
    other_region = _region()
    first = _node(region, 2, ip="10.8.0.2")
    second = _node(other_region, 3, ip="10.8.0.3")
    host = _node(region, 4, ip="10.8.0.4")
    container = _node(region, 5, ip="10.8.0.5", node_type=ControllerConstants.NODE_TYPE_CONTAINER)
    import_collector(
        [
            _payload(default_config={"nats": "old"}),
            _payload(
                "snmptrapd-linux",
                name="Snmptrapd",
                default_config={"nats": "base", "add_config": "extra"},
            ),
        ]
    )
    collector = Collector.objects.get(id="telegraf-linux-x64")
    snmp = Collector.objects.get(id="snmptrapd-linux")
    unbound = CollectorConfiguration.objects.create(
        name="unbound-pre",
        collector=collector,
        config_template="leave-unbound",
        is_pre=True,
        cloud_region=region,
    )
    inconsistent = _pre_config(collector, first, "leave-inconsistent", name="inconsistent-pre")
    inconsistent.nodes.add(second)
    host_config = _pre_config(snmp, host, "keep-host", name="snmp-host")
    container_config = _pre_config(snmp, container, "old-container", name="snmp-container")
    inconsistent_key = _etag(first, inconsistent)
    host_key = _etag(host, host_config)
    cache.set(inconsistent_key, "inconsistent-etag")
    cache.set(host_key, "host-etag")
    caplog.set_level(logging.DEBUG, logger="node")

    with django_capture_on_commit_callbacks(execute=True):
        assert (
            import_collector(
                [
                    _payload(default_config={"nats": "new"}),
                    _payload(
                        "snmptrapd-linux",
                        name="Snmptrapd",
                        default_config={"nats": "base-2", "add_config": "extra-2"},
                    ),
                ]
            )
            is None
        )

    unbound.refresh_from_db()
    inconsistent.refresh_from_db()
    host_config.refresh_from_db()
    container_config.refresh_from_db()
    assert unbound.config_template == "leave-unbound"
    assert inconsistent.config_template == "leave-inconsistent"
    assert host_config.config_template == "keep-host"
    assert container_config.config_template == "base-2\nextra-2"
    assert cache.get(inconsistent_key) == "inconsistent-etag"
    assert cache.get(host_key) == "host-etag"
    assert Collector.objects.get(id=collector.id).default_config == {"nats": "new"}
    assert Collector.objects.get(id=snmp.id).default_config == {"nats": "base-2", "add_config": "extra-2"}
    debug_records = [record for record in caplog.records if record.msg == INCONSISTENT_BINDING_LOG]
    assert len(debug_records) == 1
    assert debug_records[0].levelno == logging.DEBUG
    assert debug_records[0].args == (collector.id, inconsistent.id)
    assert debug_records[0].getMessage() == INCONSISTENT_BINDING_LOG % debug_records[0].args


def test_etag_invalidation_failure_does_not_fail_refresh(caplog):
    region = _region()
    node = _node(region, 1)
    import_collector([_payload(default_config={"nats": "v1"})])
    collector = Collector.objects.get(id="telegraf-linux-x64")
    config = _pre_config(collector, node, "v1")
    error = RuntimeError(SECRET_SENTINEL)
    caplog.set_level(logging.DEBUG, logger="node")

    with patch(
        "apps.node_mgmt.services.collector_preset_refresh.invalidate_configuration_etags",
        side_effect=error,
    ):
        assert import_collector([_payload(default_config={"nats": f"v2 {BODY_SENTINEL}"})]) is None

    collector.refresh_from_db()
    config.refresh_from_db()
    assert collector.default_config == {"nats": f"v2 {BODY_SENTINEL}"}
    assert config.config_template == f"v2 {BODY_SENTINEL}"
    assert error.args == (SECRET_SENTINEL,)
    warnings = [record for record in caplog.records if record.msg == ETAG_FAILED_LOG]
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning.levelno == logging.WARNING
    assert warning.exc_info is None
    assert warning.args == (collector.id, "RuntimeError")
    assert warning.getMessage() == ETAG_FAILED_LOG % warning.args
    assert SECRET_SENTINEL not in logging.Formatter().format(warning)
    assert BODY_SENTINEL not in logging.Formatter().format(warning)
    assert SECRET_SENTINEL not in caplog.text
    assert not any(record.levelno == logging.ERROR for record in caplog.records)


def test_linux_vector_trap_fields_survive_template_render():
    import json

    collectors = json.loads(VECTOR_PATH.read_text())
    linux = [item for item in collectors if item["id"] in {"Vector_linux", "Vector_linux_arm64"}]
    windows = [item for item in collectors if item["id"] == "Vector_windows"]
    assert [item["id"] for item in linux] == ["Vector_linux", "Vector_linux_arm64"]
    assert len(windows) == 1
    assert windows[0]["default_config"]["add_config"] == ""

    blocks = [_snmp_trap_parse_block(item["default_config"]["add_config"]) for item in linux]
    assert blocks[0] == blocks[1]
    source = _remap_source(blocks[0])
    assert source == _remap_source(blocks[1])
    assert ".source_ip = source_ip" in source
    assert ".agent_addr = agent_addr" in source
    assert '.cloud_region_id = "${node.cloud_region}"' in source
    assert '.node_ip = "${node.ip}"' in source
    assert "${node.cloud_region_id}" not in source
    for token in ("{{", "{%", "{#"):
        assert token not in source
    for item in linux:
        add_config = item["default_config"]["add_config"]
        assert add_config.count(SYSLOG_VRL) == 1
        assert "raw_hostname" not in _snmp_trap_parse_block(add_config)
        rendered = render_builtin_default_template(
            SimpleNamespace(name="Vector", default_config={"nats": "BASE", "add_config": add_config}),
            {"SIDECAR_INPUT_MODE": "nats"},
            is_container_node=True,
        )
        assert _snmp_trap_parse_block(rendered) == _snmp_trap_parse_block(add_config)
        assert "${node.cloud_region}" in rendered
    rendered_source = render_builtin_default_template(
        SimpleNamespace(name="Vector", default_config={"nats": source}),
        {"SIDECAR_INPUT_MODE": "nats", "NATS_PROTOCOL": "tls", "HOST": "10.1.1.1"},
        is_container_node=False,
    )
    # Jinja 默认丢掉模板末尾的一个换行；其余字符必须与源一致，占位符保持字面量。
    assert source.endswith("\n")
    assert rendered_source == source[:-1]
    assert "${node.cloud_region}" in rendered_source

    collect_type = json.loads(COLLECT_TYPE_PATH.read_text())
    assert collect_type["default_query"] == "collect_type: snmp_trap | last 1 by (_time) partition by (node_ip)"
    assert collect_type["attrs"][-3:] == ["source_ip", "cloud_region_id", "agent_addr"]
