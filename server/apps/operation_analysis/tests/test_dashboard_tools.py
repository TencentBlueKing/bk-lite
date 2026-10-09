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
    from apps.operation_analysis.tools import dashboard as tools

    assert not hasattr(tools, "execute_dashboard_build")
    assert not hasattr(tools, "dashboard_fallback_messages")


def test_search_uses_explicit_requirements_and_operation_analysis_rpc(monkeypatch):
    from apps.operation_analysis.tools.dashboard import search_data_sources

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

    monkeypatch.setattr("apps.operation_analysis.tools.dashboard._run_dashboard_rpc", fake_run)
    result = search_data_sources.func(requirements, _config())

    assert result == {
        "success": True,
        "data": {"candidates": [{"id": 193, "name": "告警趋势"}]},
    }
    assert calls == [
        (
            "search_dashboard_data_sources",
            {"requirements": requirements, "team_id": 7},
        )
    ]


def test_prepare_returns_page_action_without_dispatching_or_caching(monkeypatch):
    from apps.operation_analysis.tools.dashboard import prepare_dashboard_proposal

    proposal = {
        "schemaVersion": "1.0",
        "layout": [{"i": "alarm-trend", "valueConfig": {"dataSource": 193}}],
        "filters": [],
    }
    prepared = {**proposal, "layout": [{**proposal["layout"][0], "x": 0, "y": 0, "w": 4, "h": 3}]}

    def fake_run(method, **kwargs):
        assert method == "prepare_dashboard_proposal"
        assert kwargs == {"proposal": proposal, "team_id": 7}
        return {"ok": True, "proposal": prepared}

    monkeypatch.setattr("apps.operation_analysis.tools.dashboard._run_dashboard_rpc", fake_run)
    result = prepare_dashboard_proposal.func(proposal, "dashboard_426", _config())

    assert result == {
        "success": True,
        "data": {
            "ok": True,
            "proposal": prepared,
            "pageAction": {
                "name": "dashboard_config_apply",
                "value": {
                    "dashboardId": "dashboard_426",
                    "proposal": prepared,
                },
            },
        },
    }


def test_prepare_does_not_emit_page_action_when_validation_is_pending(monkeypatch):
    from apps.operation_analysis.tools.dashboard import prepare_dashboard_proposal

    pending = {"ok": False, "reason": "pending", "pending": [{"reason": "required_param"}]}
    monkeypatch.setattr("apps.operation_analysis.tools.dashboard._run_dashboard_rpc", lambda method, **kwargs: pending)
    result = prepare_dashboard_proposal.func({"schemaVersion": "1.0"}, "current", _config())

    assert result == {"success": True, "data": pending}


@pytest.mark.parametrize("tool_name", ["search_data_sources", "prepare_dashboard_proposal"])
def test_dashboard_tools_require_caller_team(tool_name):
    from apps.operation_analysis.tools import dashboard as module

    tool = getattr(module, tool_name)
    args = ([{"text": "告警"}], {}) if tool_name == "search_data_sources" else ({"schemaVersion": "1.0"}, "current", {})
    result = tool.func(*args)

    assert result["success"] is False
    assert "组织" in result["error"]


def test_tool_metadata_and_translations_are_registered():
    opspilot = Path(__file__).resolve().parents[2] / "opspilot"
    metadata = yaml.safe_load((opspilot / "management/tools/tools.yml").read_text(encoding="utf-8"))
    toolkit = next(item for item in metadata["toolkits"] if item["id"] == "ops_analysis_dashboard")

    assert {item["name"] for item in toolkit["tools"]} == {
        "search_data_sources",
        "prepare_dashboard_proposal",
    }
    assert toolkit["tools"][0]["parameters"]
    assert toolkit["tools"][1]["parameters"]

    for language in ("zh-Hans.yaml", "en.yaml"):
        payload = yaml.safe_load((opspilot / "language" / language).read_text(encoding="utf-8"))
        translated = payload["tools"]["ops_analysis_dashboard"]
        assert translated["name"]
        assert translated["description"]
        assert set(translated["tools"]) == {
            "search_data_sources",
            "prepare_dashboard_proposal",
        }


def test_dashboard_rpc_can_run_inside_a_live_event_loop(monkeypatch):
    import asyncio

    from apps.operation_analysis.tools import dashboard as tools

    def run_that_needs_its_own_loop(method, **kwargs):
        asyncio.run(asyncio.sleep(0))
        return {"ok": True, "method": method, "team_id": kwargs.get("team_id")}

    class _Rpc:
        def run(self, method, **kwargs):
            return run_that_needs_its_own_loop(method, **kwargs)

    monkeypatch.setattr(tools, "_rpc", lambda: _Rpc())
    monkeypatch.setattr(
        "apps.operation_analysis.nats.auth.sign_dashboard_request",
        lambda team_id, method: {"team_id": team_id, "method": method},
    )

    async def _call():
        return tools._run_dashboard_rpc("search_dashboard_data_sources", team_id=7, requirements=[])

    result = asyncio.run(_call())
    assert result["ok"] is True
    assert result["team_id"] == 7
