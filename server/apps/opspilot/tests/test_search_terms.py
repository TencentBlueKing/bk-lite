"""问句词表：原词加固定同义词，不把两个概念粘成一个短语。"""

import json

from langchain_core.messages import ToolMessage

from apps.core.utils.loader import LanguageLoader
from apps.opspilot.metis.llm.middleware.tool_runtime import repeated_or_search_denial, terminal_success_denial
from apps.opspilot.metis.llm.tools.search_terms import (
    accepted_model_keyword,
    build_search_terms,
    resolve_search_terms,
    user_message_from_config,
    user_question_for_search,
)
from apps.opspilot.services.workflow_attachment_service import MINIO_CONNECTION_FAILURE_MESSAGE


def test_mall_question_keeps_phenomena_and_accepts_verbatim_nouns():
    text = "商城页面最近特别慢，告警中心和日志两边对一下前端报错还是网关在拒绝"
    terms = build_search_terms(text)
    assert "商城" not in terms
    assert "前端" not in terms
    assert "网关" in terms
    assert "报错" in terms
    assert "connection refused" in terms
    assert "502" in terms
    assert "upstream" in terms
    accepted = resolve_search_terms(text, "商城 前端")
    assert "商城" in accepted
    assert "前端" in accepted
    assert "商城 502" not in accepted


def test_order_timeout_keeps_timeout_synonyms_and_verbatim_interface_name():
    text = "下单接口超时了，告警和对应日志两边有没有 timeout"
    terms = build_search_terms(text)
    assert "下单接口" not in terms
    assert "超时" in terms
    assert "timeout" in terms
    assert "timed out" in terms
    accepted = resolve_search_terms(text, "下单接口")
    assert "下单接口" in accepted
    assert "timeout" in accepted


def test_resolve_ignores_glued_model_keyword_when_user_text_exists():
    terms = resolve_search_terms("下单接口超时了，有没有 timeout", "下单超时")
    assert "下单接口" not in terms
    assert "下单超时" not in terms
    assert "timeout" in terms


def test_resolve_splits_model_keyword_when_user_text_missing():
    assert resolve_search_terms("", "商城 502") == ["商城", "502"]


def test_inventory_question_does_not_become_search_terms():
    assert build_search_terms("当前告警有哪些") == []
    assert build_search_terms("有哪些磁盘告警") == []
    terms = resolve_search_terms("有哪些磁盘告警", "磁盘")
    assert terms == ["磁盘"]


def test_active_alert_count_question_sends_no_content_keywords():
    assert build_search_terms("我现在有多少条活动告警") == []
    assert resolve_search_terms("我现在有多少条活动告警", "活动") == []
    assert resolve_search_terms("当前有多少条活动告警", "活动告警") == []
    assert build_search_terms("有多少条磁盘告警") == []
    assert resolve_search_terms("有多少条磁盘告警", "磁盘") == ["磁盘"]


def test_status_and_time_are_not_content_keywords():
    assert build_search_terms("查询活动告警") == []
    assert build_search_terms("查询下我有多少条活跃告警") == []
    assert "下单接口" not in build_search_terms("查询下单接口超时了")
    assert "超时" in build_search_terms("查询下单接口超时了")
    assert resolve_search_terms("查询下单接口超时了", "下单接口") == ["超时", "timeout", "timed out", "下单接口"]
    assert resolve_search_terms("查询活动告警", "磁盘") == []
    assert build_search_terms("查询下磁盘告警") == []
    assert resolve_search_terms("查询下磁盘告警", "磁盘") == ["磁盘"]
    assert resolve_search_terms("查询活动告警", "活动") == []
    assert resolve_search_terms("我查询活动告警", "查询活动") == []
    assert resolve_search_terms("查一下活动告警", "活动") == []
    assert build_search_terms("查询最近一小时的活动告警") == []
    log_terms = build_search_terms("查询最近24小时的error日志")
    assert log_terms == ["error"]
    assert build_search_terms("查询最近一小时的磁盘告警") == []
    assert resolve_search_terms("查询最近一小时的磁盘告警", "磁盘") == ["磁盘"]


def test_compound_content_is_kept_when_the_model_passes_it_verbatim():
    assert build_search_terms("主机在线") == []
    assert resolve_search_terms("主机在线", "在线") == ["在线"]
    assert resolve_search_terms("数据库有慢查询", "慢查询") == ["慢查询"]
    assert resolve_search_terms("活动目录同步失败", "活动目录") == ["活动目录"]
    assert resolve_search_terms("我们的服务挂了", "我们") == ["我们"]
    assert resolve_search_terms("服务存在异常", "存在") == ["存在"]
    assert resolve_search_terms("任务正在运行", "正在") == ["正在"]
    reported = resolve_search_terms("接口报错了", "报错了")
    assert "报错" in reported
    assert "报错了" in reported
    assert accepted_model_keyword("在线", "主机在线") == "在线"
    assert accepted_model_keyword("活动目录", "同步活动目录") == "活动目录"


def test_filler_only_phrases_and_scraps_are_not_content_keywords():
    assert resolve_search_terms("我查询活动告警", "查询活动") == []
    assert resolve_search_terms("当前有多少条活动告警", "活动告警") == []
    assert resolve_search_terms("查询下我有多少条活跃告警", "下我") == []
    assert resolve_search_terms("我要查询我现在有多少条活动告警", "条活动") == []
    assert resolve_search_terms("查询下磁盘告警", "查询下") == []
    assert resolve_search_terms("查询下我有多少条活跃告警", "活跃告") == []
    assert resolve_search_terms("我现在有多少条活动告警", "现在有") == []
    assert resolve_search_terms("我现在有多少条活动告警", "有多少条活") == []
    assert resolve_search_terms("查询本周报告警", "本周报") == []
    assert resolve_search_terms("查询下单接口超时了", "下单接口") == ["超时", "timeout", "timed out", "下单接口"]


def test_english_status_time_and_query_words_are_not_content_keywords():
    assert build_search_terms("how many active alerts do I have") == []
    assert build_search_terms("search logs for the last 24 hours") == []
    assert build_search_terms("Last 24 Hours") == []
    assert build_search_terms("how many open alerts") == []
    assert resolve_search_terms("how many active alerts do I have", "active") == []
    assert resolve_search_terms("search logs for the last 24 hours", "hours 24") == []
    assert build_search_terms("search logs for the last 24 hours for error") == ["error"]
    assert build_search_terms("search logs for the last 24hrs") == []
    mixed = resolve_search_terms("查询 web-01 最近 24 hours 的慢查询", "慢查询 hours")
    assert "web-01" in mixed
    assert "慢查询" in mixed
    assert "hours" not in mixed
    assert "24" not in mixed
    host = build_search_terms("timeout on web-01 and 10.10.41.149")
    assert "timeout" in host
    assert "timed out" in host
    assert "web-01" in host
    assert "10.10.41.149" in host
    assert "on" not in host
    assert "and" not in host
    assert build_search_terms("openssl error on web-01") == ["error", "web-01"]
    assert build_search_terms("error 24") == ["error", "24"]
    assert build_search_terms("查询一个月来的告警信息，整理成一个word文档给我") == []
    assert resolve_search_terms("查询一个月来的告警信息，整理成一个word文档给我", "word") == []
    assert build_search_terms("how many new alerts") == []
    assert build_search_terms("how many recovered alerts") == []
    assert build_search_terms("show auto_close alerts") == []
    assert build_search_terms("list auto_recovery alerts") == []
    assert build_search_terms("auto-recovery alerts") == []
    assert build_search_terms("auto-close alerts") == []
    assert build_search_terms("查询自动关闭的告警") == []
    assert resolve_search_terms("show auto_close alerts", "auto_close") == []
    assert "cpu_usage_5m" in build_search_terms("show cpu_usage_5m alerts")
    assert "web-01" in build_search_terms("auto_close on web-01")
    assert "disk_used_percent" in build_search_terms("show disk_used_percent")
    assert resolve_search_terms("how many new alerts", "new") == []
    assert resolve_search_terms("how many recovered alerts", "recovered") == []
    assert accepted_model_keyword("CPU", "") == "CPU"
    assert accepted_model_keyword("memory", "") == "memory"
    assert accepted_model_keyword("web", "") == "web"
    shown = build_search_terms("show me the error logs from web-01 for the last 24 hours")
    assert "error" in shown
    assert "web-01" in shown
    assert "show" not in shown
    assert "hours" not in shown
    assert "24" not in shown
    assert build_search_terms("how many active alerts.") == []
    assert build_search_terms("how many active alerts?") == []
    assert build_search_terms("Last 24 Hours.") == []
    assert build_search_terms("last 24 h") == []
    assert build_search_terms("最近 5m.") == []
    assert build_search_terms("最近 24h.") == []
    assert build_search_terms("error.") == ["error"]
    assert build_search_terms("看一下 cpu_usage_5m.") == ["cpu_usage_5m"]
    assert build_search_terms("host 10.10.41.149.") == ["10.10.41.149"]


def test_metric_name_with_time_suffix_stays_a_content_keyword():
    assert accepted_model_keyword("cpu_usage_5m", "看一下 cpu_usage_5m") == "cpu_usage_5m"
    assert accepted_model_keyword("cpu_usage_5min", "看 cpu_usage_5min") == "cpu_usage_5min"
    assert accepted_model_keyword("5m", "最近 5m") == ""
    assert accepted_model_keyword("24h", "最近 24h") == ""
    assert "5m" not in build_search_terms("最近 5m 的 cpu_usage_5m")
    assert "cpu_usage_5m" in build_search_terms("最近 5m 的 cpu_usage_5m")
    assert "24h" not in build_search_terms("last 24h cpu_usage_5m")
    assert "cpu_usage_5m" in build_search_terms("last 24h cpu_usage_5m")
    assert "24" not in build_search_terms("last 24h cpu_usage_5m")
    assert "24" not in build_search_terms("last 24 h cpu_usage_5m")
    assert "cpu_usage_5m" in build_search_terms("last 24 h cpu_usage_5m")
    assert accepted_model_keyword("cpu_usage_5m.", "看一下 cpu_usage_5m.") == "cpu_usage_5m"
    assert accepted_model_keyword("5m.", "最近 5m.") == ""


def test_english_tool_descriptions_name_status_time_and_query_phrasing():
    en_loader = LanguageLoader(app="opspilot", default_lang="en")
    zh_loader = LanguageLoader(app="opspilot", default_lang="zh-Hans")
    keys = (
        "tools.alerts.tools.alerts_list_alerts.description",
        "tools.log.tools.log_search_structured.description",
    )
    for key in keys:
        english = en_loader.get(key)
        assert "verbatim" in english
        assert "query phrasing" in english
        assert "current" in english
        assert "which" in english
        assert "Chinese content keywords" not in english
        chinese = zh_loader.get(key)
        assert "原样" in chinese
        assert "状态" in chinese
        assert "时间" in chinese


def test_error_log_question_keeps_ascii_keyword():
    terms = build_search_terms("查询最近24小时的error日志")
    assert "error" in terms
    assert "快照" not in terms
    assert "检索" not in terms


def test_page_context_injection_does_not_pollute_search_terms():
    """页面快照导语/DOM 文案不得盖住用户原问里的 error。"""
    injected = (
        "以下是用户当前正在查看的页面快照，仅当问题与页面相关时参考。"
        "时间范围、横轴起止与 KPI 一律以 <current_page> 本轮快照为准，"
        "若缺少查询对象、对象类型、时间范围或要看的指标/告警类型，必须调用 request_user_choice。\n\n"
        "查询最近24小时的error日志\n\n"
        "<current_page>\n"
        "url: /log/search\n"
        "app: log\n"
        "title: 日志搜索\n"
        "## 字段\n"
        "检索\n"
        "快照\n"
        "以下是同当前当前\n"
        "</current_page>"
    )
    assert user_question_for_search(injected) == "查询最近24小时的error日志"
    terms = resolve_search_terms(injected, "error")
    assert "error" in terms
    assert "快照" not in terms
    assert "检索" not in terms
    assert "以下是同当前当前" not in terms


def test_focused_page_context_extracts_quoted_question():
    injected = "本轮用户问题是「查询最近24小时的error日志」，已定位到图表《查询直方图》。" "只根据本轮 <current_page> 中的截图与文字回答这一问。\n\n" "<current_page>\n## KPI 快照\n检索\n</current_page>"
    assert user_question_for_search(injected) == "查询最近24小时的error日志"
    assert "error" in resolve_search_terms(injected, "error")


def test_user_message_from_config_strips_page_context():
    injected = "以下是用户当前正在查看的页面快照，仅当问题与页面相关时参考。\n\n" "查询最近24小时的error日志\n\n" "<current_page>\n快照\n检索\n</current_page>"
    config = {"configurable": {"user_message": injected}}
    assert user_message_from_config(config) == "查询最近24小时的error日志"


def test_failed_log_search_does_not_block_a_corrected_retry():
    request = type(
        "Req",
        (),
        {
            "tool_call": {
                "id": "call-2",
                "name": "log_search_structured",
                "args": {"start": "2026-10-21T14:53:09+08:00", "end": "2026-10-21T15:03:09+08:00"},
            },
            "messages": [
                ToolMessage(
                    content='{"success": false, "error": "time range values must be RFC3339 timestamps with explicit timezones"}',
                    tool_call_id="call-1",
                    name="log_search_structured",
                ),
            ],
        },
    )()
    assert repeated_or_search_denial(request) is None


def test_failed_alerts_list_does_not_block_a_corrected_retry():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "alerts_list_alerts", "args": {"status": "active", "page": 1}},
            "messages": [
                ToolMessage(
                    content='{"result": false, "data": {}, "message": "查询告警列表失败"}',
                    tool_call_id="call-1",
                    name="alerts_list_alerts",
                ),
            ],
        },
    )()
    assert repeated_or_search_denial(request) is None


def test_second_log_search_is_denied_after_success():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "log_search_structured", "args": {"keyword": "connection refused"}},
            "messages": [
                ToolMessage(content='{"success": true, "data": []}', tool_call_id="call-1", name="log_search_structured"),
            ],
        },
    )()
    denied = repeated_or_search_denial(request)
    assert denied is not None
    assert "空结果" in denied.content
    assert "不是参数错误" in denied.content


def test_non_empty_success_can_query_again_with_different_args():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "monitor_query_metric_data", "args": {"instance_ids": ["1_10.10.60.12"]}},
            "messages": [
                ToolMessage(
                    content='{"success": true, "data": {"series": [{"instance_id": "1_10.10.60.11"}]}}',
                    tool_call_id="call-1",
                    name="monitor_query_metric_data",
                ),
            ],
        },
    )()
    assert repeated_or_search_denial(request) is None


def test_empty_result_blocks_any_tool_retry():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "monitor_query_metric_data", "args": {"instance_ids": ["1_10.10.60.12"]}},
            "messages": [
                ToolMessage(
                    content='{"success": true, "data": {"series": [], "count": 0}}',
                    tool_call_id="call-1",
                    name="monitor_query_metric_data",
                ),
            ],
        },
    )()
    denied = repeated_or_search_denial(request)
    assert denied is not None
    assert "空结果" in denied.content
    assert "不是参数错误" in denied.content


def test_metric_catalog_keyword_miss_allows_a_different_keyword():
    """目录没命中可以换 keyword。不要逐个试指标，由工具让用户选。"""
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "monitor_list_object_metrics", "args": {"keyword": "memory"}},
            "messages": [
                ToolMessage(
                    content='{"success": true, "data": [], "message": "无名称/展示名包含「内存」的指标。"}',
                    tool_call_id="call-1",
                    name="monitor_list_object_metrics",
                ),
            ],
        },
    )()
    assert repeated_or_search_denial(request) is None


def test_monitor_query_metric_data_empty_matrix_blocks_retry_with_different_args():
    """Prometheus 空矩阵经 wrap_success 后，改 instance_ids / 时间窗仍要拦住。"""
    payload = {
        "success": True,
        "data": {
            "status": "success",
            "data": {"resultType": "matrix", "result": []},
            "stats": {"seriesMatched": "0"},
        },
    }
    request = type(
        "Req",
        (),
        {
            "tool_call": {
                "id": "call-2",
                "name": "monitor_query_metric_data",
                "args": {"instance_ids": ["other-host"], "start": "2026-10-22 10:00:00", "end": "2026-10-22 11:00:00"},
            },
            "messages": [
                ToolMessage(
                    content=json.dumps(payload, ensure_ascii=False),
                    tool_call_id="call-1",
                    name="monitor_query_metric_data",
                ),
            ],
        },
    )()
    denied = repeated_or_search_denial(request)
    assert denied is not None
    assert "空结果" in denied.content
    assert "不是参数错误" in denied.content

    result_only = {
        "success": True,
        "data": {"status": "success", "data": {"resultType": "matrix", "result": []}},
    }
    series_only = {
        "success": True,
        "data": {"status": "success", "stats": {"seriesMatched": "0"}},
    }
    for body in (result_only, series_only):
        again = type(
            "Req",
            (),
            {
                "tool_call": {
                    "id": "call-2",
                    "name": "monitor_query_metric_data",
                    "args": {"dimensions": {"mount": "/"}},
                },
                "messages": [
                    ToolMessage(content=json.dumps(body), tool_call_id="call-1", name="monitor_query_metric_data"),
                ],
            },
        )()
        denied_again = repeated_or_search_denial(again)
        assert denied_again is not None
        assert "空结果" in denied_again.content
        assert "不是参数错误" in denied_again.content


def test_non_empty_matrix_result_does_not_block_another_query():
    payload = {
        "success": True,
        "data": {
            "status": "success",
            "data": {"resultType": "matrix", "result": [{"metric": {"instance": "web-1"}, "values": [[1, "1"]]}]},
            "stats": {"seriesMatched": "1"},
        },
    }
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "monitor_query_metric_data", "args": {"instance_ids": ["web-2"]}},
            "messages": [
                ToolMessage(
                    content=json.dumps(payload),
                    tool_call_id="call-1",
                    name="monitor_query_metric_data",
                ),
            ],
        },
    )()
    assert repeated_or_search_denial(request) is None

    contradictory = {
        "success": True,
        "data": {
            "status": "success",
            "data": {"resultType": "matrix", "result": [{"metric": {"instance": "web-1"}, "values": [[1, "1"]]}]},
            "stats": {"seriesMatched": "0"},
        },
    }
    kept = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "monitor_query_metric_data", "args": {"instance_ids": ["web-2"]}},
            "messages": [
                ToolMessage(content=json.dumps(contradictory), tool_call_id="call-1", name="monitor_query_metric_data"),
            ],
        },
    )()
    assert repeated_or_search_denial(kept) is None


def test_result_object_without_empty_list_is_not_an_empty_success():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "monitor_query_metric_data", "args": {"metric": "cpu"}},
            "messages": [
                ToolMessage(
                    content='{"success": true, "data": {"result": {"status": "ok"}}}',
                    tool_call_id="call-1",
                    name="monitor_query_metric_data",
                ),
            ],
        },
    )()
    assert repeated_or_search_denial(request) is None


def test_parameter_error_can_retry_any_tool():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "monitor_summarize_metric_trend", "args": {"metric": "disk_used_percent"}},
            "messages": [
                ToolMessage(
                    content='{"success": false, "error": "monitor_obj_id is required"}',
                    tool_call_id="call-1",
                    name="monitor_summarize_metric_trend",
                ),
            ],
        },
    )()
    assert repeated_or_search_denial(request) is None


def test_unreachable_service_blocks_retry_for_any_tool():
    request = type(
        "Req",
        (),
        {
            "tool_call": {
                "id": "call-2",
                "name": "log_search_raw",
                "args": {"start": "2026-10-21T15:03:18+08:00", "end": "2026-10-21T15:13:18+08:00"},
            },
            "messages": [
                ToolMessage(
                    content=(
                        '{"success": false, "error": "HTTPConnectionPool(host=\'127.0.0.1\', port=9428): '
                        'Max retries exceeded. WinError 10061 由于目标计算机积极拒绝，无法连接。"}'
                    ),
                    tool_call_id="call-1",
                    name="log_search_raw",
                ),
            ],
        },
    )()
    denied = repeated_or_search_denial(request)
    assert denied is not None
    assert "服务不可达" in denied.content


def test_minio_connection_message_blocks_another_attachment_call():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "generate_attachment_file", "args": {"file_type": "docx"}},
            "messages": [
                ToolMessage(
                    content=MINIO_CONNECTION_FAILURE_MESSAGE,
                    tool_call_id="call-1",
                    name="generate_attachment_file",
                    status="error",
                ),
            ],
        },
    )()
    denied = repeated_or_search_denial(request)
    assert denied is not None
    assert "服务不可达" in denied.content
    assert "不要改参数重试" in denied.content


def test_connection_refused_inside_successful_logs_is_not_a_service_failure():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "log_search_structured", "args": {"keyword": "timeout"}},
            "messages": [
                ToolMessage(
                    content='{"success": true, "data": [{"message": "upstream connection refused"}]}',
                    tool_call_id="call-1",
                    name="log_search_structured",
                ),
            ],
        },
    )()
    assert repeated_or_search_denial(request) is None


def test_terminal_hint_stops_another_call_even_when_args_change():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "prepare_dashboard_proposal", "args": {"proposal": {"schemaVersion": "1.0"}}},
            "messages": [
                ToolMessage(
                    content='{"success": true, "_next_step_hint": "方案已校验通过。不要再次调用 prepare_dashboard_proposal。"}',
                    tool_call_id="call-1",
                    name="prepare_dashboard_proposal",
                ),
            ],
        },
    )()
    denied = terminal_success_denial(request)
    assert denied is not None
    assert "不要再调用" in denied.content

    retry = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "prepare_dashboard_proposal", "args": {"proposal": {"schemaVersion": "1.0"}}},
            "messages": [
                ToolMessage(
                    content='{"success": true, "_next_step_hint": "按这个结构改完再调用一次，不要原样重试。"}',
                    tool_call_id="call-1",
                    name="prepare_dashboard_proposal",
                ),
            ],
        },
    )()
    assert terminal_success_denial(retry) is None
