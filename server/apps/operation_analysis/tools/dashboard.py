"""运营分析仪表盘工具。

只执行模型传入的检索条件和方案，通过 NATS 调用本应用的检索与校验接口。
不读取聊天文本或页面状态，也不在对话引擎里拼装方案。
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.rpc.base import AppClient, RpcClient

CONSTRUCTOR_PARAMS = []
_CALLER_IDENTITY_KEY = "caller_identity"


def _team_id(config: RunnableConfig | None) -> int | None:
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    identity = configurable.get(_CALLER_IDENTITY_KEY)
    if not isinstance(identity, dict):
        return None
    team_id = identity.get("team_id")
    return team_id if type(team_id) is int and team_id > 0 else None


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


@tool
def search_data_sources(requirements: list[dict], config: RunnableConfig) -> dict:
    """检索当前组织可用于搭建运营分析仪表盘的数据源。

    requirements 必须由调用方显式传入，每项至少提供 text；可补充 purpose（visualization 或
    parameter_options）、domain、metric、dimension、analysisType 和 chartType。
    工具不会读取聊天文本或页面状态，也不会改写 requirements。
    返回值里的 id 和 name 是唯一可用的数据源。没有候选时只说明没有匹配的数据源。
    """

    team_id = _team_id(config)
    if not team_id:
        return _fail("缺少调用者组织，无法检索数据源")
    if not isinstance(requirements, list) or not requirements:
        return _fail("requirements 必须是非空数组")
    try:
        result = _run_dashboard_rpc(
            "search_dashboard_data_sources",
            requirements=requirements,
            team_id=team_id,
        )
    except Exception as exc:
        return _fail(str(exc))
    if not isinstance(result, dict):
        return _fail("运营分析返回了无效的检索结果")
    return _ok(result)


@tool
def prepare_dashboard_proposal(
    proposal: dict,
    dashboard_id: str = "current",
    config: RunnableConfig = None,
) -> dict:
    """校验并补全运营分析仪表盘方案，返回可由页面直接应用的结构化结果。

    proposal 必须由调用方显式传入。校验通过时返回 pageAction，页面据此套到画布。
    校验未通过时不产生页面动作。工具不缓存方案，不读取聊天或页面状态。
    """

    team_id = _team_id(config)
    if not team_id:
        return _fail("缺少调用者组织，无法校验方案")
    if not isinstance(proposal, dict):
        return _fail("proposal 必须是对象")
    target_dashboard_id = str(dashboard_id or "current")
    try:
        result = _run_dashboard_rpc(
            "prepare_dashboard_proposal",
            proposal=proposal,
            team_id=team_id,
        )
    except Exception as exc:
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
    return _ok(result)


__all__ = [
    "CONSTRUCTOR_PARAMS",
    "search_data_sources",
    "prepare_dashboard_proposal",
]
