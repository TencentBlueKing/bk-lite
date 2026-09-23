"""Issue #5855：Flow 会话列表不得把 unwrap 后的无界聚合交给 VM，fold 上限 1000。"""

from types import SimpleNamespace

import pytest

import apps.cmdb.models  # noqa: F401  INSTALL_APPS 需含 cmdb（monitor.nats.monitor 导入 cmdb.services）
import apps.node_mgmt.models  # noqa: F401  INSTALL_APPS 需含 node_mgmt（monitor.apps.ready → nats.monitor）
from apps.monitor.services import flow_conversations
from apps.monitor.services.authorized_metric_query import AuthorizedMetricQueryError
from apps.monitor.services.flow_conversations import (
    MAX_CONVERSATION_SERIES,
    parse_conversation_rows,
    query_flow_conversation_page,
)

EXPECTED_MAX_SERIES = 1000
INNER_CONVERSATION_QUERY = "sum(rate(netflow_in_bytes[60s])) by (src, src_port, dst, dst_port, protocol)"
PREPARED_TOPN_QUERY = f"topk(10, {INNER_CONVERSATION_QUERY})"
BOUNDED_QUERY = f"topk({EXPECTED_MAX_SERIES}, {INNER_CONVERSATION_QUERY})"


def _prepared(query: str = PREPARED_TOPN_QUERY) -> SimpleNamespace:
    return SimpleNamespace(query=query, end=1_700_000_000_000)


def _authorized(query: str = PREPARED_TOPN_QUERY):
    return SimpleNamespace(prepare=lambda payload: _prepared(query))


def _series_item(index: int, *, src: str, value: float) -> dict:
    return {
        "metric": {
            "src": src,
            "src_port": "12345",
            "dst": "8.8.8.8",
            "dst_port": "80",
            "protocol": "6",
        },
        "value": [1_700_000_000, str(value)],
    }


def _budget_series(count: int = 1500) -> list[dict]:
    """高流量在前：前 50 条匹配 10.0.1，预算外 500 条也匹配但不该被物化。"""
    series = []
    for index in range(count):
        if index < 50 or index >= EXPECTED_MAX_SERIES:
            src = f"10.0.1.{index}"
        else:
            src = f"10.0.0.{index}"
        series.append(_series_item(index, src=src, value=float(count - index)))
    return series


def _success_vm(series: list[dict]) -> dict:
    return {"status": "success", "data": {"result": series}}


def test_conversation_query_wraps_unwrapped_inner_with_topk_budget(mocker):
    captured = {}

    def fake_get_metrics(query, time=None):
        captured["query"] = query
        captured["time"] = time
        return _success_vm([])

    mocker.patch("apps.monitor.services.flow_conversations.Metrics.get_metrics", side_effect=fake_get_metrics)

    query_flow_conversation_page(authorized_service=_authorized(), payload={"page": 1, "page_size": 10})

    assert MAX_CONVERSATION_SERIES == EXPECTED_MAX_SERIES
    assert captured["query"] == BOUNDED_QUERY
    assert INNER_CONVERSATION_QUERY in captured["query"]
    assert captured["query"] != INNER_CONVERSATION_QUERY
    assert "topk(1000," in captured["query"].replace(" ", "")


def test_parse_conversation_rows_caps_fold_at_max_series(mocker):
    series = _budget_series(1500)
    spy = mocker.spy(flow_conversations, "fold_instant_rows")

    rows = parse_conversation_rows(_success_vm(series))

    limit = spy.call_args.kwargs.get("limit")
    if limit is None:
        limit = spy.call_args.args[2]
    assert limit == EXPECTED_MAX_SERIES
    assert len(rows) == EXPECTED_MAX_SERIES
    assert {row["src"] for row in rows if str(row.get("src") or "").startswith("10.0.1.")} == {
        f"10.0.1.{index}" for index in range(50)
    }


def test_keyword_filter_and_pagination_stay_within_budget(mocker):
    mocker.patch(
        "apps.monitor.services.flow_conversations.Metrics.get_metrics",
        return_value=_success_vm(_budget_series(1500)),
    )

    page = query_flow_conversation_page(
        authorized_service=_authorized(),
        payload={"keyword": "10.0.1", "page": 2, "page_size": 10},
    )

    assert page["count"] == 50
    assert page["page"] == 2
    assert page["page_size"] == 10
    assert len(page["items"]) == 10
    assert [item["src_ip"] for item in page["items"]] == [f"10.0.1.{index}" for index in range(10, 20)]
    overflow_src = {f"10.0.1.{index}" for index in range(EXPECTED_MAX_SERIES, 1500)}
    assert overflow_src.isdisjoint(item["src_ip"] for item in page["items"])


def test_non_conversation_query_still_rejected(mocker):
    vm = mocker.patch("apps.monitor.services.flow_conversations.Metrics.get_metrics")

    with pytest.raises(AuthorizedMetricQueryError) as exc_info:
        query_flow_conversation_page(
            authorized_service=_authorized("topk(10, sum(rate(netflow_in_bytes[60s])) by (protocol))"),
            payload={"page": 1, "page_size": 10},
        )

    assert exc_info.value.code == "capability_not_conversation"
    vm.assert_not_called()
