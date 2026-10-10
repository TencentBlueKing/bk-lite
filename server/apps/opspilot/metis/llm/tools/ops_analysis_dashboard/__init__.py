"""运营分析仪表盘工具。

只执行模型传入的检索条件和方案，通过 NATS 调用运营分析的检索与校验接口。
不读取聊天文本或页面状态，也不在对话引擎里拼装方案。
返回给模型的目录保留数据源支持的图表，以及字段的中文标题和说明。

说明：本模块 docstring 仅供工具目录展示；给大模型的调用约束写在各 @tool 中。
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.tools.rpc_identity import resolve_rpc_user_info
from apps.rpc.base import AppClient, RpcClient

CONSTRUCTOR_PARAMS = []
_PROPOSAL_SCHEMA_HINT = (
    'proposal 必须是 schemaVersion 为 "1.0" 的对象。'
    "组件放在 layout，每项用 valueConfig.chartType 和 valueConfig.dataSource；"
    "dataSource 只能填 search_data_sources 返回的数字 id。"
    "single 和 gauge 的 valueConfig.selectedFields 必须填写该数据源 fields 里的一个 name，不能为空。"
    "pie 填写 dimensionField 与 valueField，table 的 selectedFields 填写要展示的列。"
    "禁止使用 title、panels、chart_type、data_source_id。"
    "按这个结构改完再调用一次，不要原样重试。"
)
_SEARCH_HINT = (
    "一张盘要混用不同数据源。概览源最多两个 single 或 gauge，其余组件必须改用目录里 pie、topN、line、table 的其他 dataSource，不要把同一个源的每个数字都做成卡片。"
    "dataSource 只能填 candidates[].id，字段只能填 fields[].name，禁止编造数字或字段名。"
    "组件 name 用 fields[].title 的中文，description 用 fields[].description，不要把英文字段名当成标题。"
    "chartType 必须属于该数据源的 chart_type。一张盘要混用目录里实际支持的 single、gauge、line、bar、pie、table、topN，不要全部做成 single。"
    "single 和 gauge 的 selectedFields 必须包含一个字段，不能为空。pie 用 dimensionField 和 valueField。"
    "layout 是扁平数组，禁止 row、children。按这份目录调用一次 prepare_dashboard_proposal，页面会写入画布。"
    "不要反复检索，不要只写文字，不要让用户手工添加。"
)
_DATASOURCE_MISS_HINT = (
    "这些 dataSource 不存在。不要改试 1、2、10、20、100、200 或其他未列出的数字。"
    "只能使用 sources 里的 id，selectedFields 只能填该条 fields 里的名字。"
    "layout 必须是扁平组件数组，禁止 row 和 children。按 sources 改完再调用一次。"
)
_PROPOSAL_APPLIED_HINT = "方案已校验通过，已返回当前画布的应用动作。不要再次调用 prepare_dashboard_proposal。" "本轮搭盘步骤已完成，简短说明结果；画布草稿由用户点击保存后持久化。"
_PROPOSAL_PENDING_HINT = (
    "方案未应用。根据 pending 中的 index 定位 layout 组件并修正，禁止原样重试。"
    "datasource_not_found：使用本轮检索候选的数字 id；已有候选时不要让用户提供数据源。"
    "required_param：在 valueConfig.dataSourceParams 中补齐对应 name 的 value；"
    "只能使用已知值或声明的默认值，确实缺少业务参数时再向用户询问该参数。"
)


def _caller(config: RunnableConfig | None):
    try:
        return resolve_rpc_user_info(config, "运营分析")
    except ValueError as exc:
        return exc


def _rpc():
    if os.getenv("IS_LOCAL_RPC", "0") == "1":
        return AppClient("apps.operation_analysis.nats.nats")
    return RpcClient()


def _run_dashboard_rpc(method: str, **kwargs):
    from apps.operation_analysis.nats.auth import sign_dashboard_request

    kwargs["_internal_auth"] = sign_dashboard_request(kwargs.get("team_id"), method)

    def _call():
        return _rpc().run(method, **kwargs)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _call()
    # RpcClient.run 内部是 asyncio.run。对话节点已经在事件循环里，直接调用会失败。
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_call).result()


def _ok(data) -> dict:
    return {"success": True, "data": data}


def _fail(message: str) -> dict:
    return {"success": False, "error": message}


def _log_rpc_failure(method: str, exc: BaseException) -> None:
    """记录 RPC 失败。异常正文可能含响应，日志只留类型和原始调用栈。"""
    logger.error(
        "event=dashboard_tool_rpc_failed method=%s failed_stage=%s error_type=%s",
        method,
        "rpc",
        type(exc).__name__,
        exc_info=(RuntimeError, RuntimeError("dashboard tool rpc failed"), exc.__traceback__),
    )


def _reject_non_object_list(value, message: str):
    if not isinstance(value, list) or not value or any(not isinstance(item, dict) for item in value):
        return _fail(message)
    return None


def _public_field(field) -> dict | None:
    if isinstance(field, str) and field:
        return {"name": field}
    if not isinstance(field, dict) or not field.get("name"):
        return None
    item = {"name": str(field["name"])}
    title = str(field.get("title") or "").strip()
    description = str(field.get("description") or field.get("desc") or "").strip()
    if title and title != item["name"]:
        item["title"] = title
    if description and description not in {item["name"], item.get("title")}:
        item["description"] = description
    if field.get("type"):
        item["type"] = field["type"]
    return item


def _public_candidate(candidate: dict) -> dict:
    fields = []
    for field in candidate.get("fields") or []:
        public = _public_field(field)
        if public:
            fields.append(public)
    item = {
        "id": candidate.get("id"),
        "name": candidate.get("name") or "",
        "chart_type": list(candidate.get("chart_type") or []),
        "fields": fields,
    }
    tags = [str(tag) for tag in (candidate.get("tags") or []) if tag not in (None, "")]
    if tags:
        item["tags"] = tags
    desc = str(candidate.get("desc") or "").strip()
    if desc:
        item["desc"] = desc
    params = []
    for param in candidate.get("params") or []:
        if not isinstance(param, dict) or not param.get("name"):
            continue
        public = {
            "name": str(param["name"]),
            "alias": str(param.get("alias_name") or param.get("alias") or param["name"]),
            "type": str(param.get("type") or "string"),
            "filterType": str(param.get("filterType") or "params"),
        }
        if param.get("default") not in (None, ""):
            public["default"] = param.get("default")
        params.append(public)
    if params:
        item["params"] = params
    return item


def _public_search_result(result: dict) -> dict:
    raw = [item for item in (result.get("candidates") or []) if isinstance(item, dict) and item.get("id") is not None]
    public = [_public_candidate(item) for item in raw]
    ids = ",".join(str(item.get("id")) for item in public)
    payload = _ok({"candidates": public})
    hint = f"只能使用这些 id：{ids}。" + _SEARCH_HINT if ids else _SEARCH_HINT
    payload["_next_step_hint"] = hint
    return payload


def _flatten_layout(proposal: dict) -> dict:
    layout = proposal.get("layout")
    if not isinstance(layout, list):
        return proposal
    flat: list = []

    def visit(items):
        for item in items:
            if not isinstance(item, dict):
                flat.append(item)
                continue
            children = item.get("children")
            config = item.get("valueConfig") if isinstance(item.get("valueConfig"), dict) else {}
            if isinstance(children, list) and children and not config.get("chartType") and not config.get("sceneWidgetType"):
                visit(children)
                continue
            flat.append(item)

    visit(layout)
    if flat == layout:
        return proposal
    return {**proposal, "layout": flat}


def _names(values) -> str:
    return ",".join(str(item) for item in values or [] if item not in (None, ""))


def _unknown_field_hint(result: dict) -> str:
    lines = []
    for item in result.get("pending") or []:
        if not isinstance(item, dict):
            continue
        allowed = _names(item.get("allowedFields"))
        rejected = _names(item.get("fields"))
        if allowed:
            lines.append(f"组件 {item.get('index')} 不能用 {rejected}，只能用 {allowed}")
    if not lines:
        return "字段名不存在。selectedFields 只能填 pending.allowedFields，不要自造中文别名，也不要改 dataSource。"
    return "字段名不存在。" + "；".join(lines) + "。selectedFields 改成这些英文名字再调用一次，不要自造 CI数量 这类别名。"


def _model_failure(result: dict) -> dict:
    slim = {key: result[key] for key in ("ok", "reason", "pending", "sources") if key in result}
    return slim or result


@tool
def search_data_sources(requirements: list[dict], config: RunnableConfig) -> dict:
    """检索当前组织可用于搭建运营分析仪表盘的数据源。

    返回的 candidates[].id 是唯一合法的 dataSource，fields[].name 是唯一合法字段名，禁止编造。
    fields[].title 是组件中文标题，fields[].description 是组件说明，不要把英文字段名写成标题。
    chart_type 是该数据源允许的图表。一张盘要混用目录里实际支持的类型。概览源最多两个 single 或 gauge，其余组件改用 pie、topN、line、table 的其他数据源，不要把同一个源的每个数字都做成卡片。
    layout 必须是扁平组件数组，禁止 row、children。
    检索后的下一步只能调用 prepare_dashboard_proposal。禁止插入 request_user_choice，不要让用户挑选指标或确认后再添加。
    requirements 必须由调用方显式传入，每项至少提供 text；可补充 purpose（visualization 或
    parameter_options）、domain、metric、dimension、analysisType 和 chartType。
    工具不会读取聊天文本或页面状态，也不会改写 requirements。
    single 或 gauge 的 selectedFields 必须包含一个字段名，不能为空。
    pie 填写 dimensionField 与 valueField。同一数据源的多个数字要选不同字段。
    没有候选时只说明没有匹配的数据源。
    """

    caller = _caller(config)
    if isinstance(caller, ValueError):
        return _fail(str(caller))
    invalid = _reject_non_object_list(requirements, "requirements 必须是非空对象数组")
    if invalid:
        return invalid
    try:
        result = _run_dashboard_rpc(
            "search_dashboard_data_sources",
            requirements=requirements,
            team_id=caller["team"],
            user_info=caller,
        )
    except Exception as exc:
        _log_rpc_failure("search_dashboard_data_sources", exc)
        return _fail(str(exc))
    if not isinstance(result, dict):
        return _fail("运营分析返回了无效的检索结果")
    if result.get("candidates"):
        # 执行上下文只保留结果开头。目录必须完整落在这个窗口里，否则模型会改去猜 id。
        return _public_search_result(result)
    return _ok(result)


@tool
def prepare_dashboard_proposal(
    proposal: dict,
    dashboard_id: str = "current",
    config: RunnableConfig = None,
) -> dict:
    """校验并应用运营分析仪表盘方案。通过后页面直接写入当前画布，不要再次调用。

    proposal 必须由调用方显式传入，且 schemaVersion 固定为 "1.0"。
    layout 是扁平组件数组，禁止 row、children、title、panels、chart_type、data_source_id。
    dataSource 只能填 search_data_sources 返回的数字 id，禁止编造其他数字。
    chartType 必须属于该数据源的 chart_type。
    组件 name 用字段中文 title，description 用字段说明，不要用英文字段名。
    chartType 从该数据源 chart_type 里选。概览源最多两个 single 或 gauge，其余组件改用 pie、topN、line、table 的其他数据源，不要把同一个源的每个数字都做成卡片。
    single 和 gauge 的 selectedFields 必须填该数据源 fields 里的一个 name，不能为空。
    pie 填写 dimensionField 与 valueField。table 的 selectedFields 填写要展示的列。
    layout 必须显式传入；只有用户要求清空组件时才传空数组。
    dashboard_id 用 current。目录节点 id（如 dashboard_426）表示同一张当前盘。
    用户要求搭建或应用时必须调用本工具，不能只输出文字方案、让用户手工添加，或调用 request_user_choice 确认。
    校验通过时返回 pageAction，页面写入可撤销的编辑草稿。保存由用户点击页面保存完成。
    校验未通过时不产生页面动作。按 _next_step_hint、sources 或 allowedFields 改一次，禁止换一组 id 再试。
    工具不缓存方案，不读取聊天或页面状态。
    """

    caller = _caller(config)
    if isinstance(caller, ValueError):
        return _fail(str(caller))
    if not isinstance(proposal, dict):
        return _fail("proposal 必须是对象")
    proposal = _flatten_layout(proposal)
    target_dashboard_id = str(dashboard_id or "current")
    try:
        result = _run_dashboard_rpc(
            "prepare_dashboard_proposal",
            proposal=proposal,
            team_id=caller["team"],
            user_info=caller,
        )
    except Exception as exc:
        _log_rpc_failure("prepare_dashboard_proposal", exc)
        return _fail(str(exc))
    if not isinstance(result, dict):
        return _fail("运营分析返回了无效的校验结果")

    prepared = result.get("proposal")
    if result.get("ok") is True and isinstance(prepared, dict):
        result = {
            **result,
            "pageAction": {
                "name": "dashboard_config_apply",
                "value": {
                    "dashboardId": target_dashboard_id,
                    "proposal": prepared,
                },
            },
        }
    hint = None
    if result.get("reason") in {"schema", "layout"}:
        hint = _PROPOSAL_SCHEMA_HINT
    elif result.get("reason") == "pending" and any(
        isinstance(item, dict) and item.get("reason") == "datasource_not_found" for item in (result.get("pending") or [])
    ):
        hint = _DATASOURCE_MISS_HINT
    elif result.get("reason") == "pending":
        hint = _PROPOSAL_PENDING_HINT
    elif result.get("reason") == "chart_type_mismatch":
        hint = "chartType 不在 pending.allowedChartTypes 里。改成允许的类型，字段只用 pending.fields，不要换一个没列出的 id。"
    elif result.get("reason") == "unknown_field":
        hint = _unknown_field_hint(result)
    elif result.get("reason") == "chart_type":
        hint = _PROPOSAL_SCHEMA_HINT + "layout 每一项都要有 valueConfig.chartType，不要用 row 或 children 包一层。"
    elif result.get("ok") is False:
        hint = "方案未应用。根据 reason 和 pending 修正对应组件后再调用，禁止原样重试，也不要换成未检索到的 id。"
    elif result.get("ok") is True and isinstance(result.get("pageAction"), dict):
        hint = _PROPOSAL_APPLIED_HINT
    data = result if result.get("ok") is True else _model_failure(result)
    # 成功结果保留完整 pageAction 给页面。失败结果去掉回显的 proposal，把 sources 留在截断窗口里。
    return {"_next_step_hint": hint, **_ok(data)} if hint else _ok(data)


__all__ = [
    "CONSTRUCTOR_PARAMS",
    "search_data_sources",
    "prepare_dashboard_proposal",
]
