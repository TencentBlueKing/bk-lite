"""Report renderer framework — capability-driven 报告渲染分发。

设计:
- 技能包在 manifest.capabilities 声明自己支持哪些 report 能力
- 后端 dispatcher(node.py)读 skill 包声明的能力,从 RENDERER_REGISTRY 拿 renderer
- renderer 吃工具返回的 parsed dict + matched_package 上下文,产出 AG-UI report payload
- 任一来源 emit 同一份 payload 后,前端 ConfigAnalysisReportCard / DiffReportCard 直接渲染

新增能力 = 写一个 renderer + `register_renderer("能力名", fn)` 一行,不动 dispatcher。
新领域(MySQL 等)= 把工具 JSON 输出对齐到 ConfigAnalysisReportCard schema,接
generic_config_report renderer,前端 0 改动。

模块布局:
- __init__.py  ← registry / register_* / merge_analysis_results(纯框架)
- k8s.py       ← k8s-specific 全部(builder / renderer / 风险规则)
- generic.py   ← 通用透传 renderer(工具直接出 schema JSON,这里只补 report_id / a2ui)

k8s_report_tools.py 是这个包的兼容 shim,继续 re-export 旧名字,既有
node.py / 测试文件 import 路径不变。
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Renderer registry
#
# Renderer contract:
#   (parsed_tool_output, matched_package_dict) -> report_payload | None
#   - Return None  → dispatcher 不发事件
#   - Return dict  → 走 dispatch_custom_event(capability, payload)
# ---------------------------------------------------------------------------
ReportRenderer = Callable[[Any, Dict[str, Any]], Optional[Dict[str, Any]]]
RENDERER_REGISTRY: Dict[str, ReportRenderer] = {}


def register_renderer(capability: str, renderer: ReportRenderer) -> None:
    """注册一个 capability 对应的渲染器(同 capability 后写覆盖前写)。"""
    RENDERER_REGISTRY[capability] = renderer


def get_renderer(capability: str) -> Optional[ReportRenderer]:
    return RENDERER_REGISTRY.get(capability)


# ---------------------------------------------------------------------------
# Tool → capability 映射
#
# deepagent 跑完普通工具后,把 JSON 放进 ToolMessage,后处理器扫这个 tool name,
# 命中 TOOL_RESULT_TO_CAPABILITY 就调对应 capability 的 renderer 把它转成报告。
# ---------------------------------------------------------------------------
TOOL_RESULT_TO_CAPABILITY: Dict[str, str] = {}


def register_tool_result_capability(tool_name: str, capability: str) -> None:
    """声明某工具的返回结果由哪个 capability 的 renderer 接管。"""
    TOOL_RESULT_TO_CAPABILITY[tool_name] = capability


# ---------------------------------------------------------------------------
# 多次工具结果合并
#
# 后处理器把同一 capability 触发的多次工具结果合并成一次报告(LLM 分 namespace
# 调 7 次分析工具,只 emit 一张合并卡)。issues_detail 按 (severity, issue)
# 去重后 sum count / union workloads;total/problematic/healthy 累加;
# cluster_name 多 namespace 时改成 cluster_names 列表。
# 注意:不能简单 extend all_issues,LLM 每次分析返回的 issues_detail 都有
# "未配置存活探针""缺资源限制"等通用条目,串接后前端会出 N 行同一 issue 类型。
# ---------------------------------------------------------------------------
def merge_analysis_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {}
    valid = [r for r in results if isinstance(r, dict)]
    if not valid:
        return {}
    if len(valid) == 1:
        return valid[0]
    # 用最后一次调用作基线(保留最新一次扫描的 cluster_name / total)
    merged = dict(valid[-1])

    # 按 (severity, issue) 去重 issues_detail
    issue_index: Dict[tuple, Dict[str, Any]] = {}
    order: list[tuple] = []
    cluster_names: set[str] = set()
    total = 0
    problematic = 0
    healthy = 0
    for r in valid:
        details = r.get("issues_detail") or []
        if isinstance(details, list):
            for item in details:
                if not isinstance(item, dict):
                    continue
                severity = str(item.get("severity") or "info")
                issue = str(item.get("issue") or "").strip()
                if not issue:
                    continue
                key = (severity, issue)
                count = item.get("count") or 0
                workloads = item.get("workloads") or []
                if key not in issue_index:
                    issue_index[key] = {
                        "severity": severity,
                        "issue": issue,
                        "count": 0,
                        "workloads": [],
                    }
                    order.append(key)
                merged_item = issue_index[key]
                try:
                    merged_item["count"] = int(merged_item["count"]) + int(count)
                except (TypeError, ValueError):
                    pass
                if isinstance(workloads, list):
                    for w in workloads:
                        if isinstance(w, str) and w and w not in merged_item["workloads"]:
                            merged_item["workloads"].append(w)
        cn = r.get("cluster_name")
        if isinstance(cn, str) and cn:
            cluster_names.add(cn)
        if isinstance(r.get("total"), int):
            total += r["total"]
        if isinstance(r.get("problematic"), int):
            problematic += r["problematic"]
        if isinstance(r.get("healthy"), int):
            healthy += r["healthy"]

    merged["issues_detail"] = [issue_index[k] for k in order]
    merged["total"] = total
    merged["problematic"] = problematic
    if healthy:
        merged["healthy"] = healthy
    if len(cluster_names) == 1:
        merged["cluster_name"] = next(iter(cluster_names))
    elif len(cluster_names) > 1:
        merged.pop("cluster_name", None)
        merged["cluster_names"] = sorted(cluster_names)
    return merged


# 触发内置 renderer 的注册(import 子模块会在模块加载时 register_*)
from . import k8s  # noqa: E402, F401
from . import generic  # noqa: E402, F401


# ---------------------------------------------------------------------------
# LLM text 清理:strip phantom tool_call
# ---------------------------------------------------------------------------
#
# 现象:Gemini 2.0 Flash 等模型偶尔会走错格式,把"想调的工具"写成
#  <tool_call>call:name{args}</tool_call>
# 或
# <|tool_call|>call:name{args}<|tool_call|>
# 但 deepagent 不解析这些 XML 模式,所以这些"调用"根本没执行,只是 LLM 写进
# text 的幻觉。前端如果不处理,就会渲染成"已调用 5 个工具"那种假记录。
#
# 真实工具调用走 TOOL_CALL_START / TOOL_CALL_RESULT 事件通道,不在 text content 里,
# 所以这里 strip 不会影响真实工具调用,也不会影响 dispatch 出来的 report 事件。
#
# 实现注意:不要用 `re` 的 `<tool_call>.*?</tool_call>` —— Python 3.12+ 的 re 把 content 里
# 的 `{ns:1}` 这种 invalid quantifier 当成硬错误,整个 match 直接失败(实测)。
# 改用纯字符串扫描,绕过 re 的 quantifier 解析。
def strip_phantom_tool_calls(text: str) -> str:
    """把 LLM 幻觉的 XML 风格工具调用从 text 里抹掉,返回新字符串。

    支持两种 phantom call 格式:
    - <tool_call>call:name{args}<tool_call>
    - <|tool_call|>call:name{args}<|tool_call|>

    不影响:
    - 真实工具调用(走 TOOL_CALL_START 事件通道,本来就不在 text 里)
    - LLM 写的正常说明文字(包括含 `{` `}` 的 JSON 例子)
    - dispatch 的 report 事件(它们走独立 event,跟 text content 分开)
    - 孤立没闭合的 `<tool_call>` 标签(没法判断是不是工具调用,留着安全)
    """
    if not text:
        return text
    text = _strip_paired_tag(text, "<tool_call>", "</tool_call>")
    text = _strip_paired_tag(text, "<|tool_call|>", "<|tool_call|>")
    return text


def _strip_paired_tag(text: str, open_tag: str, close_tag: str) -> str:
    """找到所有 <open>...<close> 配对并整段抹掉,只删闭合完整对。

    不像 re.sub 用 `.*?` 会因为 content 含 `{` 而失败,这里纯用 str.find 扫描,
    对内容字符 0 要求(就算内容是 `{} () []` 也能正确处理)。

    LLM 实际输出有两种 phantom call 形态:
    - <tool_call>call:foo<|tool_call|></tool_call></tool_call></tool_call></tool_call></tool_call></tool_call></tool_call></tool_call></tool_call></tool_call><tool_call></tool_call>

    两种都吃。LLM 偶尔不写 /,所以找 close 时优先 proper close,fallback 到同 tag close。
    """
    if not text:
        return text
    out = []
    i = 0
    open_len = len(open_tag)
    while i < len(text):
        start = text.find(open_tag, i)
        if start < 0:
            out.append(text[i:])
            break
        out.append(text[i:start])
        # 优先找 proper close tag,有 / 的版本
        end = text.find(close_tag, start + open_len)
        if end < 0:
            # fallback:LLM 有时省略 /,close 跟 open 长得一样(<tool_call>X<tool_call>)。
            # 这种情况下找下一次同 tag,把它当 close 处理。
            end = text.find(open_tag, start + open_len)
            if end < 0:
                # 真的没闭合,留着不抹(无法判断意图)
                out.append(text[start:])
                break
            i = end + open_len
        else:
            i = end + len(close_tag)
    return "".join(out)
