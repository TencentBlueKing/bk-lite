"""generic_config_report renderer 单元测试。

适用场景:任何新领域(MySQL / Redis / etc.)的工具只要输出符合
ConfigAnalysisReportCard schema 的 JSON,就能借这个 renderer 走 dispatch,
不需要再为每个领域写"数据 → 卡片 schema"的转换。

锁定行为:
- 模块加载时已注册 generic_config_report
- 透传:parsed 里所有字段原样进 payload
- 兜底:report_id / a2ui 契约(version / component / event_name / render_mode)
- 拒收:parsed 不是 dict 或缺 title,直接 None
- 不动 k8s 已有 capability 的注册和 dispatch 路径
"""
from __future__ import annotations

from typing import Any, Dict

import pytest


pytestmark = pytest.mark.unit


def test_generic_renderer_is_registered():
    """generic_config_report 必须已经注册(模块加载时)。"""
    from apps.opspilot.metis.llm.chain.report_renderers import RENDERER_REGISTRY

    assert "generic_config_report" in RENDERER_REGISTRY
    # k8s 那两个还在(没被覆盖)
    assert "config_analysis_report" in RENDERER_REGISTRY
    assert "repair_diff_report" in RENDERER_REGISTRY


def test_generic_renderer_passes_through_parsed_fields():
    """工具给的所有字段原样进 payload,renderer 不做转换。"""
    from apps.opspilot.metis.llm.chain.report_renderers import get_renderer

    renderer = get_renderer("generic_config_report")
    assert renderer is not None

    parsed = {
        "title": "MySQL 配置检查报告 - db-01",
        "cluster_name": "prod-mysql",
        "summary": {"total": 5, "problematic": 3, "healthy": 2},
        "severity_sections": [
            {
                "severity": "high",
                "title": "High",
                "issues": [
                    {
                        "issue": "无慢查询日志",
                        "count": 2,
                        "workloads": ["db-01", "db-02"],
                        "risk": "排查慢查询困难,可能影响性能调优。",
                    }
                ],
            }
        ],
        "recommendations": [
            {"priority": "P1", "action": "开启慢查询日志", "target": "db-01", "benefit": "可定位性能瓶颈。"}
        ],
        "scope": {"cluster_name": "prod-mysql", "namespace": "default"},
        "custom_field": "renderer must not drop this",  # 未在白名单的字段也要保留
    }
    package = {"name": "mysql-specialist", "id": 99}
    payload = renderer(parsed, package)

    assert payload is not None
    # 透传:工具给的字段都保留
    assert payload["title"] == parsed["title"]
    assert payload["cluster_name"] == parsed["cluster_name"]
    assert payload["summary"] == parsed["summary"]
    assert payload["severity_sections"] == parsed["severity_sections"]
    assert payload["recommendations"] == parsed["recommendations"]
    assert payload["scope"] == parsed["scope"]
    assert payload["custom_field"] == "renderer must not drop this"
    # package 暂未使用(为未来扩展预留)
    # assert payload["matched_package"] == package  # 留作未来扩展点


def test_generic_renderer_backfills_report_id():
    """工具没给 report_id 时,renderer 必须兜底生成 8 位短 id。"""
    from apps.opspilot.metis.llm.chain.report_renderers import get_renderer

    renderer = get_renderer("generic_config_report")
    parsed = {"title": "No-Report-Id Report"}
    payload = renderer(parsed, {})

    assert payload is not None
    assert "report_id" in payload
    # uuid4().hex[:8] 长度
    assert len(payload["report_id"]) == 8
    assert isinstance(payload["report_id"], str)


def test_generic_renderer_preserves_tool_supplied_report_id():
    """工具已经给了 report_id 时,renderer 不得覆盖。"""
    from apps.opspilot.metis.llm.chain.report_renderers import get_renderer

    renderer = get_renderer("generic_config_report")
    parsed = {"title": "X", "report_id": "custom-id"}
    payload = renderer(parsed, {})

    assert payload["report_id"] == "custom-id"


def test_generic_renderer_backfills_a2ui_contract():
    """a2ui 契约缺失时兜底,event_name = 'generic_config_report'(区分 k8s 源)。"""
    from apps.opspilot.metis.llm.chain.report_renderers import get_renderer

    renderer = get_renderer("generic_config_report")
    parsed = {"title": "X"}  # 无 a2ui
    payload = renderer(parsed, {})

    a2ui = payload["a2ui"]
    assert a2ui["version"] == "1.0"
    assert a2ui["component"] == "config-analysis-report"
    assert a2ui["event_name"] == "generic_config_report"
    assert a2ui["render_mode"] == "card"


def test_generic_renderer_preserves_partial_a2ui():
    """a2ui 给了部分字段时,只兜底缺失的,不得覆盖已有值。"""
    from apps.opspilot.metis.llm.chain.report_renderers import get_renderer

    renderer = get_renderer("generic_config_report")
    parsed = {
        "title": "X",
        "a2ui": {"version": "2.0", "event_name": "custom_event"},
    }
    payload = renderer(parsed, {})

    a2ui = payload["a2ui"]
    # 已有的不能改
    assert a2ui["version"] == "2.0"
    assert a2ui["event_name"] == "custom_event"
    # 缺的兜底
    assert a2ui["component"] == "config-analysis-report"
    assert a2ui["render_mode"] == "card"


def test_generic_renderer_rejects_non_dict():
    """parsed 不是 dict(比如 string / list)时,直接 None,不出空卡。"""
    from apps.opspilot.metis.llm.chain.report_renderers import get_renderer

    renderer = get_renderer("generic_config_report")
    for invalid in [None, "just a string", ["a", "list"], 42, True]:
        assert renderer(invalid, {}) is None, f"Should reject {invalid!r}"


def test_generic_renderer_rejects_missing_title():
    """title 缺失时直接 None —— 没 title 没法渲染,放弃总比出空卡好。"""
    from apps.opspilot.metis.llm.chain.report_renderers import get_renderer

    renderer = get_renderer("generic_config_report")
    assert renderer({}, {}) is None
    assert renderer({"title": ""}, {}) is None
    assert renderer({"title": None}, {}) is None


def test_generic_renderer_does_not_mutate_input_parsed():
    """renderer 必须不修改调用方的 parsed 字典(dict() 浅拷贝足以防误改)。"""
    from apps.opspilot.metis.llm.chain.report_renderers import get_renderer

    renderer = get_renderer("generic_config_report")
    parsed = {
        "title": "X",
        "summary": {"total": 5, "problematic": 3},
        "a2ui": {"event_name": "custom"},
    }
    snapshot = {
        "title": "X",
        "summary": {"total": 5, "problematic": 3},
        "a2ui": {"event_name": "custom"},
    }
    renderer(parsed, {})
    assert parsed == snapshot  # 输入字典未被修改


def test_k8s_renderers_unaffected_by_generic():
    """generic_config_report 不会污染 k8s 已有 capability 的注册和 dispatch 路径。"""
    from apps.opspilot.metis.llm.chain.report_renderers import get_renderer

    k8s = get_renderer("config_analysis_report")
    assert k8s is not None
    # k8s 自己的判断:无效 parsed 返 None
    assert k8s({"error": "x"}, {}) is None
    assert k8s(None, {}) is None
    # k8s 有效 parsed 产出标准 k8s schema(走 build_config_analysis_report_payload)
    valid_k8s = {
        "cluster_name": "K1",
        "total": 1,
        "problematic": 1,
        "issues_detail": [
            {"severity": "high", "issue": "缺探针", "count": 1, "workloads": ["x"]}
        ],
    }
    payload = k8s(valid_k8s, {})
    assert payload is not None
    assert payload["a2ui"]["event_name"] == "config_analysis_report"  # k8s 用自己的 event_name


def test_generic_capability_uses_dedicated_event_name():
    """generic_config_report 注册为 'generic_config_report' 事件,跟 k8s 'config_analysis_report' 区分。

    这样后端 dispatch 按事件名路由,前端 / 后续 consumer 可以按需监听特定源。
    """
    from apps.opspilot.metis.llm.chain.report_renderers import RENDERER_REGISTRY, get_renderer

    # 直接用 registry 验证(模拟 dispatcher 行为)
    assert RENDERER_REGISTRY.get("generic_config_report") is not None
    # 跟 k8s 同一事件 key 不会冲突
    assert RENDERER_REGISTRY.get("config_analysis_report") is not None
    assert RENDERER_REGISTRY.get("generic_config_report") is not RENDERER_REGISTRY.get("config_analysis_report")
