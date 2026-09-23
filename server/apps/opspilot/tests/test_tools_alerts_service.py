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
        rpc_cls.return_value.list_alerts.return_value = {"result": True, "data": {"count": 0, "items": []}}
        out = alerts_list_alerts.invoke({"status": "unassigned", "page": 1}, config=cfg())
    assert out["success"] is True
    rpc_cls.return_value.list_alerts.assert_called_once()
    kwargs = rpc_cls.return_value.list_alerts.call_args.kwargs
    assert kwargs["user_info"]["user"] == "alice"
    assert kwargs["query_data"]["status"] == "unassigned"


def test_alerts_detail_requires_alert_id():
    out = alerts_get_alert_detail.invoke({"alert_id": ""}, config=cfg())
    assert out["error"] == "alert_id is required"


def test_alerts_events_maps_to_rpc():
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alert_events.return_value = {"result": True, "data": {"count": 1, "items": [{"event_id": "e1"}]}}
        out = alerts_list_alert_events.invoke({"alert_id": "ALERT-1"}, config=cfg())
    assert out["data"]["items"][0]["event_id"] == "e1"


def test_alerts_list_uses_question_terms_instead_of_glued_keyword():
    config = cfg()
    config["configurable"]["user_message"] = "下单接口超时了，有没有 timeout"
    with patch("apps.opspilot.metis.llm.tools.alerts.utils.AlertOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_alerts.return_value = {"result": True, "data": {"count": 0, "items": []}}
        out = alerts_list_alerts.invoke({"keyword": "下单超时"}, config=config)
    keywords = rpc_cls.return_value.list_alerts.call_args.kwargs["query_data"]["keywords"]
    assert "下单接口" in keywords
    assert "timeout" in keywords
    assert "下单超时" not in keywords
    assert out["searched_keywords"] == keywords
    out = alerts_list_alerts.invoke({}, config={"configurable": {}})
    assert "caller_identity" in out["error"]
