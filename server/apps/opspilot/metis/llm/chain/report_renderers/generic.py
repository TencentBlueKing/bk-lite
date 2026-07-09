"""Generic schema report renderer —— 工具直接出 ConfigAnalysisReportCard 兼容 JSON。

适用场景(给 MySQL / Redis / 其他领域的工具用):
- 工具的 ToolMessage.content 已经是 ConfigAnalysisReportCard 认识的 schema
  (report_id / title / summary / severity_sections / recommendations / ...)
- 不想为每个新领域写 k8s_report_tools.py 里那种"k8s data → 卡片 schema"的 renderer
- 走法:工具自己组织好 JSON,generic renderer 只透传 + 兜底 report_id / a2ui 字段

跟 k8s renderer 的对比:
- k8s    : 工具返回 k8s 专用 JSON,renderer 把它转成标准 schema(知识库 + 风险描述)
- generic: 工具直接返回标准 schema,renderer 透传,无领域知识耦合

前端兼容:generic 走和 k8s 完全相同的 config_analysis_report 事件,
ConfigAnalysisReportCard 直接吃 payload,前端 0 改动。
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from . import register_renderer


# ConfigAnalysisReportCard 真正会用的最小字段集合。其他字段原样透传,
# 卡片有自己的字段白名单(severity / count / workloads / risk),多写的字段
# 不会渲染,也不会报错。
# 这里只兜底卡渲染必需的 report_id + a2ui 契约,其他字段透传即可。
def render_generic_config_report(
    parsed: Any,
    package: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """工具直接出标准 schema JSON 时的 renderer。

    必填: title(没 title 不知道渲染啥,直接放弃)
    兜底: report_id, a2ui.component, a2ui.event_name, a2ui.render_mode

    parsed 的形态:
        {
            "title": "配置检查报告 - <资源名>",
            "cluster_name": "...",   # 可选
            "scope": {...},          # 可选
            "summary": {...},        # 可选
            "severity_sections": [...],  # 可选
            "recommendations": [...],    # 可选
            "markdown": "...",       # 可选
            ...
        }
    """
    if not isinstance(parsed, dict):
        return None
    title = parsed.get("title")
    if not title:
        # 没 title 没法渲染,放弃(避免静默给一张空白卡)
        return None

    payload = dict(parsed)  # 浅拷贝,不动调用方原数据
    payload.setdefault("report_id", str(uuid.uuid4())[:8])

    # a2ui 契约让前端 / 后续 consumer 知道这是 generic 类型
    # component 还是 "config-analysis-report",前端 ConfigAnalysisReportCard 仍能吃
    # event_name 用 "generic_config_report" 区分来源(后端 dispatch 也用它做 key)
    # 注意:a2ui 自身也要深一层拷贝,否则 setdefault 会污染调用方的 dict
    a2ui = payload.get("a2ui")
    if not isinstance(a2ui, dict):
        a2ui = {}
    else:
        a2ui = dict(a2ui)
    a2ui.setdefault("version", "1.0")
    a2ui.setdefault("component", "config-analysis-report")
    a2ui.setdefault("event_name", "generic_config_report")
    a2ui.setdefault("render_mode", "card")
    payload["a2ui"] = a2ui

    return payload


# 注册为 builtin renderer,跟 k8s 的两个并列
register_renderer("generic_config_report", render_generic_config_report)
