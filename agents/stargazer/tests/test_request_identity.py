from types import SimpleNamespace

from core.collection.request_identity import (
    build_request_task_id,
    canonicalize_headers,
    canonicalize_query,
)


def test_canonicalize_headers_order_independent():
    left = canonicalize_headers({"host": "a", "b": "2", "a": "1"})
    right = canonicalize_headers({"a": "1", "b": "2", "Host": "other"})
    assert left == right == "a:1\nb:2"


def test_canonicalize_query_order_independent():
    left = canonicalize_query("b=2&a=1&a=0")
    right = canonicalize_query("a=0&a=1&b=2")
    assert left == right == "a=0&a=1&b=2"
    assert canonicalize_query({"b": "2", "a": ["0", "1"]}) == left


def test_build_request_task_id_stable_across_header_and_query_order():
    first = build_request_task_id(
        "GET",
        "/api/collect/collect_info",
        "cmdbhosts=10.0.0.1&cmdbplugin_name=mysql_info",
        {"cmdbpassword": "secret", "cmdbhost": "db", "User-Agent": "telegraf"},
    )
    second = build_request_task_id(
        "get",
        "/api/collect/collect_info",
        "cmdbplugin_name=mysql_info&cmdbhosts=10.0.0.1",
        {
            "User-Agent": "curl/8",
            "cmdbhost": "db",
            "cmdbpassword": "secret",
            "Host": "stargazer:8083",
            "X-Task-ID": "caller-should-be-ignored",
        },
    )
    assert first == second
    assert first.startswith("req_")
    assert len(first) == 4 + 64


def test_build_request_task_id_changes_when_business_header_changes():
    base = dict(host="10.0.0.1", username="root", password="secret")
    left = build_request_task_id("GET", "/api/monitor/host/metrics", "", base)
    right = build_request_task_id(
        "GET", "/api/monitor/host/metrics", "", {**base, "password": "other"}
    )
    assert left != right


def test_noise_headers_alone_do_not_change_identity():
    business = {"instance_id": "cmdb_1", "host": "10.0.0.1"}
    left = build_request_task_id("GET", "/api/monitor/host/metrics", "", business)
    right = build_request_task_id(
        "GET",
        "/api/monitor/host/metrics",
        "",
        {
            **business,
            "User-Agent": "changed",
            "Host": "other",
            "Accept": "*/*",
            "X-Forwarded-For": "1.2.3.4",
            "X-Task-ID": "old-id",
        },
    )
    assert left == right


def test_path_difference_changes_identity():
    headers = {"host": "10.0.0.1"}
    collect = build_request_task_id("GET", "/api/collect/collect_info", "", headers)
    monitor = build_request_task_id("GET", "/api/monitor/host/metrics", "", headers)
    assert collect != monitor


def test_build_from_request_object():
    request = SimpleNamespace(
        method="GET",
        path="/api/collect/collect_info",
        query_string="b=2&a=1",
        headers={"cmdbhost": "db", "x-task-id": "ignored"},
    )
    from core.collection.request_identity import build_request_task_id_from_request

    assert build_request_task_id_from_request(request) == build_request_task_id(
        "GET",
        "/api/collect/collect_info",
        "b=2&a=1",
        {"cmdbhost": "db", "x-task-id": "ignored"},
    )
