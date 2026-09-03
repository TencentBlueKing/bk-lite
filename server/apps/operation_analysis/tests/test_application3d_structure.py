from apps.operation_analysis.services.application3d.health import no_application_health, no_host_health, unavailable_health
from apps.operation_analysis.services.application3d.structure import compose_architecture_tree


def _health(reason="no_active_alarm"):
    if reason == "no_application":
        return no_application_health()
    if reason == "no_host":
        return no_host_health()
    if reason == "unavailable":
        return unavailable_health()
    return {
        "state": "normal",
        "reason": "no_active_alarm",
        "activeAlarmCount": 0,
        "severityCounts": {"critical": 0, "error": 0, "warning": 0, "info": 0},
        "noDataAlarmCount": 0,
        "highestSeverity": {"id": "normal", "label": "正常", "rank": 0, "color": "success"},
        "stale": False,
    }


def test_compose_architecture_tree_keeps_system_app_host_edges():
    tree = compose_architecture_tree(
        system_id="sys-1",
        system_name="门户系统",
        system_health=_health(),
        application_ids=["app-1", "app-2"],
        applications={
            "app-1": {"name": "门户", "health": _health()},
            "app-2": {"name": "订单", "health": _health()},
        },
        hosts_by_application={"app-1": ["host-1"], "app-2": ["host-2"]},
        hosts={
            "host-1": {"name": "web-1", "health": _health()},
            "host-2": {"name": "web-2", "health": _health()},
        },
    )

    assert tree["systemId"] == "sys-1"
    assert [node["id"] for node in tree["nodes"]] == ["sys-1", "app-1", "host-1", "app-2", "host-2"]
    assert [node["kind"] for node in tree["nodes"]] == ["system", "application", "host", "application", "host"]
    assert {(edge["sourceId"], edge["targetId"], edge["relation"]) for edge in tree["edges"]} == {
        ("sys-1", "app-1", "system_contains_application"),
        ("sys-1", "app-2", "system_contains_application"),
        ("app-1", "host-1", "application_run_host"),
        ("app-2", "host-2", "application_run_host"),
    }
    assert not any(edge["relation"] == "system_run_host" for edge in tree["edges"])
    assert not any(edge["sourceId"] == "sys-1" and edge["targetId"].startswith("host-") for edge in tree["edges"])


def test_compose_architecture_tree_dedupes_shared_host_with_multiple_edges():
    tree = compose_architecture_tree(
        system_id="sys-1",
        system_name="共享主机系统",
        system_health=_health(),
        application_ids=["app-1", "app-2"],
        applications={
            "app-1": {"name": "A", "health": _health()},
            "app-2": {"name": "B", "health": _health()},
        },
        hosts_by_application={"app-1": ["host-shared", "host-2"], "app-2": ["host-shared"]},
        hosts={
            "host-shared": {"name": "shared", "health": _health()},
            "host-2": {"name": "only-a", "health": _health()},
        },
    )

    host_nodes = [node for node in tree["nodes"] if node["kind"] == "host"]
    assert [node["id"] for node in host_nodes] == ["host-shared", "host-2"]
    shared_edges = [edge for edge in tree["edges"] if edge["targetId"] == "host-shared" and edge["relation"] == "application_run_host"]
    assert {(edge["sourceId"], edge["targetId"]) for edge in shared_edges} == {
        ("app-1", "host-shared"),
        ("app-2", "host-shared"),
    }


def test_compose_architecture_tree_empty_system_is_root_only():
    tree = compose_architecture_tree(
        system_id="sys-empty",
        system_name="空系统",
        system_health=_health("no_application"),
        application_ids=[],
        applications={},
        hosts_by_application={},
        hosts={},
    )

    assert [node["id"] for node in tree["nodes"]] == ["sys-empty"]
    assert tree["nodes"][0]["health"]["reason"] == "no_application"
    assert tree["edges"] == []
    assert tree["nodes"][0]["health"]["state"] != "normal"


def test_compose_architecture_tree_no_host_keeps_apps_without_host_nodes():
    tree = compose_architecture_tree(
        system_id="sys-1",
        system_name="无主机",
        system_health=_health("no_host"),
        application_ids=["app-1", "app-isolated"],
        applications={
            "app-1": {"name": "无主机应用", "health": _health("no_host")},
            "app-isolated": {"name": "孤立应用", "health": _health("no_host")},
        },
        hosts_by_application={"app-1": [], "app-isolated": []},
        hosts={},
    )

    assert [node["kind"] for node in tree["nodes"]] == ["system", "application", "application"]
    assert [node["id"] for node in tree["nodes"]] == ["sys-1", "app-1", "app-isolated"]
    assert {edge["relation"] for edge in tree["edges"]} == {"system_contains_application"}
    assert not any(node["kind"] == "host" for node in tree["nodes"])
    assert tree["nodes"][0]["health"]["reason"] == "no_host"
    assert tree["nodes"][0]["health"]["state"] != "normal"


def test_compose_architecture_tree_omits_invisible_apps_and_hosts():
    tree = compose_architecture_tree(
        system_id="sys-1",
        system_name="部分可见",
        system_health=_health("unavailable"),
        application_ids=["app-visible"],
        applications={"app-visible": {"name": "可见应用", "health": _health("unavailable")}},
        hosts_by_application={"app-visible": ["host-visible", "host-hidden"]},
        hosts={"host-visible": {"name": "可见主机", "health": _health("unavailable")}},
    )

    ids = {node["id"] for node in tree["nodes"]}
    assert ids == {"sys-1", "app-visible", "host-visible"}
    assert "app-hidden" not in ids
    assert "host-hidden" not in ids
    assert not any(edge["targetId"] == "host-hidden" for edge in tree["edges"])
