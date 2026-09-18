"""工具与技能脚本失败分型。无 langchain 依赖，技能执行器与规划器共用。"""

from __future__ import annotations

import json
import re
from typing import Any

POLICY_RESULT_MARKER = "[OPSPILOT_POLICY]"
SKILL_RESULT_MARKER = "[OPSPILOT_SKILL_RESULT]"
SKILL_STOP_MARKER = "[OPSPILOT_SKILL_STOP]"

_POLICY_GUIDANCE_MARKERS = (
    POLICY_RESULT_MARKER,
    SKILL_STOP_MARKER,
    SKILL_RESULT_MARKER,
    "当前不可用。不要用 read_file",
    "不要用 read_file/ls/grep 扫技能包",
)

# 扫包拒绝、成功/改命令提示：正文不拿去分型。脚本失败（含 401）要分型，故不含「脚本失败」。
_CONTROL_GUIDANCE_MARKERS = (
    POLICY_RESULT_MARKER,
    SKILL_STOP_MARKER,
    "当前不可用。不要用 read_file",
    "不要用 read_file/ls/grep 扫技能包",
)
_SKILL_CONTROL_RESULT_HINTS = (
    "已成功返回数据",
    "已成功结束且无匹配数据",
    "脚本不存在",
    "参数错误",
    "被沙箱拒绝",
    "禁止 read_file/ls/grep 扫技能包",
    "不要再用 cat/ls/grep/echo 探测",
)


def is_policy_guidance(content: Any) -> bool:
    """可见性拦截 / 停手提示：不是工具硬失败，不应触发外层重规划。"""
    text = str(content or "")
    if not text:
        return False
    return any(marker in text for marker in _POLICY_GUIDANCE_MARKERS)


def is_control_guidance(content: Any) -> bool:
    """扫包/停手/成功/改命令：不算凭据类失败。脚本失败正文仍要分型。"""
    text = str(content or "")
    if not text:
        return False
    if any(marker in text for marker in _CONTROL_GUIDANCE_MARKERS):
        return True
    if SKILL_RESULT_MARKER in text and any(hint in text for hint in _SKILL_CONTROL_RESULT_HINTS):
        return True
    return False


def is_skill_policy_guidance(content: Any) -> bool:
    """兼容旧名。"""
    return is_policy_guidance(content)


def is_tool_result_failure(content: Any, status: str = "") -> bool:
    """识别工具硬失败与 JSON 软失败（如 {"error": "..."}）。"""
    if is_policy_guidance(content):
        return False
    if str(status or "").lower() == "error":
        return True

    if content is None:
        return False

    if isinstance(content, dict):
        err = content.get("error")
        return bool(err not in (None, "", [], {}))

    text = str(content).strip()
    if not text:
        return False

    lowered = text.casefold()
    if lowered.startswith(("error", "exception")):
        return True

    if text[0] not in "{[":
        return False

    try:
        payload = json.loads(text)
    except Exception:
        return False

    if isinstance(payload, dict):
        err = payload.get("error")
        return bool(err not in (None, "", [], {}))
    return False


TOOL_FAILURE_AUTHN = "authn"
TOOL_FAILURE_AUTHZ = "authz"
TOOL_FAILURE_CONFIG = "config"
TOOL_FAILURE_INTERNAL = "internal"
TOOL_FAILURE_OTHER = "other"

_AUTHN_FAILURE_RE = re.compile(
    r"\b401\b|unauthorized|invalid[_\s-]token|\binvalid token\b|"
    r"expired[_\s-]token|\bexpired token\b|"
    r"invalid[_\s-]?credentials|bad[_\s-]?credentials|invalid certificate|"
    r"certificate expired|x509|authentication failed|鉴权失败",
    re.I,
)
_AUTHZ_FAILURE_RE = re.compile(
    r"\b403\b|forbidden|permission denied|access denied|没有权限|未授权",
    re.I,
)
_INTERNAL_FAILURE_RE = re.compile(
    r"AttributeError|TypeError|NameError|ImportError|ModuleNotFoundError|" r"SyntaxError|IndentationError|Traceback \(most recent call last\)",
)
_CONFIG_FAILURE_RE = re.compile(
    r"connection_failed|无法加载\s*kubernetes|请检查 kubeconfig|api server|"
    r"CredentialValidationError|(?:host|url) is required|"
    r"No \w+ instances configured|"
    r"decrypt failed|Failed to decrypt|InvalidToken|解密失败",
    re.I,
)


def _tool_failure_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, dict):
        parts = [content.get("error"), content.get("message"), content.get("suggestion")]
        dumped = json.dumps(content, ensure_ascii=False)
        return " ".join(str(part) for part in (*parts, dumped) if part)
    return str(content)


def classify_tool_failure_kind(content: Any, status: str = "") -> str:
    """把工具/技能脚本失败分成凭据/权限/配置/其它，供外层决定是否重规划。"""
    if is_control_guidance(content):
        return TOOL_FAILURE_OTHER
    text = _tool_failure_text(content)
    if _AUTHN_FAILURE_RE.search(text):
        return TOOL_FAILURE_AUTHN
    if _AUTHZ_FAILURE_RE.search(text):
        return TOOL_FAILURE_AUTHZ
    # 应用 previous 日志常带 Traceback；只有工具硬失败才算实现异常。
    if _INTERNAL_FAILURE_RE.search(text) and is_tool_result_failure(content, status):
        return TOOL_FAILURE_INTERNAL
    if _CONFIG_FAILURE_RE.search(text):
        return TOOL_FAILURE_CONFIG
    return TOOL_FAILURE_OTHER


def is_non_replanable_tool_failure(content: Any, status: str = "") -> bool:
    """凭据、权限、连接配置或实现异常再规划也不会变，应直接收口告诉用户。

    技能脚本失败常带 [OPSPILOT_SKILL_RESULT]，仍按同一套分型；扫包/成功/改命令提示除外。
    """
    if is_control_guidance(content):
        return False
    return classify_tool_failure_kind(content, status) in {
        TOOL_FAILURE_AUTHN,
        TOOL_FAILURE_AUTHZ,
        TOOL_FAILURE_CONFIG,
        TOOL_FAILURE_INTERNAL,
    }


UNRECOVERABLE_SKILL_RESULT_HINT = f"{SKILL_RESULT_MARKER} 连接、凭据、权限或脚本实现失败，禁止重试。" "把错误原样告诉用户并结束，不要改参，不要 read_file。"

MISSING_PARAMS_CHOICE_HINT = (
    "工具因缺少必要参数失败，这不是系统故障。" "必须立即调用 request_user_choice，用选项让用户补全缺失信息" "（查询对象、时间范围、看 CPU/内存/磁盘还是告警等）。" "禁止编造 uvx、python -m、白名单命令或其他替代排查方案，禁止换其他工具盲猜。"
)

# 查询缺参：走选择器。namespace 仍留给 K8s 反查重规划；host/url 走配置失败。
_MISSING_PARAMS_RE = re.compile(
    r"missing parameters|missing required|field required|"
    r"缺少必要(?:的)?(?:检索)?参数|"
    r"\b(?:monitor_obj_id|metric|instance_id|instance_ids|search|model_id|"
    r"start|end|query|alert_id)\s+is required\b",
    re.I,
)

_SUBSTITUTE_PLAN_MARKERS = ("uvx", "白名单内的命令", "替代执行方案", "python -m")


def is_missing_tool_params_failure(content: Any, status: str = "") -> bool:
    """工具/校验因查询必填参数缺失失败，应问用户而不是换工具或编 CLI。"""
    if is_non_replanable_tool_failure(content, status):
        return False
    text = _tool_failure_text(content)
    if not text:
        return False
    return bool(_MISSING_PARAMS_RE.search(text))


def wrap_tool_error_payload(message: str) -> dict[str, Any]:
    payload = {"success": False, "error": message}
    if is_missing_tool_params_failure(message):
        payload["_next_step_hint"] = MISSING_PARAMS_CHOICE_HINT
    return payload


def _message_is_user_choice(message: Any) -> bool:
    name = str(getattr(message, "name", "") or "")
    if name == "request_user_choice":
        return True
    for call in getattr(message, "tool_calls", None) or []:
        call_name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
        if str(call_name or "") == "request_user_choice":
            return True
    return False


def _message_is_tool_result(message: Any) -> bool:
    if getattr(message, "type", "") == "tool":
        return True
    return type(message).__name__ == "ToolMessage"


def step_has_unasked_missing_params(messages: list[Any] | tuple[Any, ...] | None) -> bool:
    """步骤里出现查询缺参，且尚未调用 request_user_choice。"""
    saw_missing = False
    saw_choice = False
    for message in messages or ():
        if _message_is_user_choice(message):
            saw_choice = True
        if not _message_is_tool_result(message):
            continue
        status = str(getattr(message, "status", "") or "")
        if is_missing_tool_params_failure(getattr(message, "content", None), status):
            saw_missing = True
    return saw_missing and not saw_choice


def is_substitute_plan_message(message: Any) -> bool:
    """模型在缺参后编造的 uvx/白名单替代方案，不应展示给用户。"""
    msg_type = str(getattr(message, "type", "") or "")
    cls_name = type(message).__name__
    if msg_type not in {"ai", "AIMessage"} and cls_name not in {"AIMessage", "AIMessageChunk"}:
        return False
    text = str(getattr(message, "content", "") or "").casefold()
    if not text:
        return False
    return any(marker.casefold() in text for marker in _SUBSTITUTE_PLAN_MARKERS)


def tool_graph_failure_user_prompt(exc: BaseException) -> str:
    detail = f"{type(exc).__name__}: {str(exc)[:800]}"
    if is_missing_tool_params_failure(str(exc)):
        return f"上一轮工具调用因缺少必要参数失败({detail})。{MISSING_PARAMS_CHOICE_HINT}"
    return f"上一轮工具执行失败(异常 {detail}),请用中文告诉用户失败原因," "并给出可执行的替代方案(例如改用白名单内的命令 uvx / python -m," "或换其他可用工具)。不要再尝试调同样的命令。"


def tool_graph_failure_plain_text(exc: BaseException) -> str:
    detail = f"{type(exc).__name__}: {str(exc)[:400]}"
    if is_missing_tool_params_failure(str(exc)):
        return "查询缺少必要参数。请补充查询对象、时间范围或要查看的指标后重试。"
    return f"工具执行失败:{detail}\n请尝试改用白名单内的等效命令(uvx / python -m 等)或换其他工具。"


def unrecoverable_skill_result_hint(text: str) -> str | None:
    """技能脚本 stdout 若是凭据/配置/实现异常，返回禁止重试提示。"""
    if is_non_replanable_tool_failure(text or ""):
        return UNRECOVERABLE_SKILL_RESULT_HINT
    return None
