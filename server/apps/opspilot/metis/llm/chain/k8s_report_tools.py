"""k8s_report_tools 兼容 shim(2026-07 重构)。

历史:K039 之前的报告渲染代码全在这一个文件里。重构后拆到
``report_renderers/`` 包:
- ``report_renderers/__init__.py`` — 通用 framework(RENDERER_REGISTRY /
  TOOL_RESULT_TO_CAPABILITY / register_* / merge_analysis_results)
- ``report_renderers/k8s.py``       — k8s 专用 builders / 风险规则 / 两个 builtin renderers
- ``report_renderers/generic.py``   — 通用透传 renderer(给 MySQL/Redis 等用)

本文件保留只为向后兼容:node.py / 测试 / 其它模块里所有
``from apps.opspilot.metis.llm.chain.k8s_report_tools import X``
继续工作(行为零变化)。

新代码应该直接从 ``report_renderers`` 包里 import(见那个包的 docstring)。
"""
from __future__ import annotations

# 通用 framework(name 在新包里的 __init__.py)
from .report_renderers import (  # noqa: F401
    RENDERER_REGISTRY,
    TOOL_RESULT_TO_CAPABILITY,
    get_renderer,
    merge_analysis_results,
    register_renderer,
    register_tool_result_capability,
    strip_phantom_tool_calls,
)

# k8s 专用 builders / 风险规则(原文件里 100~678 行的内容,搬到 k8s.py)
from .report_renderers.k8s import (  # noqa: F401
    _build_config_analysis_report_total,
    _build_config_analysis_scan_range,
    _build_config_analysis_scope,
    _config_analysis_benefit_description,
    _config_analysis_fix_description,
    _config_analysis_risk_description,
    build_a2ui_report_contract,
    build_config_analysis_report_markdown,
    build_config_analysis_report_payload,
    build_config_diff_report_payload,
    build_post_tool_directives,
    build_repair_mode_choice_args,
    downgrade_config_analysis_next_step_hint,
    find_completed_k8s_analysis_choice,
    find_pending_k8s_analysis_choice,
    should_emit_config_analysis_report,
)

# builtin renderers(name 在 k8s.py 里,但调用方常用 "from ... import render_*")
from .report_renderers.k8s import (  # noqa: F401
    render_config_analysis_report,
    render_repair_diff_report,
)
