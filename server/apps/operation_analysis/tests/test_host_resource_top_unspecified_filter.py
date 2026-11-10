import json
import time
from pathlib import Path
from types import SimpleNamespace

from apps.monitor.nats import monitor as nm
from apps.monitor.services.host_resource_top import HostResourceTopService
from apps.operation_analysis.views.datasource_view import _resolve_request_params

SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"


def _host_top_source():
    entries = json.loads(SOURCE_API.read_text(encoding="utf-8"))
    return next(item for item in entries if item.get("rest_api") == "monitor/get_host_resource_top")


def _source_instance(source=None):
    source = source or _host_top_source()
    return SimpleNamespace(rest_api=source["rest_api"], params=source["params"])


def _authorize_two_hosts(monkeypatch):
    allowed = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)
    other = SimpleNamespace(id="host-2", name="web-2", ip="10.0.0.2", interval=300)
    monkeypatch.setattr(
        nm,
        "_get_nats_actor_scope",
        lambda user_info: (None, user_info.get("team"), False, frozenset({user_info.get("team")}), False, None),
    )
    monkeypatch.setattr(
        nm,
        "_get_authorized_monitor_instances",
        lambda user_info, scope_ids: ({"host-1": allowed, "host-2": other}, None),
    )
    return allowed, other


def _install_vm(monkeypatch, rows):
    queries = []

    class FakeVM:
        def query(self, query, **kwargs):
            queries.append(query)
            return {"status": "success", "data": {"result": rows}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    return queries


def _sample_rows():
    now = time.time()
    return [
        {"metric": {"instance_id": "host-1"}, "value": [now, "10"]},
        {"metric": {"instance_id": "host-2"}, "value": [now, "30"]},
    ]


def test_omitted_instance_ids_are_not_backfilled_from_source_default():
    source = _host_top_source()
    instance_ids = next(item for item in source["params"] if item["name"] == "instance_ids")
    assert instance_ids["value"] is None
    instance = _source_instance(source)

    for metric_type in ("cpu", "memory", "disk"):
        resolved = _resolve_request_params(instance, {"metric_type": metric_type})
        assert resolved == {"metric_type": metric_type}

    stale = json.loads(json.dumps(source))
    stale_ids = next(item for item in stale["params"] if item["name"] == "instance_ids")
    stale_ids["value"] = []
    resolved = _resolve_request_params(_source_instance(stale), {"metric_type": "memory"})
    assert resolved == {"metric_type": "memory"}


def test_explicit_empty_and_explicit_ids_stay_on_the_request():
    instance = _source_instance()
    empty = _resolve_request_params(instance, {"metric_type": "cpu", "instance_ids": []})
    assert empty == {"metric_type": "cpu", "instance_ids": []}
    chosen = _resolve_request_params(
        instance,
        {"metric_type": "disk", "instance_ids": ["host-1", "host-unauthorized"], "organization": "7"},
    )
    assert chosen == {
        "metric_type": "disk",
        "instance_ids": ["host-1", "host-unauthorized"],
        "organization": "7",
    }


def test_other_sources_still_backfill_an_empty_list_default():
    instance = SimpleNamespace(
        rest_api="monitor/get_host_metric_range",
        params=[{"name": "instance_ids", "type": "string", "value": [], "filterType": "filter"}],
    )
    assert _resolve_request_params(instance, {}) == {"instance_ids": []}


def test_unspecified_filter_queries_authorized_hosts_for_each_metric(monkeypatch):
    _authorize_two_hosts(monkeypatch)
    queries = _install_vm(monkeypatch, _sample_rows())
    instance = _source_instance()
    user_info = {"user": "u", "team": 1}

    for metric_type in ("cpu", "memory", "disk"):
        resolved = _resolve_request_params(instance, {"metric_type": metric_type})
        out = nm.get_host_resource_top(**resolved, user_info=user_info)
        assert out["result"] is True
        assert [row["instance_id"] for row in out["data"]] == ["host-2", "host-1"]
        assert queries[-1] == HostResourceTopService.METRIC_QUERIES[metric_type]


def test_explicit_empty_selection_does_not_query_or_fallback(monkeypatch):
    _authorize_two_hosts(monkeypatch)

    class FailVM:
        def __init__(self):
            raise AssertionError("empty selection must not query")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    resolved = _resolve_request_params(_source_instance(), {"metric_type": "memory", "instance_ids": []})
    out = nm.get_host_resource_top(**resolved, user_info={"user": "u", "team": 1})
    assert out == {"result": True, "data": [], "message": ""}


def test_explicit_ids_drop_unknown_and_unauthorized_without_widening_org(monkeypatch):
    seen = {}

    def scope(user_info):
        seen["team"] = user_info.get("team")
        return None, user_info.get("team"), False, frozenset({user_info.get("team")}), False, None

    def instances(user_info, scope_ids):
        seen["scope_ids"] = set(scope_ids)
        allowed = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)
        return {"host-1": allowed}, None

    monkeypatch.setattr(nm, "_get_nats_actor_scope", scope)
    monkeypatch.setattr(nm, "_get_authorized_monitor_instances", instances)
    queries = _install_vm(monkeypatch, _sample_rows())
    resolved = _resolve_request_params(
        _source_instance(),
        {
            "metric_type": "cpu",
            "instance_ids": ["host-1", "host-unauthorized", "missing-host"],
            "organization": "99",
        },
    )
    out = nm.get_host_resource_top(**resolved, user_info={"user": "u", "team": 1})

    assert out["result"] is True
    assert [row["instance_id"] for row in out["data"]] == ["host-1"]
    assert queries == [HostResourceTopService.METRIC_QUERIES["cpu"]]
    assert seen == {"team": 1, "scope_ids": {1}}

    unknown = _resolve_request_params(
        _source_instance(),
        {"metric_type": "disk", "instance_ids": ["missing-host"]},
    )

    class FailVM:
        def __init__(self):
            raise AssertionError("unknown ids must not query the whole scope")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.get_host_resource_top(**unknown, user_info={"user": "u", "team": 1})
    assert out == {"result": True, "data": [], "message": ""}
    assert seen["scope_ids"] == {1}
