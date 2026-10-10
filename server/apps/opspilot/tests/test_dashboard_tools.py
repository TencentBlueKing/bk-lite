import asyncio
import json
from pathlib import Path

import pytest
import yaml

from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader


def _config(team_id=7):
    return {
        "configurable": {
            "caller_identity": {
                "username": "alice",
                "domain": "default",
                "team_id": team_id,
                "include_children": False,
            },
            "messages": [{"role": "user", "content": "这段页面文字不得被工具读取"}],
        }
    }


def test_dashboard_toolkit_is_loaded_only_when_selected():
    tools = ToolsLoader.load_tools("langchain:ops_analysis_dashboard")
    assert {item.name for item in tools} == {
        "search_data_sources",
        "prepare_dashboard_proposal",
    }


def test_dashboard_tool_does_not_assemble_or_backfill():
    from apps.opspilot.metis.llm.tools import ops_analysis_dashboard as tools

    assert not hasattr(tools, "execute_dashboard_build")
    assert not hasattr(tools, "dashboard_fallback_messages")


def test_search_uses_explicit_requirements_and_operation_analysis_rpc(monkeypatch):
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import search_data_sources

    requirements = [
        {
            "text": "查看告警趋势",
            "purpose": "visualization",
            "domain": "告警",
            "analysisType": "trend",
            "chartType": "line",
        }
    ]
    calls = []

    def fake_run(method, **kwargs):
        calls.append((method, kwargs))
        return {"candidates": [{"id": 193, "name": "告警趋势"}]}

    monkeypatch.setattr("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc", fake_run)
    result = search_data_sources.func(requirements, _config())

    assert result["success"] is True
    assert result["data"]["candidates"] == [{"id": 193, "name": "告警趋势", "chart_type": [], "fields": []}]
    assert "193" in result["_next_step_hint"]
    assert "selectedFields" in result["_next_step_hint"]
    assert "不能为空" in result["_next_step_hint"]
    assert calls == [
        (
            "search_dashboard_data_sources",
            {
                "requirements": requirements,
                "team_id": 7,
                "user_info": {"user": "alice", "domain": "default", "team": 7, "include_children": False},
            },
        )
    ]


def test_prepare_returns_page_action_without_dispatching_or_caching(monkeypatch):
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal

    proposal = {
        "schemaVersion": "1.0",
        "layout": [{"i": "alarm-trend", "valueConfig": {"dataSource": 193}}],
        "filters": [],
    }
    prepared = {**proposal, "layout": [{**proposal["layout"][0], "x": 0, "y": 0, "w": 4, "h": 3}]}

    def fake_run(method, **kwargs):
        assert method == "prepare_dashboard_proposal"
        assert kwargs == {
            "proposal": proposal,
            "team_id": 7,
            "user_info": {"user": "alice", "domain": "default", "team": 7, "include_children": False},
        }
        return {"ok": True, "proposal": prepared}

    monkeypatch.setattr("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc", fake_run)
    result = prepare_dashboard_proposal.func(proposal, "dashboard_426", _config())

    assert result["success"] is True
    assert result["data"] == {
        "ok": True,
        "proposal": prepared,
        "pageAction": {
            "name": "dashboard_config_apply",
            "value": {
                "dashboardId": "dashboard_426",
                "proposal": prepared,
            },
        },
    }
    assert "不要再次调用" in result["_next_step_hint"]


def test_search_catalog_fits_in_the_model_window_and_keeps_real_ids(monkeypatch):
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import search_data_sources

    candidates = []
    for index in range(12):
        candidates.append(
            {
                "id": 200 + index,
                "name": f"CMDB 概览 {index}",
                "desc": "很长的说明" * 20,
                "tags": ["CMDB"],
                "chart_type": ["single", "gauge"],
                "params": [
                    {
                        "name": "organization",
                        "alias_name": "组织",
                        "filterType": "filter",
                        "required": False,
                        "default": "",
                        "inputConfig": {
                            "control": "organization",
                            "optionsSource": {"type": "static", "staticItems": [{"label": "全部", "value": "all"}]},
                        },
                    }
                ],
                "fields": [{"name": f"metric_{field}", "type": "number", "desc": "指标说明" * 8} for field in range(8)],
                "option_ready": True,
            }
        )

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc",
        lambda method, **kwargs: {"candidates": candidates},
    )
    result = search_data_sources.func([{"text": "CMDB概览"}], _config())
    encoded = json.dumps(result, ensure_ascii=False)

    assert "example" not in result["data"]
    assert [item["id"] for item in result["data"]["candidates"]] == [200 + index for index in range(12)]
    assert result["data"]["candidates"][0]["fields"][0]["name"] == "metric_0"
    assert result["data"]["candidates"][0]["fields"][0]["description"]
    assert result["data"]["candidates"][0]["chart_type"] == ["single", "gauge"]
    assert result["data"]["candidates"][0]["params"] == [
        {"name": "organization", "alias": "组织", "type": "string", "filterType": "filter"},
    ]
    for candidate in candidates:
        assert str(candidate["id"]) in result["_next_step_hint"]
    assert "inputConfig" not in encoded
    assert "不要把英文字段名当成标题" in result["_next_step_hint"]
    assert "不要全部做成 single" in result["_next_step_hint"]
    assert result["data"]["candidates"][0]["tags"] == ["CMDB"]
    assert list(result)[0] == "success"


def test_search_plan_without_prepare_gets_an_apply_step(caplog):
    import logging

    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, ToolExecutionStep, ensure_dashboard_prepare_follows_search

    sentinel = "plan-goal-sentinel-not-for-logs"
    template = "event=dashboard_prepare_step_appended search_tool=%s prepare_tool=%s"
    plan = ToolExecutionPlan(
        goal=sentinel,
        steps=[ToolExecutionStep(objective="检索告警数据源", tools=["search_data_sources", "request_user_choice"])],
    )
    with caplog.at_level(logging.DEBUG, logger="opspilot"):
        fixed = ensure_dashboard_prepare_follows_search(
            plan,
            {"search_data_sources", "prepare_dashboard_proposal", "request_user_choice"},
            max_steps=4,
        )
    assert [step.tools for step in fixed.steps] == [
        ["search_data_sources"],
        ["prepare_dashboard_proposal"],
    ]
    records = [record for record in caplog.records if record.msg == template]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert records[0].args == ("search_data_sources", "prepare_dashboard_proposal")
    assert records[0].getMessage() == (
        "event=dashboard_prepare_step_appended search_tool=search_data_sources prepare_tool=prepare_dashboard_proposal"
    )
    assert sentinel not in caplog.text
    assert not any(record.levelno >= logging.INFO and record.msg == template for record in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="opspilot"):
        unchanged = ensure_dashboard_prepare_follows_search(
            fixed,
            {"search_data_sources", "prepare_dashboard_proposal", "request_user_choice"},
            max_steps=4,
        )
    assert [step.tools for step in unchanged.steps] == [
        ["search_data_sources"],
        ["prepare_dashboard_proposal"],
    ]
    assert not any(record.msg == template for record in caplog.records)


def test_search_catalog_stays_in_the_next_step_summary():
    from langchain_core.messages import AIMessage, ToolMessage

    from apps.opspilot.metis.llm.chain.deepagent_assembly import DeepAgentAssemblyMixin, compact_completed_step_line

    payload = {
        "success": True,
        "data": {
            "candidates": [
                {
                    "id": 218,
                    "name": "CMDB 覆盖概览",
                    "tags": ["CMDB"],
                    "chart_type": ["single", "gauge"],
                    "fields": [{"name": "covered"}, {"name": "total"}],
                }
            ]
        },
        "_next_step_hint": "说明" * 400,
    }
    messages = [
        ToolMessage(content=json.dumps(payload, ensure_ascii=False), name="search_data_sources", tool_call_id="1"),
        AIMessage(content="检索完成。" + "忽略" * 300),
    ]
    summary = DeepAgentAssemblyMixin._summarize_planned_step_messages(messages)
    line = compact_completed_step_line("检索 CMDB 数据源", summary)
    assert line.index("dataSource=218") < line.index("检索完成")
    assert "name=CMDB 覆盖概览" in line
    assert "tag=CMDB" in line
    assert "fields=covered,total" in line
    assert "概览源最多两个 single" in line
    assert "说明说明" not in line


def test_prepare_flattens_nested_rows_before_validation(monkeypatch):
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal

    seen = {}

    def fake_run(method, **kwargs):
        seen["proposal"] = kwargs["proposal"]
        return {"ok": True, "proposal": kwargs["proposal"]}

    monkeypatch.setattr("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc", fake_run)
    result = prepare_dashboard_proposal.func(
        {
            "schemaVersion": "1.0",
            "layout": [
                {
                    "type": "row",
                    "children": [
                        {
                            "name": "实例总量",
                            "valueConfig": {"chartType": "single", "dataSource": 218, "selectedFields": ["instance_count"]},
                        }
                    ],
                }
            ],
        },
        "current",
        _config(),
    )

    widget = seen["proposal"]["layout"][0]
    assert widget["valueConfig"]["dataSource"] == 218
    assert "children" not in widget
    assert result["data"]["pageAction"]["value"]["proposal"]["layout"][0]["name"] == "实例总量"


def test_unknown_datasource_returns_real_sources_without_echoing_the_proposal(monkeypatch):
    from apps.operation_analysis.services.dashboard_proposal_service import brief_from_source
    from apps.operation_analysis.services.dashboard_proposal_service import prepare_dashboard_proposal as prepare
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal

    brief = brief_from_source(
        {
            "id": 218,
            "name": "CMDB 覆盖概览",
            "chart_type": ["single"],
            "field_schema": [{"name": "instance_count", "title": "实例总量"}],
        }
    )

    def fake_run(method, **kwargs):
        return prepare(kwargs["proposal"], [brief])

    monkeypatch.setattr("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc", fake_run)
    result = prepare_dashboard_proposal.func(
        {
            "schemaVersion": "1.0",
            "layout": [{"name": "实例总量", "valueConfig": {"chartType": "single", "dataSource": 1, "selectedFields": ["instance_total"]}}],
        },
        "current",
        _config(),
    )

    assert result["data"]["ok"] is False
    assert result["data"]["sources"][0]["id"] == 218
    assert "instance_count" in result["data"]["sources"][0]["fields"]
    assert "proposal" not in result["data"]
    assert "不要改试" in result["_next_step_hint"]


def test_unknown_field_hint_lists_the_real_field_names(monkeypatch):
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc",
        lambda method, **kwargs: {
            "ok": False,
            "reason": "unknown_field",
            "pending": [{"index": 0, "fields": ["CI数量"], "allowedFields": ["instance_count", "model_count"]}],
        },
    )
    result = prepare_dashboard_proposal.func(
        {
            "schemaVersion": "1.0",
            "layout": [{"valueConfig": {"chartType": "single", "dataSource": 218, "selectedFields": ["CI数量"]}}],
        },
        "current",
        _config(),
    )

    assert "instance_count" in result["_next_step_hint"]
    assert "CI数量" in result["_next_step_hint"]
    assert result["_next_step_hint"].index("instance_count") < 180


def test_prepare_schema_failure_tells_the_model_the_proposal_shape(monkeypatch):
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal

    rejected = {"ok": False, "reason": "schema", "pending": []}
    monkeypatch.setattr("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc", lambda method, **kwargs: rejected)
    result = prepare_dashboard_proposal.func({"title": "概览", "panels": []}, "current", _config())

    assert result["success"] is True
    assert result["data"] == rejected
    assert "pageAction" not in result["data"]
    hint = result["_next_step_hint"]
    assert "layout" in hint
    assert "selectedFields" in hint
    assert "panels" in hint
    assert "data_source_id" in hint


def test_prepare_does_not_emit_page_action_when_validation_is_pending(monkeypatch):
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal

    pending = {"ok": False, "reason": "pending", "pending": [{"reason": "required_param"}]}
    monkeypatch.setattr("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc", lambda method, **kwargs: pending)
    result = prepare_dashboard_proposal.func({"schemaVersion": "1.0"}, "current", _config())

    assert result["success"] is True
    assert result["data"] == pending
    assert "pageAction" not in result["data"]
    assert "required_param" in result["_next_step_hint"]
    assert "禁止原样重试" in result["_next_step_hint"]


@pytest.mark.parametrize("tool_name", ["search_data_sources", "prepare_dashboard_proposal"])
def test_dashboard_tools_require_caller_team(tool_name):
    from apps.opspilot.metis.llm.tools import ops_analysis_dashboard as module

    tool = getattr(module, tool_name)
    args = ([{"text": "告警"}], {}) if tool_name == "search_data_sources" else ({"schemaVersion": "1.0"}, "current", {})
    result = tool.func(*args)

    assert result["success"] is False
    assert "caller_identity" in result["error"]


def test_tool_metadata_and_translations_are_registered():
    opspilot = Path(__file__).resolve().parents[1]
    metadata = yaml.safe_load((opspilot / "management/tools/tools.yml").read_text(encoding="utf-8"))
    toolkit = next(item for item in metadata["toolkits"] if item["id"] == "ops_analysis_dashboard")

    assert {item["name"] for item in toolkit["tools"]} == {
        "search_data_sources",
        "prepare_dashboard_proposal",
    }
    assert toolkit["tools"][0]["parameters"]
    proposal = toolkit["tools"][1]
    assert "layout" in proposal["description"]
    assert "data_source_id" in proposal["description"]
    assert "selectedFields" in proposal["parameters"]["proposal"]["description"]

    for language in ("zh-Hans.yaml", "en.yaml"):
        payload = yaml.safe_load((opspilot / "language" / language).read_text(encoding="utf-8"))
        translated = payload["tools"]["ops_analysis_dashboard"]
        assert translated["name"]
        assert translated["description"]
        assert set(translated["tools"]) == {
            "search_data_sources",
            "prepare_dashboard_proposal",
        }
        assert "layout" in translated["tools"]["prepare_dashboard_proposal"]["description"]


def test_dashboard_rpc_can_run_inside_a_live_event_loop(monkeypatch):
    import asyncio

    from apps.opspilot.metis.llm.tools import ops_analysis_dashboard as tools

    def run_that_needs_its_own_loop(method, **kwargs):
        asyncio.run(asyncio.sleep(0))
        return {"ok": True, "method": method, "team_id": kwargs.get("team_id")}

    class _Rpc:
        def run(self, method, **kwargs):
            return run_that_needs_its_own_loop(method, **kwargs)

    monkeypatch.setattr(tools, "_rpc", lambda: _Rpc())
    monkeypatch.setattr(
        "apps.operation_analysis.nats.auth.sign_dashboard_request",
        lambda team_id, method, user_info=None: {"team_id": team_id, "method": method},
    )

    async def _call():
        return tools._run_dashboard_rpc("search_dashboard_data_sources", team_id=7, requirements=[])

    result = asyncio.run(_call())
    assert result["ok"] is True
    assert result["team_id"] == 7


@pytest.mark.parametrize("as_tool_call", [False, True])
def test_real_tool_end_preserves_json_page_action(monkeypatch, as_tool_call):
    from ag_ui.encoder import EventEncoder

    from apps.opspilot.metis.llm.chain.graph import BasicGraph
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal

    proposal = {"schemaVersion": "1.0", "layout": [{"valueConfig": {"chartType": "single", "dataSource": 23, "selectedFields": ["value"]}}]}
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc",
        lambda method, **kwargs: {"ok": True, "proposal": proposal},
    )

    async def collect():
        tool_input = {"proposal": proposal}
        if as_tool_call:
            tool_input = {"type": "tool_call", "id": "apply-1", "name": "prepare_dashboard_proposal", "args": tool_input}
        return [event async for event in prepare_dashboard_proposal.astream_events(tool_input, config=_config(), version="v2")]

    events = asyncio.run(collect())
    event = next(event for event in events if event["event"] == "on_tool_end")
    current_calls = {"apply-1": {"run_id": event["run_id"], "name": "prepare_dashboard_proposal"}}

    class DashboardGraph(BasicGraph):
        async def compile_graph(self, request):
            return None

    graph = DashboardGraph()
    wire_events = graph._handle_tool_end_event(event, event["data"], EventEncoder(), current_calls)
    result_event = next(json.loads(line[6:]) for line in wire_events if '"TOOL_CALL_RESULT"' in line)
    delivered = json.loads(result_event["content"])
    assert result_event["toolCallId"] == "apply-1"
    assert delivered["data"]["pageAction"]["value"]["proposal"] == proposal


def test_success_hint_survives_execution_result_compaction(monkeypatch):
    from types import SimpleNamespace

    from langchain_core.messages import ToolMessage

    from apps.opspilot.metis.llm.agent.tool_execution_planner import compact_planned_execution_messages
    from apps.opspilot.metis.llm.middleware.tool_runtime import terminal_success_denial
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal

    proposal = {"schemaVersion": "1.0", "layout": [{"name": "资产数量", "valueConfig": {"dataSource": 23}} for _ in range(20)]}
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc",
        lambda method, **kwargs: {"ok": True, "proposal": proposal},
    )
    result = prepare_dashboard_proposal.func(proposal, "current", _config())
    message = ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id="apply-1", name="prepare_dashboard_proposal")
    compacted = compact_planned_execution_messages([message], max_tool_chars=1500)
    assert result["_next_step_hint"] in compacted[0].content
    retry = SimpleNamespace(tool_call={"id": "apply-2", "name": "prepare_dashboard_proposal", "args": {}}, messages=compacted)
    assert terminal_success_denial(retry) is not None


@pytest.mark.parametrize("layout", [None, {}, "widgets"])
def test_missing_or_invalid_layout_cannot_emit_an_empty_canvas_action(monkeypatch, layout):
    from apps.operation_analysis.services.dashboard_proposal_service import prepare_dashboard_proposal as prepare
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal

    proposal = {"schemaVersion": "1.0", "panels": [{"title": "资产总数"}]}
    if layout is not None:
        proposal["layout"] = layout
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc",
        lambda method, **kwargs: prepare(kwargs["proposal"], []),
    )
    result = prepare_dashboard_proposal.func(proposal, "current", _config())
    assert result["data"]["ok"] is False
    assert "pageAction" not in result["data"]
    assert "layout" in result["_next_step_hint"]


def test_explicit_empty_layout_still_supports_removing_widgets(monkeypatch):
    from apps.operation_analysis.services.dashboard_proposal_service import prepare_dashboard_proposal as prepare
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import prepare_dashboard_proposal

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc",
        lambda method, **kwargs: prepare(kwargs["proposal"], []),
    )
    result = prepare_dashboard_proposal.func({"schemaVersion": "1.0", "layout": []}, "current", _config())
    assert result["data"]["pageAction"]["value"]["proposal"]["layout"] == []


@pytest.mark.parametrize("requirements", [[], ["告警趋势"], [{"text": "告警"}, "趋势"]])
def test_search_rejects_requirements_that_are_not_objects(requirements):
    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import search_data_sources

    result = search_data_sources.func(requirements, _config())
    assert result == {"success": False, "error": "requirements 必须是非空对象数组"}


def test_search_rpc_failure_keeps_error_and_omits_it_from_logs(monkeypatch, caplog):
    import logging

    from apps.opspilot.metis.llm.tools.ops_analysis_dashboard import search_data_sources

    sentinel = "dashboard-rpc-secret-payload"

    def explode(method, **kwargs):
        raise RuntimeError(sentinel)

    monkeypatch.setattr("apps.opspilot.metis.llm.tools.ops_analysis_dashboard._run_dashboard_rpc", explode)
    with caplog.at_level(logging.ERROR, logger="opspilot"):
        result = search_data_sources.func([{"text": "告警趋势"}], _config())

    assert result == {"success": False, "error": sentinel}
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    record = errors[0]
    assert record.msg == "event=dashboard_tool_rpc_failed method=%s failed_stage=%s error_type=%s"
    assert record.args == ("search_dashboard_data_sources", "rpc", "RuntimeError")
    assert record.exc_info[0] is RuntimeError
    assert record.exc_info[1].args == ("dashboard tool rpc failed",)
    assert record.exc_info[2].tb_frame.f_code.co_name == "search_data_sources"
    assert record.exc_info[2].tb_next.tb_frame.f_code.co_name == "explode"
    rendered = logging.Formatter().format(record)
    assert record.getMessage() == "event=dashboard_tool_rpc_failed method=search_dashboard_data_sources failed_stage=rpc error_type=RuntimeError"
    assert sentinel not in record.getMessage()
    assert sentinel not in rendered
    assert rendered.count("Traceback") == 1
