"""Alerts LLM tools: NATS RPC wrappers with caller_identity."""

from unittest.mock import patch

import pytest

from apps.opspilot.metis.llm.tools.alerts import alerts_get_alert_detail, alerts_list_alert_events, alerts_list_alerts


@pytest.fixture(autouse=True)
def _skip_db_cleanup_on_tool_invoke(mocker):
    mocker.patch("apps.opspilot.utils.db_cleanup.close_old_connections")


CALLER_IDENTITY = {
    "username": "alice",
    "domain": "tenant-a.com",
    "team_id": 12,
    "include_children": False,
}


def cfg():
    return {"configurable": {"caller_identity": CALLER_IDENTITY}}


def test_alerts_constructor_has_no_identity_params():
    from apps.opspilot.metis.llm.tools.alerts import CONSTRUCTOR_PARAMS

    assert CONSTRUCTOR_PARAMS == []


def test_alerts_list_maps_to_rpc():
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = alert_page(0)
        out = alerts_list_alerts.invoke({"status": "unassigned", "page": 1}, config=cfg())
    assert out["success"] is True
    rpc_cls.return_value.list_alerts.assert_called_once()
    kwargs = rpc_cls.return_value.list_alerts.call_args.kwargs
    assert kwargs["user_info"]["user"] == "alice"
    assert kwargs["query_data"]["status"] == "unassigned"


def test_alerts_list_sends_created_time_bounds_and_omits_them_when_absent():
    config = cfg()
    config["configurable"]["user_timezone"] = "Asia/Shanghai"
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = {"result": True, "data": {"count": 1, "items": []}}
        alerts_list_alerts.invoke(
            {"start": "2026-10-17 00:00:00", "end": "2026-11-17T10:41:15Z"},
            config=config,
        )
        alerts_list_alerts.invoke({"page": 1}, config=config)
        invalid = alerts_list_alerts.invoke({"start": "上个月"}, config=config)
    window = rpc_cls.return_value.list_alerts.call_args_list[0].kwargs["query_data"]
    assert window["start"] == "2026-10-16T16:00:00.000Z"
    assert window["end"] == "2026-11-17T10:41:15.000Z"
    assert "status" in window
    assert window["status"] is None
    plain = rpc_cls.return_value.list_alerts.call_args_list[1].kwargs["query_data"]
    assert "start" not in plain
    assert "end" not in plain
    assert invalid["error"]
    assert rpc_cls.return_value.list_alerts.call_count == 2


def test_alerts_detail_requires_alert_id():
    out = alerts_get_alert_detail.invoke({"alert_id": ""}, config=cfg())
    assert out["error"] == "alert_id is required"


def test_alerts_events_maps_to_rpc():
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alert_events.return_value = {"result": True, "data": {"count": 1, "items": [{"event_id": "e1"}]}}
        out = alerts_list_alert_events.invoke({"alert_id": "ALERT-1"}, config=cfg())
    assert out["data"]["items"][0]["event_id"] == "e1"


def test_alerts_list_active_count_matches_activity_page_filter():
    config = cfg()
    config["configurable"]["user_message"] = "我现在有多少条活动告警"
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = alert_page(3)
        out = alerts_list_alerts.invoke({"status": "active", "keyword": "活动", "page_size": 20}, config=config)
    query_data = rpc_cls.return_value.list_alerts.call_args.kwargs["query_data"]
    assert query_data["keywords"] == []
    assert query_data["status"] == "active"
    assert out["data"]["count"] == 3
    assert "searched_keywords" not in out


def test_alerts_list_status_question_does_not_send_keywords():
    config = cfg()
    config["configurable"]["user_message"] = "查询活动告警"
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = alert_page(4)
        alerts_list_alerts.invoke({"status": "active", "keyword": "活动"}, config=config)
    query_data = rpc_cls.return_value.list_alerts.call_args.kwargs["query_data"]
    assert query_data["keywords"] == []
    assert query_data["status"] == "active"


def test_alerts_list_inventory_question_does_not_send_keywords():
    config = cfg()
    config["configurable"]["user_message"] = "当前告警有哪些"
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = alert_page(5)
        out = alerts_list_alerts.invoke({"status": "active", "page_size": 20}, config=config)
    query_data = rpc_cls.return_value.list_alerts.call_args.kwargs["query_data"]
    assert query_data["keywords"] == []
    assert query_data["status"] == "active"
    assert "searched_keywords" not in out
    assert "search_note" not in out


def test_alerts_list_uses_question_terms_instead_of_glued_keyword():
    config = cfg()
    config["configurable"]["user_message"] = "下单接口超时了，有没有 timeout"
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = alert_page(0)
        out = alerts_list_alerts.invoke({"keyword": "下单超时"}, config=config)
    keywords = rpc_cls.return_value.list_alerts.call_args.kwargs["query_data"]["keywords"]
    assert "下单接口" not in keywords
    assert "timeout" in keywords
    assert "下单超时" not in keywords
    assert out["searched_keywords"] == keywords
    out = alerts_list_alerts.invoke({}, config={"configurable": {}})
    assert "caller_identity" in out["error"]


def alert_page(count, page=1, page_size=100, start=None, size=None):
    start = (page - 1) * page_size if start is None else start
    size = min(page_size, max(0, count - start)) if size is None else size
    return {
        "result": True,
        "data": {
            "count": count,
            "page": page,
            "page_size": page_size,
            "items": [{"alert_id": f"ALERT-{i}", "item": "cpu_usage"} for i in range(start, start + size)],
        },
    }


def test_default_alert_query_fetches_all_pages_with_same_identity_and_filters():
    config = cfg()
    config["configurable"]["user_message"] = "查看db-01的活动告警"
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc = rpc_cls.return_value.list_alerts
        rpc.side_effect = [alert_page(203, page=i) for i in (1, 2, 3)]
        out = alerts_list_alerts.invoke({"status": "active", "level": "0", "keyword": "db-01", "page_size": 100}, config=config)
    assert out["success"] is True
    data = out["data"]
    assert data["complete"] is True
    assert data["count"] == data["retrieved_count"] == len(data["items"]) == 203
    assert data["pages_fetched"] == 3
    assert data["items"][-1]["alert_id"] == "ALERT-202"
    assert "page_size" not in data and "page" not in data
    calls = [call.kwargs for call in rpc.call_args_list]
    assert [c["query_data"]["page"] for c in calls] == [1, 2, 3]
    assert all(c["user_info"] == calls[0]["user_info"] for c in calls)
    assert all(
        {k: v for k, v in c["query_data"].items() if k != "page"} == {"status": "active", "level": "0", "keywords": ["db-01"], "page_size": 100}
        for c in calls
    )


@pytest.mark.parametrize("page,complete,next_page", [(1, False, 2), (3, False, None)])
def test_explicit_single_page_does_not_claim_full_result(page, complete, next_page):
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = alert_page(203, page=page)
        out = alerts_list_alerts.invoke({"status": "active", "fetch_all": False, "page": page, "page_size": 100}, config=cfg())
    rpc_cls.return_value.list_alerts.assert_called_once()
    assert out["data"]["page"] == page
    assert out["data"]["complete"] is complete
    assert out["data"]["next_page"] == next_page


def test_complete_empty_query_is_successful():
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = alert_page(0)
        out = alerts_list_alerts.invoke({}, config=cfg())
    assert out["success"] is True and out["data"]["complete"] is True
    assert out["data"]["items"] == [] and out["data"]["retrieved_count"] == 0


@pytest.mark.parametrize(
    "responses,error",
    [
        ([alert_page(1001)], "limit"),
        ([alert_page(203), {"result": False, "message": "page unavailable"}], "page unavailable"),
        ([alert_page(203), alert_page(204, page=2)], "changed"),
        ([alert_page(203), alert_page(203, page=2, start=0)], "duplicate"),
        ([alert_page(203), alert_page(203, page=2, size=0)], "progress"),
        ([alert_page(203, size=101)], "page"),
        ([alert_page(203), TimeoutError("rpc timeout")], "rpc timeout"),
        ([{"result": True, "data": {"count": True, "items": []}}], "page"),
        ([{"result": True, "data": {"count": 1, "page": 1, "page_size": 100, "items": [{}]}}], "alert_id"),
    ],
)
def test_incomplete_fetch_fails_without_exposing_partial_rows(responses, error):
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.side_effect = responses
        out = alerts_list_alerts.invoke({"status": "active"}, config=cfg())
    assert out["success"] is False and out["complete"] is False
    assert error in out["error"]
    assert "items" not in out and "data" not in out


def test_complete_fetch_rejects_later_start_page_without_rpc():
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        out = alerts_list_alerts.invoke({"page": 2}, config=cfg())
    assert out["success"] is False and out["complete"] is False
    rpc_cls.assert_not_called()


def test_complete_fetch_limits_utf8_bytes():
    page = alert_page(1)
    page["data"]["items"][0]["content"] = "警" * 350000
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = page
        out = alerts_list_alerts.invoke({}, config=cfg())
    assert out["success"] is False and out["complete"] is False
    assert "byte limit" in out["error"] and "items" not in out


def test_complete_fetch_accepts_exact_record_limit():
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.side_effect = [alert_page(1000, page=i) for i in range(1, 11)]
        out = alerts_list_alerts.invoke({}, config=cfg())
    assert out["success"] is True and out["data"]["retrieved_count"] == 1000
    assert out["data"]["pages_fetched"] == 10


def test_single_page_complete_only_when_it_contains_all_records():
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = alert_page(3, page_size=20)
        out = alerts_list_alerts.invoke({"fetch_all": False, "page_size": 20}, config=cfg())
    assert out["data"]["complete"] is True
    assert out["data"]["next_page"] is None
    assert rpc_cls.return_value.list_alerts.call_args.kwargs["query_data"]["page_size"] == 20
