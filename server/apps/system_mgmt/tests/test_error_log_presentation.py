from apps.system_mgmt.utils.error_log_presentation import (
    apply_display_mask,
    apply_export_mask,
    expand_app_filter_values,
    present_error_log,
    request_path_without_query,
)

PARSED_MESSAGE = "[GET] /api/v1/monitor/alert_rule/\n错误类型: ValueError\n错误信息: node_id 必填"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc"


def test_parsed_template_fields():
    presented = present_error_log(
        app="monitor",
        error_message=PARSED_MESSAGE,
        stack_trace="File x\n",
        mapping={},
    )
    assert presented.parsed is True
    assert presented.reason == "node_id 必填"
    assert presented.exception_type == "ValueError"
    assert presented.method == "GET"
    assert presented.path == "/api/v1/monitor/alert_rule/"
    assert "?" not in presented.path
    assert presented.stack_text == "File x\n"


def test_parsed_path_drops_query():
    message = "[GET] /api/v1/monitor/alert_rule/?token=abc\n错误类型: ValueError\n错误信息: node_id 必填"
    presented = present_error_log(app="monitor", error_message=message, mapping={})
    assert presented.parsed is True
    assert presented.path == "/api/v1/monitor/alert_rule/"
    assert "token=****" in presented.recorded_text


def test_free_text_stays_unparsed():
    presented = present_error_log(app="monitor", error_message="NATS boom", mapping={})
    assert presented.parsed is False
    assert presented.recorded_text == "NATS boom"
    assert presented.method == ""
    assert presented.path == ""
    assert presented.exception_type == ""
    assert presented.reason == ""


def test_display_mask_query_and_password_but_not_sentence_token():
    text = "GET /x/?token=abc&x=1 password=hunter2 Invalid or expired token node_id 必填"
    masked = apply_display_mask(text)
    assert "?token=****&x=****" in masked
    assert "password=****" in masked
    assert "Invalid or expired token" in masked
    assert "node_id 必填" in masked
    assert "hunter2" not in masked
    assert "abc" not in masked


def test_list_display_mask_does_not_apply_jwt():
    text = f"failed {JWT}"
    assert JWT in apply_display_mask(text)
    assert JWT not in apply_export_mask(text)
    assert "****" in apply_export_mask(text)


def test_system_mgmt_maps_to_console_id_for_display():
    presented = present_error_log(app="system_mgmt", error_message="x", mapping={})
    assert presented.app_name == "system-manager"
    unknown = present_error_log(app="not-a-console-app", error_message="x", mapping={})
    assert unknown.app_name == "not-a-console-app"


def test_app_filter_aliases_system_manager():
    assert set(expand_app_filter_values(["system-manager"])) == {"system-manager", "system_mgmt"}
    assert set(expand_app_filter_values(["system_mgmt"])) == {"system-manager", "system_mgmt"}
    assert expand_app_filter_values(["monitor"]) == ["monitor"]


def test_request_path_without_query():
    assert request_path_without_query("/api/v1/monitor/alert_rule/?token=abc") == "/api/v1/monitor/alert_rule/"
    assert request_path_without_query("/api/v1/monitor/alert_rule/") == "/api/v1/monitor/alert_rule/"
