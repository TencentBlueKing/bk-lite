import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.monitor.models import MonitorInstance, MonitorObject
from apps.monitor.services.authorized_metric_query import AuthorizedMetricQueryError, AuthorizedMetricQueryService
from apps.monitor.services.dashboard_query_capabilities import build_dashboard_query, dashboard_query_capability_id, load_dashboard_query_capabilities
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.views.metrics_instance import MetricsInstanceViewSet

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins"
METADATA_PATH = Path(__file__).resolve().parents[4] / "web" / "src" / "app" / "monitor" / "dashboards" / "metadata.ts"
METADATA_OBJECT_NAME_RE = re.compile(r"\{\s*key:\s*'([^']+)'[\s\S]*?objectName:\s*'([^']+)'[\s\S]*?\}")
SPELLING_KEY_RE = re.compile(r"[^a-z0-9]")


def _object(name="Website"):
    return MonitorObject(name=name, instance_id_keys=["instance_id"])


def _canonical_plugin_monitor_object_names() -> dict[str, str]:
    canonical_by_casefold: dict[str, str] = {}
    for path in PLUGIN_ROOT.rglob("metrics.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for name in MonitorPluginService._extract_monitor_object_names(data):
            key = name.casefold()
            existing = canonical_by_casefold.get(key)
            if existing is not None and existing != name:
                raise AssertionError(f"plugin monitor object name case conflict: {existing!r} vs {name!r} in {path}")
            canonical_by_casefold[key] = name
    return canonical_by_casefold


def _spelling_key(name: str) -> str:
    return SPELLING_KEY_RE.sub("", name.casefold())


def _canonical_plugin_names_by_spelling(canonical_by_casefold: dict[str, str]) -> dict[str, str]:
    by_spelling: dict[str, str] = {}
    for name in canonical_by_casefold.values():
        key = _spelling_key(name)
        existing = by_spelling.get(key)
        if existing is not None and existing != name:
            continue
        by_spelling[key] = name
    return by_spelling


def _metadata_object_names() -> list[tuple[str, str]]:
    source = METADATA_PATH.read_text(encoding="utf-8")
    return [(match.group(1), match.group(2)) for match in METADATA_OBJECT_NAME_RE.finditer(source)]


def _name_drift(name: str, canonical_by_casefold: dict[str, str], canonical_by_spelling: dict[str, str]) -> str | None:
    canonical = canonical_by_casefold.get(name.casefold())
    if canonical is None:
        canonical = canonical_by_spelling.get(_spelling_key(name))
    if canonical is not None and name != canonical:
        return canonical
    return None


def test_manifest_is_complete_and_content_addressed():
    capabilities = load_dashboard_query_capabilities()

    assert len(capabilities) >= 800
    assert all(capability.id == dashboard_query_capability_id(capability.template) for capability in capabilities.values())


def test_mongodb_capabilities_bind_canonical_plugin_object_name():
    load_dashboard_query_capabilities.cache_clear()
    capabilities = load_dashboard_query_capabilities()
    mongodb_caps = [item for item in capabilities.values() if "MongoDB" in item.object_names]
    drifted = [item.id for item in capabilities.values() if "Mongodb" in item.object_names]

    assert len(mongodb_caps) == 27
    assert drifted == []

    query = build_dashboard_query(
        capability_id=mongodb_caps[0].id,
        monitor_object=_object("MongoDB"),
        instance_ids=("('mongo-a',)",),
        start=0,
        end=60_000,
    )
    assert "__$" not in query
    assert 'instance_id=~"mongo\\\\-a"' in query


def test_capabilities_bind_canonical_plugin_object_names():
    canonical_by_casefold = _canonical_plugin_monitor_object_names()
    canonical_by_spelling = _canonical_plugin_names_by_spelling(canonical_by_casefold)
    assert canonical_by_casefold

    metadata_drifted = [
        (key, name, _name_drift(name, canonical_by_casefold, canonical_by_spelling))
        for key, name in _metadata_object_names()
        if _name_drift(name, canonical_by_casefold, canonical_by_spelling)
    ]
    assert metadata_drifted == []

    load_dashboard_query_capabilities.cache_clear()
    capabilities = load_dashboard_query_capabilities()
    drifted = []
    bound_canonical = set()
    for cap in capabilities.values():
        for name in cap.object_names:
            canonical = _name_drift(name, canonical_by_casefold, canonical_by_spelling)
            if canonical:
                drifted.append((cap.id, name, canonical))
                continue
            if name.casefold() in canonical_by_casefold:
                bound_canonical.add(name)

    assert drifted == []
    assert len(bound_canonical) >= 40
    assert "Nginx" in bound_canonical
    assert "MongoDB" in bound_canonical
    assert "nginx" not in bound_canonical
    assert "Mongodb" not in bound_canonical

    for canonical in sorted(bound_canonical):
        caps = [item for item in capabilities.values() if canonical in item.object_names]
        query = build_dashboard_query(
            capability_id=caps[0].id,
            monitor_object=_object(canonical),
            instance_ids=("('instance-a',)",),
            start=0,
            end=60_000,
        )
        assert "__$" not in query


def test_static_capability_injects_authorized_instance_and_server_window():
    capability = next(
        item for item in load_dashboard_query_capabilities().values() if "Website" in item.object_names and "__$window__" in item.template
    )

    query = build_dashboard_query(
        capability_id=capability.id,
        monitor_object=_object(),
        instance_ids=("('website-a',)",),
        start=0,
        end=3_600_000,
    )

    assert "__$" not in query
    assert 'instance_id=~"website\\\\-a"' in query
    assert "[1h]" in query


def test_capability_is_bound_to_monitor_object():
    capability = next(item for item in load_dashboard_query_capabilities().values() if "Website" in item.object_names)

    with pytest.raises(AuthorizedMetricQueryError, match="查询能力与监控对象不匹配"):
        build_dashboard_query(
            capability_id=capability.id,
            monitor_object=_object("Host"),
            instance_ids=("('host-a',)",),
            start=0,
            end=60_000,
        )


def test_unknown_capability_is_rejected():
    with pytest.raises(AuthorizedMetricQueryError, match="查询能力不存在"):
        build_dashboard_query(
            capability_id="dashboard:v1:ffffffff",
            monitor_object=_object(),
            instance_ids=("('website-a',)",),
            start=0,
            end=60_000,
        )


def test_dynamic_kafka_capability_escapes_dimensions_and_keeps_instance_scope():
    query = build_dashboard_query(
        capability_id="dashboard:dynamic:kafka:current-offset",
        monitor_object=_object("Kafka"),
        instance_ids=("('kafka-a',)",),
        start=0,
        end=60_000,
        params={
            "dimensions": [
                {
                    "consumer_group": 'group"a',
                    "topic": "orders",
                    "partition": "0",
                }
            ]
        },
    )

    assert 'instance_id=~"kafka\\\\-a"' in query
    assert 'consumergroup="group\\"a"' in query
    assert 'topic="orders"' in query


@pytest.mark.parametrize(
    "params",
    ["dimensions", {"dimensions": [{"consumer_group": "group-a", "topic": "x" * 257, "partition": "0"}]}],
)
def test_dynamic_kafka_capability_rejects_unbounded_params(params):
    with pytest.raises(AuthorizedMetricQueryError, match="Kafka 查询"):
        build_dashboard_query(
            capability_id="dashboard:dynamic:kafka:current-offset",
            monitor_object=_object("Kafka"),
            instance_ids=("('kafka-a',)",),
            start=0,
            end=60_000,
            params=params,
        )


def test_raw_promql_rest_actions_are_removed():
    assert not hasattr(MetricsInstanceViewSet, "get_metrics")
    assert not hasattr(MetricsInstanceViewSet, "get_metrics_range")


@pytest.mark.django_db
def test_authorized_service_executes_registered_capability(mocker):
    monitor_object = MonitorObject.objects.create(name="Website", instance_id_keys=["instance_id"])
    instance = MonitorInstance.objects.create(
        id="('website-a',)",
        name="website-a",
        monitor_object=monitor_object,
    )
    capability = next(item for item in load_dashboard_query_capabilities().values() if "Website" in item.object_names)
    vm_query = mocker.patch(
        "apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range",
        return_value={"status": "success", "data": {"result": []}},
    )

    result = AuthorizedMetricQueryService(
        user=SimpleNamespace(is_superuser=True),
        current_team=1,
        include_children=False,
    ).query_range(
        {
            "monitor_object_id": monitor_object.id,
            "capability_id": capability.id,
            "instance_ids": [instance.id],
            "start": 0,
            "end": 60_000,
            "step": "60s",
        }
    )

    assert result["status"] == "success"
    assert "__$" not in vm_query.call_args.args[0]


@pytest.mark.django_db
def test_capability_object_mismatch_stops_before_vm(mocker):
    monitor_object = MonitorObject.objects.create(name="Host", instance_id_keys=["instance_id"])
    instance = MonitorInstance.objects.create(
        id="('host-a',)",
        name="host-a",
        monitor_object=monitor_object,
    )
    capability = next(item for item in load_dashboard_query_capabilities().values() if "Website" in item.object_names)
    vm_query = mocker.patch("apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range")

    with pytest.raises(AuthorizedMetricQueryError, match="查询能力与监控对象不匹配"):
        AuthorizedMetricQueryService(
            user=SimpleNamespace(is_superuser=True),
            current_team=1,
            include_children=False,
        ).query_range(
            {
                "monitor_object_id": monitor_object.id,
                "capability_id": capability.id,
                "instance_ids": [instance.id],
                "start": 0,
                "end": 60_000,
                "step": "60s",
            }
        )

    vm_query.assert_not_called()
