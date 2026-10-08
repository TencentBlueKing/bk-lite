import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader
from apps.opspilot.services.chat_service import ChatService


@pytest.fixture(autouse=True)
def use_dashboard_locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-ops-analysis-dashboard",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def test_dashboard_plan_applies_directly_and_keeps_confirmation_compatible():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import (
        ToolExecutionPlan,
        ToolExecutionStep,
        dashboard_confirmation_intent,
        missing_planned_dashboard_tools,
        rewrite_dashboard_builder_plan,
    )

    names = {"search_data_sources", "prepare_dashboard_proposal", "apply_dashboard_proposal"}
    original = ToolExecutionPlan(
        goal="再检索",
        steps=[ToolExecutionStep(objective="检索", tools=["search_data_sources"])],
    )
    page = "符合了\n\n以下是用户当前正在查看的页面快照，仅当问题与页面相关时参考。"
    assert dashboard_confirmation_intent(page) == "apply"
    assert dashboard_confirmation_intent("是") == "apply"
    assert dashboard_confirmation_intent("新建") is None
    assert dashboard_confirmation_intent("不要了") == "cancel"
    assert dashboard_confirmation_intent("先不要应用") == "cancel"
    assert dashboard_confirmation_intent("暂不应用") == "cancel"
    assert dashboard_confirmation_intent("不确认") == "cancel"
    assert dashboard_confirmation_intent("帮我搭一个能看到主机资产情况的仪表盘") is None
    created = rewrite_dashboard_builder_plan(
        original,
        names,
        user_message="创建一个告警数据预览的仪表盘 能展示告警数、告警趋势",
    )
    assert [step.tools for step in created.steps] == [
        ["search_data_sources"],
        ["prepare_dashboard_proposal"],
        ["apply_dashboard_proposal"],
    ]
    asked = rewrite_dashboard_builder_plan(original, names, user_message=page)
    assert asked.steps[0].tools == ["apply_dashboard_proposal"]
    buried = rewrite_dashboard_builder_plan(
        original,
        names,
        user_message=("帮我创建一个cmdb的仪表盘，展示资产数量\n" "确认\n\n" "## 仪表盘编辑状态\n" "dashboardId: dashboard_426\n" "widgets:\n- none\n"),
    )
    assert [step.tools for step in buried.steps] == [["apply_dashboard_proposal"]]
    built = rewrite_dashboard_builder_plan(original, names, user_message="帮我搭一个能看到主机资产情况的仪表盘")
    assert [step.tools for step in built.steps] == [
        ["search_data_sources"],
        ["prepare_dashboard_proposal"],
        ["apply_dashboard_proposal"],
    ]
    added = rewrite_dashboard_builder_plan(
        ToolExecutionPlan(goal="回答", steps=[]),
        names,
        user_message="我希望新增一个可以按时间范围查看告警数的仪表盘，帮我创建一个，默认时间为30天",
    )
    assert [step.tools for step in added.steps] == [
        ["search_data_sources"],
        ["prepare_dashboard_proposal"],
        ["apply_dashboard_proposal"],
    ]
    extended = rewrite_dashboard_builder_plan(
        ToolExecutionPlan(goal="回答", steps=[]),
        names,
        user_message="再增加几个告警等级分布等的图表",
    )
    assert [step.tools for step in extended.steps] == [
        ["search_data_sources"],
        ["prepare_dashboard_proposal"],
        ["apply_dashboard_proposal"],
    ]
    implicit_widget = rewrite_dashboard_builder_plan(
        ToolExecutionPlan(goal="新增一个cmdb的模型实例分类统计", steps=[]),
        names,
        user_message="新增一个cmdb的模型实例分类统计",
    )
    assert [step.tools for step in implicit_widget.steps] == [
        ["search_data_sources"],
        ["prepare_dashboard_proposal"],
        ["apply_dashboard_proposal"],
    ]
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import remember_ready_proposal

    remember_ready_proposal(1, "dashboard_424", {"schemaVersion": "1.0", "layout": [], "filters": []})
    ready = rewrite_dashboard_builder_plan(
        original,
        names,
        user_message="可以\n\n以下是用户当前正在查看的页面快照 dashboard_424",
    )
    assert ready.steps[0].tools == ["apply_dashboard_proposal"]
    cancelled = rewrite_dashboard_builder_plan(original, names, user_message="不要了")
    assert cancelled.steps == []
    assert missing_planned_dashboard_tools(["search_data_sources"], []) == ["search_data_sources"]
    removed = rewrite_dashboard_builder_plan(
        original,
        names,
        user_message="去掉主机资源快照 主机数这个单值组件\n\n以下是用户当前正在查看的页面快照",
    )
    assert [step.tools for step in removed.steps] == [["prepare_dashboard_proposal"], ["apply_dashboard_proposal"]]
    layout_change = rewrite_dashboard_builder_plan(
        original,
        names,
        user_message="你想把布局改成每行的宽度为4吗",
    )
    assert [step.tools for step in layout_change.steps] == [["prepare_dashboard_proposal"], ["apply_dashboard_proposal"]]
    natural_layout_change = rewrite_dashboard_builder_plan(original, names, user_message="调整成一行两个组件")
    assert [step.tools for step in natural_layout_change.steps] == [["prepare_dashboard_proposal"], ["apply_dashboard_proposal"]]
    deferred = rewrite_dashboard_builder_plan(original, names, user_message="把单位改成个")
    assert deferred.steps == []
    question = rewrite_dashboard_builder_plan(original, names, user_message="这个表格为什么是空的")
    assert question.steps == []
    explained = rewrite_dashboard_builder_plan(
        ToolExecutionPlan(goal="解释", steps=[ToolExecutionStep(objective="查告警", tools=["alerts_list"])]),
        names | {"alerts_list"},
        user_message="这个表格为什么是空的",
    )
    assert [step.tools for step in explained.steps] == [["alerts_list"]]
    asked = rewrite_dashboard_builder_plan(original, names, user_message="看看当前这张盘上有什么，告警趋势如何")
    assert asked.steps == []
    unique = (
        "去掉数据治理健康度趋势，这不是告警的数据\n"
        "## 仪表盘编辑状态\nwidgets:\n"
        "- id=trend name=告警趋势 chart=line dataSource=193 fields=selected:value params= bindings= pos=0,0,4,3\n"
        "- id=health name=数据治理健康度趋势 chart=line dataSource=233 fields=selected:score params= bindings= pos=8,0,4,3\n"
    )
    direct = rewrite_dashboard_builder_plan(original, names, user_message=unique)
    assert [step.tools for step in direct.steps] == [["prepare_dashboard_proposal"], ["apply_dashboard_proposal"]]

    indirect = rewrite_dashboard_builder_plan(
        ToolExecutionPlan(
            goal="把这里整理成值班时一眼能看懂的告警视图",
            steps=[ToolExecutionStep(objective="检索可用告警数据", tools=["search_data_sources"])],
        ),
        names,
        user_message="把这里整理成值班时一眼能看懂的告警视图",
    )
    assert [step.tools for step in indirect.steps] == [
        ["search_data_sources"],
        ["prepare_dashboard_proposal"],
        ["apply_dashboard_proposal"],
    ]
    from langchain_core.messages import HumanMessage

    from apps.opspilot.metis.llm.agent.tool_execution_planner import dashboard_build_query

    assert (
        dashboard_build_query(
            "可以\n\n以下是用户当前正在查看的页面快照",
            [HumanMessage(content="帮我搞一个告警数据预览的仪表盘")],
        )
        == "帮我搞一个告警数据预览的仪表盘"
    )

    from langchain_core.messages import AIMessage

    from apps.opspilot.metis.llm.agent.tool_execution_planner import dashboard_planning_message

    followup = "告警等级分布、告警类型分布、告警来源分布"
    contextual = dashboard_planning_message(
        followup,
        [
            HumanMessage(content="再增加几个告警等级分布等的图表"),
            AIMessage(content="请说明想增加哪些图表"),
            HumanMessage(content=followup),
        ],
    )
    assert contextual == "再增加图表，展示告警等级分布、告警类型分布、告警来源分布"

    from apps.opspilot.metis.llm.agent.tool_execution_planner import dashboard_planning_message_for_tools

    untouched = dashboard_planning_message_for_tools(
        followup, [HumanMessage(content="再增加几个告警等级分布等的图表"), HumanMessage(content=followup)], ["lookup_pod"]
    )
    assert untouched == followup
    rewritten = dashboard_planning_message_for_tools(
        followup,
        [HumanMessage(content="再增加几个告警等级分布等的图表"), HumanMessage(content=followup)],
        ["apply_dashboard_proposal"],
    )
    assert rewritten.startswith("再增加图表，展示")


def test_dashboard_channel_session_id_only_on_the_dashboard_page():
    from apps.opspilot.services.skill_channel_chat_service import dashboard_channel_session_id

    page = {"app": "ops-analysis", "capabilities": ["dashboard-builder"]}
    assert dashboard_channel_session_id(page, "session-1") == "session-1"
    assert dashboard_channel_session_id({"app": "ops-analysis", "capabilities": ["dashboard-export"]}, "session-1") is None
    assert dashboard_channel_session_id({"app": "cmdb", "capabilities": ["dashboard-builder"]}, "session-1") is None
    assert dashboard_channel_session_id(None, "session-1") is None


def test_dashboard_final_reply_stays_inside_dashboard_plans():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionStep, dashboard_final_reply

    answer = "没有找到能够可靠回答这个问题"
    completed = [SimpleNamespace(result=answer)]
    assert dashboard_final_reply(completed, [ToolExecutionStep(objective="查告警", tools=["alerts_list_alerts"])]) == ""
    assert dashboard_final_reply(completed, [ToolExecutionStep(objective="检索", tools=["search_data_sources"])]) == answer


def test_dashboard_plan_rewrite_logs_branch_at_debug(caplog):
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, rewrite_dashboard_builder_plan

    utterance = "帮我搭一个主机资产仪表盘"
    with caplog.at_level(logging.DEBUG, logger="opspilot"):
        rewrite_dashboard_builder_plan(
            ToolExecutionPlan(goal="", steps=[]),
            {"search_data_sources", "prepare_dashboard_proposal", "apply_dashboard_proposal"},
            user_message=utterance,
        )
    matches = [record for record in caplog.records if getattr(record, "msg", "") == "event=dashboard_plan_rewritten branch=%s"]
    assert matches
    assert all(record.levelno == logging.DEBUG for record in matches)
    assert matches[-1].args == ("rule_build",)
    formatted = matches[-1].getMessage()
    assert formatted == "event=dashboard_plan_rewritten branch=rule_build"
    assert utterance not in formatted
    assert not any(record.levelno == logging.INFO and "dashboard_plan_rewritten" in record.getMessage() for record in caplog.records)


def test_dynamic_param_choices_failure_log_keeps_stage_and_omits_exception_text(caplog):
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import dynamic_param_choices

    secret = "token-should-not-leak"
    declared = {
        "inputConfig": {
            "optionsSource": {
                "type": "dynamic",
                "sourceRef": {"type": "rest_api", "value": "monitor/list"},
            }
        }
    }
    with caplog.at_level(logging.WARNING, logger="opspilot"):
        with patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard.AppClient") as client:
            client.return_value.run.side_effect = RuntimeError(secret)
            assert dynamic_param_choices(declared, {"team_id": 7}) == []
    records = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert records
    message = records[-1].getMessage()
    assert message == "event=dashboard_param_choices_read_failed failed_stage=read_param_choices error_type=RuntimeError team_id=7"
    assert records[-1].args == ("RuntimeError", 7)
    assert secret not in message
    assert records[-1].exc_info is None


def test_extend_prepares_new_widgets_on_top_of_the_current_canvas():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal, remember_search_candidates

    _clear_ready()
    remember_search_candidates(
        [
            {
                "id": 222,
                "name": "活跃告警等级分布",
                "tags": ["告警"],
                "chart_type": ["pie"],
                "fields": [{"name": "name", "desc": "等级"}, {"name": "value", "desc": "数量", "type": "number"}],
                "params": [],
            }
        ],
        requirements=[{"text": "告警等级分布", "purpose": "visualization", "chartType": "pie"}],
        team_id=7,
        session_id="session-extend",
    )

    class Rpc:
        def run(self, method_name, **kwargs):
            assert method_name == "prepare_dashboard_proposal"
            return {"ok": True, "proposal": kwargs["proposal"], "pending": []}

    message = (
        "再增加几个告警等级分布等的图表\n" "## 仪表盘编辑状态\nwidgets:\n" "- id=trend name=告警与关联事件趋势 chart=line dataSource=193 fields= params= bindings= pos=0,0,4,3\n"
    )
    config = {
        "configurable": {
            "caller_identity": {"team_id": 7},
            "dashboard_session_id": "session-extend",
            "dashboard_user_message": message,
        }
    }
    with (
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._briefs", return_value=[]),
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._rpc", return_value=Rpc()),
    ):
        result = prepare_dashboard_proposal.func({}, config)

    assert result["data"]["ok"] is True
    layout = result["data"]["proposal"]["layout"]
    assert [item["valueConfig"]["dataSource"] for item in layout] == [193, 222]
    assert layout[1]["y"] >= 3


def test_apply_uses_the_remembered_proposal_not_the_model_payload():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import proposal_for_apply, remember_ready_proposal, reply_from_apply_content

    remembered = {"schemaVersion": "1.0", "layout": [{"i": "ai-267", "name": "主机数"}], "filters": []}
    remember_ready_proposal(7, "current", remembered)
    chosen = proposal_for_apply({"schemaVersion": "1.0", "layout": []}, 7, "current")
    assert chosen["layout"][0]["i"] == "ai-267"
    assert reply_from_apply_content({"success": True, "data": {"applied": True}}) == "已应用到当前编辑中的仪表盘。"


def test_new_search_invalidates_the_previous_pending_proposal_in_the_same_dashboard():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import (
        proposal_for_apply,
        remember_ready_proposal,
        saved_search_candidates,
        search_data_sources,
    )

    remember_ready_proposal(
        7,
        "dashboard_426",
        {
            "schemaVersion": "1.0",
            "layout": [
                {
                    "i": "old-cmdb",
                    "valueConfig": {"chartType": "single", "dataSource": 218, "selectedFields": ["model_count"]},
                }
            ],
            "filters": [],
        },
        session_id="replace-proposal",
    )
    config = {
        "configurable": {
            "caller_identity": {"team_id": 7},
            "dashboard_session_id": "replace-proposal",
            "dashboard_user_message": (
                "我希望新增一个可以按时间范围查看告警数的仪表盘\n\n" '## 仪表盘编辑状态\n{"snapshotVersion":"1.0","dashboardId":"dashboard_426","layout":[],"filters":[]}\n'
            ),
        }
    }
    alert_brief = {
        "id": 223,
        "name": "告警与事件汇总",
        "tags": ["告警"],
        "chart_type": ["line"],
        "fields": [{"name": "time", "type": "time"}, {"name": "count", "type": "number"}],
        "params": [],
    }

    with patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._briefs", return_value=[alert_brief]):
        result = search_data_sources.func(
            [{"text": "过去30天告警数量趋势", "purpose": "visualization", "domain": "告警", "chartType": "line"}],
            config,
        )

    assert result["success"] is True
    assert [item["id"] for item in saved_search_candidates(team_id=7, session_id="replace-proposal", dashboard_id="dashboard_426")] == [223]
    assert saved_search_candidates(team_id=7, session_id="replace-proposal", dashboard_id="other-dashboard") == []
    assert proposal_for_apply({}, 7, "dashboard_426", session_id="replace-proposal") is None


def test_apply_rejects_a_negative_confirmation_before_dispatch():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import apply_dashboard_proposal, remember_ready_proposal

    proposal = {"schemaVersion": "1.0", "layout": [], "filters": []}
    remember_ready_proposal(7, "current", proposal, session_id="safe-session")
    config = {
        "configurable": {
            "caller_identity": {"team_id": 7},
            "dashboard_session_id": "safe-session",
            "dashboard_user_message": "先不要应用",
        }
    }
    with patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard.dispatch_custom_event") as dispatch:
        result = apply_dashboard_proposal.func(proposal, "current", config)

    dispatch.assert_not_called()
    assert result["success"] is False


def test_apply_accepts_the_original_build_request_without_a_confirmation_round():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import apply_dashboard_proposal, remember_ready_proposal

    proposal = {"schemaVersion": "1.0", "layout": [], "filters": []}
    remember_ready_proposal(7, "current", proposal, session_id="direct-session")

    class Rpc:
        def run(self, method_name, **kwargs):
            assert method_name == "prepare_dashboard_proposal"
            return {"ok": True, "proposal": kwargs["proposal"], "pending": []}

    config = {
        "configurable": {
            "caller_identity": {"team_id": 7},
            "dashboard_session_id": "direct-session",
            "dashboard_user_message": "帮我弄一个值班时能快速扫一眼的告警视图",
        }
    }
    with (
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard.dispatch_custom_event") as dispatch,
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._rpc", return_value=Rpc()),
    ):
        result = apply_dashboard_proposal.func(proposal, "current", config)

    dispatch.assert_called_once()
    assert result["data"]["applied"] is True


def test_fieldless_trend_source_still_becomes_a_line_widget():
    from apps.operation_analysis.services.dashboard_proposal_service import brief_from_source, draft_proposal_from_candidates
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import confirmation_reply

    brief = brief_from_source(
        {
            "id": 19,
            "name": "主机指标趋势",
            "chart_type": ["line", "bar"],
            "field_schema": [],
            "params": [
                {
                    "name": "metric_type",
                    "required": True,
                    "value": "cpu",
                    "inputConfig": {
                        "control": "select",
                        "optionsSource": {"type": "static", "staticItems": [{"label": "CPU使用率", "value": "cpu"}]},
                    },
                }
            ],
        }
    )
    draft = draft_proposal_from_candidates([brief])
    assert brief["chart_type"] == ["line", "bar"]
    assert draft["layout"][0]["valueConfig"]["chartType"] == "line"
    assert confirmation_reply(draft).startswith("已生成并校验仪表盘方案")
    assert "组件清单" in confirmation_reply(draft)
    assert "图表类型: line" in confirmation_reply(draft)


def test_search_step_result_keeps_real_ids():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import format_search_step_result

    text = format_search_step_result(
        {"success": True, "data": {"candidates": [{"id": 263, "name": "主机", "chart_type": ["table"], "fields": [{"name": "bk_host_name"}]}]}}
    )
    assert "id=263" in text
    assert "bk_host_name" in text
    assert "cmdb_data_source" not in text
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import candidates_from_tool_content

    found = candidates_from_tool_content('{"success": true, "data": {"candidates": [{"id": 197, "name": "主机资源使用率Top10"}]}}')
    assert found[0]["id"] == 197


def test_search_matches_chinese_phrase_against_source_name():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import search_briefs

    found = search_briefs(
        [{"text": "资产总数", "purpose": "visualization", "chartType": "single"}],
        [
            {"id": 2, "name": "资产统计", "chart_type": ["single"], "fields": [{"name": "value"}], "params": [], "tags": []},
            {
                "id": 3,
                "name": "组织列表",
                "chart_type": [],
                "fields": [{"name": "id"}, {"name": "name"}],
                "params": [],
                "tags": [],
                "option_ready": True,
            },
        ],
    )
    assert [item["id"] for item in found] == [2]
    by_title = search_briefs(
        [{"text": "主机名", "purpose": "visualization", "chartType": "table"}],
        [{"id": 8, "name": "CMDB实例", "chart_type": ["table"], "fields": [{"name": "bk_host_name", "desc": "主机名"}], "params": [], "tags": []}],
    )
    assert [item["id"] for item in by_title] == [8]


def test_search_tool_uses_the_user_goals_and_remembers_them_for_prepare():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import saved_search_requirements, search_data_sources

    config = {
        "configurable": {
            "caller_identity": {"team_id": 7},
            "dashboard_session_id": "session-reqs",
            "dashboard_user_message": "展示资产总数、类型分布和资产明细",
        }
    }
    briefs = [
        {"id": 1, "name": "资产总数", "chart_type": ["single"], "fields": [{"name": "count", "type": "number"}]},
        {"id": 2, "name": "资产类型分布", "chart_type": ["pie"], "fields": [{"name": "type"}, {"name": "count"}]},
        {"id": 3, "name": "资产明细", "chart_type": ["table"], "fields": [{"name": "name"}]},
    ]

    with patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._briefs", return_value=briefs):
        result = search_data_sources.func([{"text": "资产总览", "purpose": "visualization"}], config)

    assert [item["chartType"] for item in result["data"]["requirements"]] == ["single", "pie", "table"]
    assert saved_search_requirements(team_id=7, session_id="session-reqs") == result["data"]["requirements"]


def test_build_fails_closed_when_retrieved_sources_cannot_compile():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import (
        prepare_dashboard_proposal,
        remember_search_candidates,
        reply_from_prepare_content,
    )

    remember_search_candidates(
        [
            {
                "id": 192,
                "name": "日志命中数",
                "tags": ["日志"],
                "chart_type": ["line", "single"],
                "fields": [],
                "params": [],
            }
        ],
        requirements=[{"text": "日志情况概览", "purpose": "visualization"}],
        team_id=7,
        session_id="session-fail-closed",
    )
    config = {
        "configurable": {
            "caller_identity": {"team_id": 7},
            "dashboard_session_id": "session-fail-closed",
            "dashboard_user_message": "帮我搭建一个日志情况概览的仪表盘",
        }
    }
    polluted_model_proposal = {
        "schemaVersion": "1.0",
        "layout": [
            {
                "i": "wrong-cmdb",
                "name": "CMDB 模型数量",
                "valueConfig": {"chartType": "single", "dataSource": 218, "selectedFields": ["model_count"]},
            }
        ],
        "filters": [],
    }

    with patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._rpc") as rpc:
        result = prepare_dashboard_proposal.func(polluted_model_proposal, config)

    rpc.assert_not_called()
    assert result["success"] is True
    assert result["data"]["ok"] is False
    assert result["data"]["reason"] == "no_reliable_match"
    assert "没有找到" in result["data"]["reply"]
    assert reply_from_prepare_content(result) == result["data"]["reply"]


def test_distribution_search_requires_the_requested_dimension_not_only_the_domain_tag():
    from apps.operation_analysis.services.dashboard_proposal_service import search_briefs

    briefs = [
        {
            "id": 200,
            "name": "活跃告警状态分布",
            "desc": "未分派、待响应、处理中分布",
            "tags": ["告警"],
            "chart_type": ["pie"],
            "fields": [{"name": "name", "desc": "告警状态"}, {"name": "value", "desc": "告警数量"}],
        },
        {
            "id": 222,
            "name": "活跃告警等级分布",
            "desc": "当前活跃告警按等级分布",
            "tags": ["告警"],
            "chart_type": ["pie"],
            "fields": [{"name": "name", "desc": "等级名称"}, {"name": "value", "desc": "数量"}],
        },
    ]

    assert search_briefs([{"text": "告警类型分布", "chartType": "pie"}], briefs) == []
    assert [item["id"] for item in search_briefs([{"text": "告警等级分布", "chartType": "pie"}], briefs)] == [222]


def test_alarm_named_sources_outrank_overview_that_only_mentions_alerts():
    from apps.operation_analysis.services.dashboard_proposal_service import draft_proposal_from_candidates, search_briefs

    found = search_briefs(
        [{"text": "帮我搞一个告警数据预览的仪表盘", "purpose": "visualization"}],
        [
            {
                "id": 202,
                "name": "监控中心总览统计",
                "desc": "监控中心资源/能力/告警总览统计数据",
                "chart_type": ["single"],
                "fields": [{"name": "policy_total", "desc": "告警策略总数"}],
                "params": [],
                "tags": ["monitor"],
            },
            {
                "id": 200,
                "name": "活跃告警状态分布",
                "desc": "未分派、待响应、处理中分布",
                "chart_type": ["pie"],
                "fields": [{"name": "name", "desc": "状态名称"}, {"name": "value", "desc": "告警数量"}],
                "params": [],
                "tags": ["alerts"],
            },
            {
                "id": 214,
                "name": "今日产生关闭与当前处理中",
                "desc": "今日新产生与关闭的告警数",
                "chart_type": ["single"],
                "fields": [{"name": "today_created_count", "desc": "今日产生告警数"}],
                "params": [],
                "tags": ["alerts"],
            },
        ],
    )
    assert [item["id"] for item in found[:2]] == [200, 214]
    draft = draft_proposal_from_candidates(found)
    assert [item["valueConfig"]["dataSource"] for item in draft["layout"]] == [200, 214]
    assert draft["layout"][0]["valueConfig"]["chartType"] == "pie"


def test_prepare_result_becomes_the_apply_event():
    from apps.operation_analysis.services.dashboard_proposal_service import brief_from_source, prepare_dashboard_proposal
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import _proposal_payload

    brief = brief_from_source(
        {
            "id": 2,
            "name": "资产统计",
            "chart_type": ["single"],
            "field_schema": [{"name": "value"}],
            "params": [{"name": "organization_id", "filterType": "fixed", "value": "org-001", "required": True}],
        }
    )
    prepared = prepare_dashboard_proposal(
        {
            "schemaVersion": "1.0",
            "layout": [{"id": "card-1", "valueConfig": {"chartType": "single", "dataSource": 2, "selectedFields": ["value"]}}],
            "filters": [],
        },
        [brief],
    )
    payload = _proposal_payload({"success": True, "data": prepared}, "current")

    assert prepared["ok"] is True
    widget = payload["proposal"]["layout"][0]
    assert payload["dashboardId"] == "current"
    assert widget["i"] == "card-1"
    assert widget["valueConfig"]["dataSourceParams"][0]["value"] == "org-001"


def test_dashboard_builder_tools_are_registered():
    tools = ToolsLoader.load_tools("langchain:ops_analysis_dashboard")
    assert {tool.name for tool in tools} == {
        "search_data_sources",
        "prepare_dashboard_proposal",
        "apply_dashboard_proposal",
    }
    apply_tool = next(tool for tool in tools if tool.name == "apply_dashboard_proposal")
    assert list(apply_tool.args) == ["proposal", "dashboard_id"]


def _attach(message, page_context=None):
    chat_kwargs = {"system_message_prompt": "base", "execution_id": "exec-1"}
    with patch("apps.opspilot.services.chat_service.SkillTools.objects.filter", return_value=[]):
        ChatService._process_tools_and_extra_config(
            {"tools": [], "user_message": message, "page_context": page_context},
            chat_kwargs,
            {},
        )
    return chat_kwargs


def test_edit_state_message_attaches_dashboard_tools_and_direct_apply_rule():
    chat_kwargs = _attach(
        "请加一张图",
        {"app": "ops-analysis", "capabilities": ["dashboard-builder"]},
    )
    urls = [item.get("url") for item in chat_kwargs["tools_servers"]]
    assert "langchain:ops_analysis_dashboard" in urls
    assert "校验通过后立即调用 apply_dashboard_proposal" in chat_kwargs["system_message_prompt"]
    assert "去掉、删除已有组件时不要检索数据源" in chat_kwargs["system_message_prompt"]
    assert "用户明确取消或拒绝应用时" in chat_kwargs["system_message_prompt"]
    assert "保留的数据源组件必须原样带回" in chat_kwargs["system_message_prompt"]
    assert "fields 的 name 是字段 key" in chat_kwargs["system_message_prompt"]
    assert "data.ok 不是 true" in chat_kwargs["system_message_prompt"]
    assert "按 data.pending 告诉用户还缺哪个参数或字段" in chat_kwargs["system_message_prompt"]
    assert "传入 prepare 返回的 data.proposal" in chat_kwargs["system_message_prompt"]
    assert "无法安全搭盘" in chat_kwargs["system_message_prompt"]
    assert "告警趋势、告警分布、告警数量都可以直接上盘" in chat_kwargs["system_message_prompt"]
    assert "single" in chat_kwargs["system_message_prompt"]
    assert "networkStatusTopology" not in chat_kwargs["system_message_prompt"]


def test_view_page_snapshot_attaches_dashboard_tools():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, rewrite_dashboard_builder_plan

    chat_kwargs = _attach(
        "帮我搭一个主机资产仪表盘",
        {"app": "ops-analysis", "capabilities": ["dashboard-builder"]},
    )
    urls = [item.get("url") for item in chat_kwargs["tools_servers"]]
    assert "langchain:ops_analysis_dashboard" in urls
    empty = ToolExecutionPlan(goal="寒暄", steps=[])
    names = {"search_data_sources", "prepare_dashboard_proposal", "apply_dashboard_proposal"}
    planned = rewrite_dashboard_builder_plan(empty, names, user_message="帮我搭一个主机资产仪表盘")
    assert [step.tools for step in planned.steps] == [
        ["search_data_sources"],
        ["prepare_dashboard_proposal"],
        ["apply_dashboard_proposal"],
    ]


def test_message_markers_do_not_attach_dashboard_tools_without_page_capability():
    chat_kwargs = _attach(
        "帮我搭盘\n\n## 仪表盘编辑状态\nid=card-1\n正在查看运营分析仪表盘",
    )
    urls = [item.get("url") for item in chat_kwargs["tools_servers"]]
    assert "langchain:ops_analysis_dashboard" not in urls


def test_other_page_capability_does_not_attach_dashboard_tools():
    chat_kwargs = _attach(
        "帮我搭盘",
        {"app": "monitor", "capabilities": ["dashboard-builder"]},
    )
    urls = [item.get("url") for item in chat_kwargs["tools_servers"]]
    assert "langchain:ops_analysis_dashboard" not in urls


def _clear_ready():
    from django.core.cache import cache

    cache.clear()


def test_param_answer_prepares_the_saved_proposal_instead_of_searching_again():
    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, ToolExecutionStep, rewrite_dashboard_builder_plan
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import remember_ready_proposal

    _clear_ready()
    remember_ready_proposal(
        1,
        "current",
        {
            "schemaVersion": "1.0",
            "layout": [
                {
                    "name": "数量图",
                    "valueConfig": {
                        "dataSourceParams": [{"name": "bucket", "alias_name": "统计口径", "required": True, "filterType": "params", "value": ""}]
                    },
                }
            ],
            "filters": [],
        },
    )
    names = {"search_data_sources", "prepare_dashboard_proposal", "apply_dashboard_proposal"}
    original = ToolExecutionPlan(goal="回答", steps=[ToolExecutionStep(objective="回答", tools=["search_data_sources"])])
    planned = rewrite_dashboard_builder_plan(
        original,
        names,
        user_message="按模型",
        runtime_config={"configurable": {"caller_identity": {"team_id": 1}}},
    )
    assert [step.tools for step in planned.steps] == [["prepare_dashboard_proposal"], ["apply_dashboard_proposal"]]
    confirmed = rewrite_dashboard_builder_plan(original, names, user_message="确认")
    assert confirmed.steps[0].tools == ["apply_dashboard_proposal"]
    _clear_ready()


def test_ready_proposal_is_isolated_by_team_session_and_dashboard():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import load_ready_proposal, proposal_for_apply, remember_ready_proposal

    _clear_ready()
    remember_ready_proposal(
        1,
        "dashboard_426",
        {"schemaVersion": "1.0", "layout": [{"i": "kept", "valueConfig": {"chartType": "table", "dataSource": 219}}], "filters": []},
        session_id="session-a",
    )
    loaded = load_ready_proposal(1, "dashboard_426", session_id="session-a")
    assert loaded["layout"][0]["i"] == "kept"
    assert load_ready_proposal(9, "dashboard_426", session_id="session-a") is None
    assert load_ready_proposal(1, "dashboard_426", session_id="session-b") is None
    assert load_ready_proposal(1, "other-dashboard", session_id="session-a") is None
    assert proposal_for_apply({"reply": "确认"}, 1, "dashboard_426", session_id="session-a") == loaded


def _apply(proposal, dashboard_id="current", prepared=None):
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import apply_dashboard_proposal, remember_ready_proposal

    _clear_ready()
    stored = json.loads(proposal) if isinstance(proposal, str) else proposal
    if isinstance(stored, dict) and isinstance(stored.get("data"), dict):
        stored = stored["data"].get("proposal") or stored["data"]
    remember_ready_proposal(7, dashboard_id, stored, session_id="test-session")

    class Rpc:
        def run(self, method_name, **kwargs):
            if method_name == "list_dashboard_datasource_briefs":
                return {"briefs": []}
            assert method_name == "prepare_dashboard_proposal"
            if prepared is not None:
                return prepared
            return {"ok": True, "proposal": kwargs["proposal"], "pending": []}

    config = {
        "configurable": {
            "caller_identity": {"team_id": 7},
            "dashboard_session_id": "test-session",
            "dashboard_user_message": "确认",
        }
    }
    with (
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard.dispatch_custom_event") as dispatch,
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._rpc", return_value=Rpc()),
    ):
        result = apply_dashboard_proposal.func(proposal, dashboard_id, config)
    return result, dispatch


def test_apply_defaults_the_first_option_and_puts_it_on_the_canvas():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import apply_dashboard_proposal, remember_ready_proposal

    _clear_ready()
    proposal = {
        "schemaVersion": "1.0",
        "layout": [
            {
                "i": "need-param",
                "name": "数量图",
                "valueConfig": {
                    "chartType": "multiValue",
                    "dataSource": 210,
                    "dataSourceParams": [
                        {
                            "name": "bucket",
                            "alias_name": "统计口径",
                            "required": True,
                            "filterType": "params",
                            "value": "",
                            "inputConfig": {
                                "optionsSource": {
                                    "type": "static",
                                    "staticItems": [
                                        {"label": "按模型", "value": "model"},
                                        {"label": "按分类", "value": "classification"},
                                    ],
                                }
                            },
                        }
                    ],
                },
            }
        ],
        "filters": [],
    }

    class Rpc:
        def run(self, method_name, **kwargs):
            assert method_name == "prepare_dashboard_proposal"
            params = kwargs["proposal"]["layout"][0]["valueConfig"].get("dataSourceParams") or []
            if params and params[0].get("value"):
                return {"ok": True, "proposal": kwargs["proposal"], "pending": []}
            return {"ok": False, "reason": "pending", "pending": [{"index": 0, "reason": "required_param", "name": "bucket"}]}

    config = {"configurable": {"caller_identity": {"team_id": 7}, "dashboard_user_message": "确认"}}
    remember_ready_proposal(7, "current", proposal)
    with (
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard.dispatch_custom_event") as dispatch,
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._briefs", return_value=[]),
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._rpc", return_value=Rpc()),
    ):
        result = apply_dashboard_proposal.func(proposal, "current", config)

    event = dispatch.call_args.args[1]
    assert event["proposal"]["layout"][0]["valueConfig"]["dataSourceParams"][0]["value"] == "model"
    assert result["data"]["applied"] is True


def test_apply_parses_proposal_json_string():
    result, dispatch = _apply('{"schemaVersion":"1.0","layout":[]}', "dash-1")

    dispatch.assert_called_once()
    assert dispatch.call_args.args == (
        "dashboard_config_apply",
        {"dashboardId": "dash-1", "proposal": {"schemaVersion": "1.0", "layout": [], "filters": []}},
    )
    assert result["success"] is True
    assert result["data"]["applied"] is True


def test_apply_unwraps_prepare_result_and_widget_id():
    prepared = {
        "success": True,
        "data": {
            "ok": True,
            "proposal": {
                "schemaVersion": "1.0",
                "layout": [{"id": "card-1", "valueConfig": {"chartType": "single"}}],
            },
        },
    }
    _result, dispatch = _apply(prepared, "current")

    payload = dispatch.call_args.args[1]
    assert payload["proposal"]["filters"] == []
    assert payload["proposal"]["layout"][0]["i"] == "card-1"


def test_apply_publishes_to_the_request_event_queue():
    import asyncio

    from apps.opspilot.metis.llm.chain.nested_stream import bind_owned_event_queue

    queue = asyncio.Queue()
    previous = bind_owned_event_queue(queue)
    try:
        _result, dispatch = _apply({"schemaVersion": "1.0", "layout": [], "filters": []}, "dash-9")
    finally:
        bind_owned_event_queue(previous)

    dispatch.assert_not_called()
    event = queue.get_nowait()
    assert event["event"] == "on_custom_event"
    assert event["name"] == "dashboard_config_apply"
    assert event["data"]["dashboardId"] == "dash-9"
    assert event["data"]["proposal"]["schemaVersion"] == "1.0"


def test_apply_uses_remembered_proposal_when_the_model_payload_is_rejected():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import apply_dashboard_proposal, remember_ready_proposal

    _clear_ready()

    ready = {
        "schemaVersion": "1.0",
        "layout": [{"i": "ai-197", "valueConfig": {"chartType": "table", "dataSource": 197}}],
        "filters": [],
    }
    remember_ready_proposal(7, "current", ready)
    calls = []

    class Rpc:
        def run(self, method_name, **kwargs):
            assert method_name == "prepare_dashboard_proposal"
            calls.append(kwargs["proposal"])
            if kwargs["proposal"].get("layout") == []:
                return {"ok": False, "reason": "pending", "pending": []}
            return {"ok": True, "proposal": kwargs["proposal"], "pending": []}

    config = {"configurable": {"caller_identity": {"team_id": 7}, "dashboard_user_message": "确认"}}
    with (
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard.dispatch_custom_event") as dispatch,
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._rpc", return_value=Rpc()),
    ):
        result = apply_dashboard_proposal.func(
            {"schemaVersion": "1.0", "layout": [], "filters": []},
            "current",
            config,
        )

    dispatch.assert_called_once()
    assert dispatch.call_args.args[1]["proposal"]["layout"][0]["i"] == "ai-197"
    assert result["data"]["applied"] is True
    assert calls[0]["layout"][0]["i"] == "ai-197"


def test_apply_does_not_send_when_prepare_rejects():
    result, dispatch = _apply(
        {"schemaVersion": "1.0", "layout": [], "filters": []},
        prepared={"ok": False, "reason": "pending", "pending": [{"index": 0, "reason": "required_param"}]},
    )

    dispatch.assert_not_called()
    assert result["success"] is True
    assert result["data"]["ok"] is False


def test_prepare_on_remove_uses_current_canvas_not_model_redraft():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal, remember_ready_proposal

    _clear_ready()

    remember_ready_proposal(
        7,
        "current",
        {
            "schemaVersion": "1.0",
            "layout": [
                {
                    "i": "ai-267-host_count",
                    "name": "主机资源快照 主机数",
                    "valueConfig": {"chartType": "single", "dataSource": 267, "selectedFields": ["host_count"]},
                },
                {
                    "i": "ai-267-avg_cpu",
                    "name": "主机资源快照 平均CPU(%)",
                    "valueConfig": {"chartType": "single", "dataSource": 267, "selectedFields": ["avg_cpu"]},
                },
            ],
            "filters": [],
        },
    )
    captured = []

    class Rpc:
        def run(self, method_name, **kwargs):
            if method_name == "list_dashboard_datasource_briefs":
                return {"briefs": []}
            captured.append(kwargs["proposal"])
            return {"ok": True, "proposal": kwargs["proposal"], "pending": []}

    config = {
        "configurable": {
            "caller_identity": {"team_id": 7},
            "dashboard_user_message": "去掉主机资源快照 主机数这个单值组件",
        }
    }
    with patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._rpc", return_value=Rpc()):
        result = prepare_dashboard_proposal.func(
            {
                "schemaVersion": "1.0",
                "layout": [{"i": "new-cmdb", "name": "主机", "valueConfig": {"chartType": "table", "dataSource": 1}}],
                "filters": [{"id": "department__string"}],
            },
            config,
        )

    assert [item["i"] for item in captured[0]["layout"]] == ["ai-267-avg_cpu"]
    assert captured[0]["filters"] == []
    assert result["data"]["ok"] is True


def test_second_build_remembers_search_draft_not_the_canvas_already_applied():
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import (
        apply_dashboard_proposal,
        load_ready_proposal,
        mark_proposal_applied,
        prepare_dashboard_proposal,
        remember_ready_proposal,
        remember_search_candidates,
    )

    _clear_ready()
    remember_ready_proposal(
        7,
        "current",
        {
            "schemaVersion": "1.0",
            "layout": [
                {
                    "i": "alarm-1",
                    "name": "告警与关联事件趋势",
                    "valueConfig": {"chartType": "line", "dataSource": 12, "selectedFields": ["count"]},
                }
            ],
            "filters": [],
        },
    )
    mark_proposal_applied(7, "current")
    remember_search_candidates(
        [
            {
                "id": 215,
                "name": "CMDB实例列表",
                "tags": ["CMDB"],
                "chart_type": ["table"],
                "fields": [{"name": "model", "desc": "模型"}, {"name": "count", "desc": "数量"}],
                "params": [],
            }
        ],
        team_id=7,
    )

    class Rpc:
        def run(self, method_name, **kwargs):
            if method_name == "list_dashboard_datasource_briefs":
                return {"briefs": []}
            assert method_name == "prepare_dashboard_proposal"
            return {"ok": True, "proposal": kwargs["proposal"], "pending": []}

    config = {
        "configurable": {
            "caller_identity": {"team_id": 7},
            "dashboard_user_message": "帮我创建一个cmdb的仪表盘，展示资产分类、资产数据等等",
        }
    }
    with (
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard.dispatch_custom_event") as dispatch,
        patch("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._rpc", return_value=Rpc()),
    ):
        prepared = prepare_dashboard_proposal.func(
            {
                "schemaVersion": "1.0",
                "layout": [
                    {
                        "i": "alarm-1",
                        "name": "告警与关联事件趋势",
                        "valueConfig": {"chartType": "line", "dataSource": 12, "selectedFields": ["count"]},
                    }
                ],
                "filters": [],
            },
            config,
        )
        config["configurable"]["dashboard_user_message"] = "确认"
        applied = apply_dashboard_proposal.func(
            {"schemaVersion": "1.0", "layout": [], "filters": []},
            "current",
            config,
        )

    remembered = load_ready_proposal(7, "current")
    assert prepared["data"]["ok"] is True
    assert prepared["data"]["reply"].startswith("已生成并校验仪表盘方案")
    assert "图表类型: table" in prepared["data"]["reply"]
    assert "数据源: 215" in prepared["data"]["reply"]
    assert "字段: model、count" in prepared["data"]["reply"]
    assert remembered["layout"][0]["valueConfig"]["dataSource"] == 215
    assert all(item.get("i") != "alarm-1" for item in remembered["layout"])
    assert applied["data"]["applied"] is True
    published = dispatch.call_args.args[1]["proposal"]["layout"]
    assert published[0]["valueConfig"]["dataSource"] == 215
    assert all(item.get("i") != "alarm-1" for item in published)
