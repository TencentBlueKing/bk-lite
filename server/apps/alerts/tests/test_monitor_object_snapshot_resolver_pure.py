"""Alert 监控对象快照集合的纯归并契约。"""

from types import SimpleNamespace

from apps.alerts.service.monitor_object_snapshot import resolve_monitor_objects


def _event(pk, monitor_id, cmdb_id, resource_type, resource_name, **overrides):
    values = {
        "pk": pk,
        "monitor_id": monitor_id,
        "cmdb_id": cmdb_id,
        "resource_type": resource_type,
        "resource_name": resource_name,
        "resource_id": monitor_id,
        "push_source_id": "lite-monitor",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_resolve_monitor_objects_deduplicates_requirement_example():
    events = [
        _event(1, "0001", "xxxx1", "Host", "ip1"),
        _event(2, "0001", "xxxx1", "Host", "ip1"),
        _event(3, "0001", "xxxx1", "Host", "ip1"),
        _event(4, "0002", "xxxx2", "Switch", "ip2"),
    ]

    assert resolve_monitor_objects(events) == [
        {
            "monitor_id": "0001",
            "cmdb_id": "xxxx1",
            "resource_type": "Host",
            "resource_name": "ip1",
        },
        {
            "monitor_id": "0002",
            "cmdb_id": "xxxx2",
            "resource_type": "Switch",
            "resource_name": "ip2",
        },
    ]


def test_resolve_monitor_objects_does_not_deduplicate_by_resource_name():
    events = [
        _event(1, "monitor-a", "cmdb-a", "Host", "shared-name"),
        _event(2, "monitor-b", "cmdb-b", "Host", "shared-name"),
    ]

    result = resolve_monitor_objects(events)

    assert [item["monitor_id"] for item in result] == ["monitor-a", "monitor-b"]


def test_resolve_monitor_objects_keeps_monitor_without_cmdb_link():
    event = _event(1, "monitor-unlinked", None, "Host", "unlinked-host")

    assert resolve_monitor_objects([event]) == [
        {
            "monitor_id": "monitor-unlinked",
            "cmdb_id": None,
            "resource_type": "Host",
            "resource_name": "unlinked-host",
        }
    ]


def test_resolve_monitor_objects_fills_only_empty_snapshot_slots():
    events = [
        _event(1, "monitor-fill", None, None, ""),
        _event(2, "monitor-fill", "cmdb-fill", "Switch", "switch-1"),
    ]

    assert resolve_monitor_objects(events) == [
        {
            "monitor_id": "monitor-fill",
            "cmdb_id": "cmdb-fill",
            "resource_type": "Switch",
            "resource_name": "switch-1",
        }
    ]


def test_resolve_monitor_objects_keeps_first_non_empty_snapshot_values():
    events = [
        _event(1, "monitor-conflict", "cmdb-first", "Host", "host-first"),
        _event(2, "monitor-conflict", "cmdb-later", "Switch", "host-later"),
    ]

    assert resolve_monitor_objects(events) == [
        {
            "monitor_id": "monitor-conflict",
            "cmdb_id": "cmdb-first",
            "resource_type": "Host",
            "resource_name": "host-first",
        }
    ]


def test_resolve_monitor_objects_never_infers_monitor_id_from_other_ids():
    event = _event(
        1,
        None,
        "cmdb-only",
        "Host",
        "vendor-host",
        resource_id="vendor-resource",
    )

    assert resolve_monitor_objects([event]) == []


def test_resolve_monitor_objects_uses_explicit_identity_without_source_coupling():
    event = _event(
        1,
        "explicit-monitor",
        "explicit-cmdb",
        "Host",
        "explicit-host",
        push_source_id="another-compatible-producer",
    )

    assert resolve_monitor_objects([event])[0]["monitor_id"] == "explicit-monitor"


def test_resolve_monitor_objects_normalizes_monitor_id_whitespace():
    events = [
        _event(1, " monitor-spaced ", None, " Host ", " host-1 "),
        _event(2, "monitor-spaced", " cmdb-1 ", "Switch", "host-2"),
    ]

    assert resolve_monitor_objects(events) == [
        {
            "monitor_id": "monitor-spaced",
            "cmdb_id": "cmdb-1",
            "resource_type": "Host",
            "resource_name": "host-1",
        }
    ]


def test_resolve_monitor_objects_returns_empty_list_for_empty_input():
    assert resolve_monitor_objects([]) == []
