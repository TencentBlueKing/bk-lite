"""PathRewritingBackend:在 execute 命令字符串里重写 ``/skills/...`` 与 ``/tmp/...`` 虚拟路径。

背景:
    deepagents ``LocalShellBackend`` 在 ``virtual_mode=True`` 时,只重写文件系统
    操作(read/write/ls/glob/grep)的路径,``execute`` 走 ``subprocess.run`` 把
    命令字符串直接传给宿主 shell,**不做任何路径重写**。
    这意味着当 LLM 写 ``python /skills/pdf/create_pdf.py`` 时:
      - cwd 是物理 sandbox_dir(如 ``/var/folders/.../run-XXX``),不是 ``/``
      - shell 找绝对路径 ``/skills/...`` 在文件系统根下不存在 → "No such file"
      - LLM 多次重试失败,最终 fallback 到自己直接调 Python 生成

    **L3 跨工具一致性问题:** 即便 ``/skills/...`` 通过 PathRewritingBackend 解决,
    LLM 还可能写 ``/tmp/<file>`` 这类沙箱外路径。deepagents virtual_mode 会把
    ``read_file('/tmp/...')`` 重写为 ``sandbox_dir/tmp/...``,但 ``execute`` 不会。
    两者路径域不一致 → "execute 写入成功,read_file 找不到"(同 sandbox 内)。

解决:
    ``PathRewritingBackend.execute`` / ``aexecute`` 接收 LLM 写的命令字符串,
    用正则把:
      - ``/skills/<path>`` → ``sandbox_dir/skills/<path>``
      - ``/tmp/<path>``   → ``sandbox_dir/tmp/<path>``(L3 扩展,与 virtual_mode 对齐)
    其他方法(read/write/ls/glob/grep)透传给底层 LocalShellBackend,后者已经
    正确处理 virtual_mode。

Phase 0 引入,Phase 1 NATS worker / 容器沙箱上线后可废弃。
"""
from __future__ import annotations

import asyncio
import re
import sys
import threading
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from deepagents.backends.protocol import SandboxBackendProtocol

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.common.tool_failure import unrecoverable_skill_result_hint

# 匹配 ``/skills/`` 开头、连续路径字符(不含 shell 特殊字符)的子串
_SKILLS_PATH_PATTERN = re.compile(r"/skills/[^\s'\"\|;&<>(){}\\`$?!*]*")
# L3 扩展:匹配 ``/tmp/`` 开头、连续路径字符(不含 shell 特殊字符)
_TMP_PATH_PATTERN = re.compile(r"/tmp/[^\s'\"\|;&<>(){}\\`$?!*]*")


def extract_skill_names_from_text(text: str, skills_root: str = "/skills") -> list[str]:
    """从命令或文件路径里抽出被访问的技能目录名(去重、保序)。"""
    if not text:
        return []
    root = skills_root.rstrip("/")
    # 统一成以 / 开头,便于匹配 ``/skills/<name>/...``
    haystack = text if text.startswith("/") else f"/{text}"
    pattern = re.compile(re.escape(root) + r"/([a-z0-9][a-z0-9-]{0,63})(?:/|$|\s|[\"'])")
    names: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(haystack):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


_EXPORT_HEAD_RE = re.compile(r"^(?:export|set)\s+", re.IGNORECASE)
_ENV_PAIR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=(?:'[^']*'|\"[^\"]*\"|[^\s;&|]+)\s*")
_CONNECTOR_RE = re.compile(r"^(?:&&|\|\||;)\s*")


def strip_leading_env_boilerplate(command: str) -> str:
    """去掉 LLM 常写的 ``export VAR=1 && python3 ...`` 前缀。

    技能包变量已由 PathRewritingBackend 注入,host(尤其 Windows)也跑不了 ``export``。
    赋值内容丢弃,不并入进程环境,避免 ``export PATH=...`` 覆盖沙箱 PATH。
    """
    stripped = str(command or "").strip()
    changed = True
    while changed and stripped:
        changed = False
        head = _EXPORT_HEAD_RE.match(stripped)
        if head:
            stripped = stripped[head.end() :]
            changed = True
        while True:
            pair = _ENV_PAIR_RE.match(stripped)
            if not pair:
                break
            stripped = stripped[pair.end() :]
            changed = True
        connector = _CONNECTOR_RE.match(stripped)
        if connector:
            stripped = stripped[connector.end() :]
            changed = True
    return stripped.strip()


_PYTHON_BASENAME_RE = re.compile(r"^python(\d+(\.\d+)*)?$", re.IGNORECASE)
_SKIP_EXEC_PREFIXES = frozenset({"env", "command", "sudo", "time", "nice", "nohup", "xargs"})


def _split_first_token(command: str) -> tuple[str, str]:
    """拆出第一个 shell token(支持单/双引号),返回 (token, rest)。"""
    text = str(command or "").lstrip()
    if not text:
        return "", ""
    if text[0] in {'"', "'"}:
        quote = text[0]
        end = text.find(quote, 1)
        if end > 0:
            return text[1:end], text[end + 1 :].lstrip()
    parts = text.split(None, 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def command_basename(token: str) -> str:
    """命令 token 的可执行文件名,兼容 /usr/bin/python3 与 Windows python.exe。"""
    name = (token or "").strip().strip("'\"").replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name


def is_python_interpreter(token: str) -> bool:
    return bool(_PYTHON_BASENAME_RE.match(command_basename(token)))


def _quote_executable(path: str) -> str:
    if any(ch in path for ch in (" ", "\t")):
        return '"' + path.replace('"', '\\"') + '"'
    return path


def normalize_sandbox_executable(command: str, *, python_executable: str | None = None) -> str:
    """把 python / python3 / /usr/bin/python3 归一成当前服务解释器。

    Windows 没有 ``/usr/bin/python3``;Linux 部署上模型又常写该绝对路径。
    两边都改成 ``sys.executable``,技能脚本才能用到同一套已装依赖(如 ldap3)。
    """
    python_executable = python_executable or sys.executable
    stripped = str(command or "").strip()
    if not stripped:
        return command
    prefix: list[str] = []
    token, rest = _split_first_token(stripped)
    while token:
        base = command_basename(token)
        if base.lower() in _SKIP_EXEC_PREFIXES or "=" in token:
            prefix.append(token if "=" in token else base)
            if not rest:
                return stripped
            token, rest = _split_first_token(rest)
            continue
        break
    if not token or not is_python_interpreter(token):
        return stripped
    parts = [*prefix, _quote_executable(python_executable)]
    if rest:
        parts.append(rest)
    return " ".join(parts)


_AD_SEARCH_SCRIPT_RE = re.compile(r"/skills/[^/\s]+/scripts/ad_search\.py\b")
_AD_SEARCH_FIELD_ALIAS_RE = re.compile(
    r"(?:^|\s)--(?:field|fields|attribute|attributes|attr)(?:=|\s+)(?P<val>[^\s]+)",
    re.IGNORECASE,
)
_AD_SEARCH_TOP_RE = re.compile(r"(?:^|\s)--top(?:=|\s+)(?P<val>\d+)\b", re.IGNORECASE)
_AD_SEARCH_FILTER_PREFIX_RE = re.compile(
    r"(?:^|\s)--filter[_-]?prefix(?:=|\s+)(?P<val>[^\s]+)",
    re.IGNORECASE,
)
_AD_SEARCH_BAD_FILTER_RE = re.compile(r"(?:^|\s)--filter(?:=|\s+)(?P<val>[^\s]+)", re.IGNORECASE)
_AD_SEARCH_TYPE_USERS_RE = re.compile(r"(?:^|\s)--type(?:=|\s+)users\b", re.IGNORECASE)
_AD_SEARCH_TYPE_GROUPS_RE = re.compile(r"(?:^|\s)--type(?:=|\s+)groups\b", re.IGNORECASE)
_AD_SEARCH_TYPE_COMPUTERS_RE = re.compile(r"(?:^|\s)--type(?:=|\s+)computers\b", re.IGNORECASE)
_AD_SEARCH_QUERY_FLAG_RE = re.compile(r"(?:^|\s)--query(?:\s|=)", re.IGNORECASE)
_AD_SEARCH_TYPE_FLAG_RE = re.compile(r"(?:^|\s)--type(?:\s|=)", re.IGNORECASE)
_AD_SEARCH_HELP_RE = re.compile(r"(?:^|\s)(?:--help|-h)(?=\s|$)", re.IGNORECASE)
_STDERR_MERGE_RE = re.compile(r"\s*(?:2>&1|1>&2|2>\s*/dev/null)\s*")
_PIPE_HEAD_TAIL_RE = re.compile(
    r"\s*\|\s*(?:head|tail)(?:\s+(?:-n|--lines)=?\s*\d+|\s+-\d+)?\b",
    re.IGNORECASE,
)
_AD_SEARCH_QUERY_VALUE_RE = re.compile(
    r"""(--query)(?:=|\s+)(?P<q>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s]+)""",
    re.IGNORECASE,
)
_AD_SEARCH_LDAP_ATTR_FILTER_RE = re.compile(
    r"^\(?\s*(?P<attr>sAMAccountName|cn|displayName|mail|givenName|sn|userPrincipalName)\s*=\s*(?P<val>[^)]*?)\s*\)?$",
    re.IGNORECASE,
)


def _unwrap_ad_search_query_value(raw: str) -> str:
    """把模型误塞进 --query 的 LDAP 片段还原成关键字。

    (sAMAccountName=SM_*) 与 sAMAccountName=SM_* 都变成 SM_*。
    含逗号的 DN（CN=xx,DC=yy）不拆。
    """
    val = str(raw or "").strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
        val = val[1:-1]
    val = val.rstrip("\\").strip().strip('"').strip("'").strip()
    match = _AD_SEARCH_LDAP_ATTR_FILTER_RE.match(val)
    if match:
        extracted = match.group("val").strip()
        if extracted and "," not in extracted and "=" not in extracted:
            return extracted
    return val


def _rewrite_ad_search_query_token(match: re.Match[str]) -> str:
    unwrapped = _unwrap_ad_search_query_value(match.group("q"))
    if not unwrapped:
        unwrapped = "*"
    if any(ch in unwrapped for ch in (" ", '"', "'", "*", "(", ")")):
        escaped = unwrapped.replace("\\", "\\\\").replace('"', '\\"')
        return f'{match.group(1)} "{escaped}"'
    return f"{match.group(1)} {unwrapped}"


def strip_skill_stdout_viewers(command: str) -> str:
    """去掉模型爱加的 2>&1 | head，把误挂到 head 后面的脚本参数留回原命令。"""
    rewritten = _STDERR_MERGE_RE.sub(" ", str(command or ""))
    rewritten = _PIPE_HEAD_TAIL_RE.sub(" ", rewritten)
    return " ".join(rewritten.split())


def normalize_ad_search_args(command: str) -> str:
    """纠正模型对 ad_search.py 的常见错参。

    - --field/--attr → --attrs
    - --top → --limit
    - --type users/groups/computers → 单数
    - 去掉 --help/-h（用法已在技能说明里，探 help 会被管道沙箱打成 126）
    - 去掉未声明的 --filter_prefix/--filter，并把前缀落到 --query
    - --query "(sAMAccountName=SM_*)" / --query "sAMAccountName=SM_*" → --query "SM_*"
    - 缺 --query 时补 "*"
    """
    stripped = str(command or "").strip()
    if not stripped or not _AD_SEARCH_SCRIPT_RE.search(stripped):
        return command
    rewritten = _AD_SEARCH_HELP_RE.sub(" ", stripped)
    prefix_match = _AD_SEARCH_FILTER_PREFIX_RE.search(rewritten)
    prefix_val = prefix_match.group("val").strip().strip('"').strip("'") if prefix_match else ""
    rewritten = _AD_SEARCH_FILTER_PREFIX_RE.sub(" ", rewritten)
    rewritten = _AD_SEARCH_BAD_FILTER_RE.sub(" ", rewritten)
    rewritten = _AD_SEARCH_TOP_RE.sub(lambda match: f" --limit {match.group('val')}", rewritten)
    rewritten = _AD_SEARCH_FIELD_ALIAS_RE.sub(lambda match: f" --attrs {match.group('val')}", rewritten)
    rewritten = _AD_SEARCH_TYPE_USERS_RE.sub(" --type user", rewritten)
    rewritten = _AD_SEARCH_TYPE_GROUPS_RE.sub(" --type group", rewritten)
    rewritten = _AD_SEARCH_TYPE_COMPUTERS_RE.sub(" --type computer", rewritten)
    rewritten = _AD_SEARCH_QUERY_VALUE_RE.sub(_rewrite_ad_search_query_token, rewritten)
    if prefix_val:
        query_match = _AD_SEARCH_QUERY_VALUE_RE.search(rewritten)
        current = _unwrap_ad_search_query_value(query_match.group("q")) if query_match else ""
        if not current or current == "*":
            prefix_query = prefix_val if prefix_val.endswith("*") else f"{prefix_val}*"
            if query_match:
                rewritten = _AD_SEARCH_QUERY_VALUE_RE.sub(
                    lambda _m, q=prefix_query: f'--query "{q}"',
                    rewritten,
                    count=1,
                )
            else:
                rewritten = f'{rewritten.rstrip()} --query "{prefix_query}"'
    if not _AD_SEARCH_QUERY_FLAG_RE.search(rewritten):
        rewritten = f'{rewritten.rstrip()} --query "*"'
    if not _AD_SEARCH_TYPE_FLAG_RE.search(rewritten):
        rewritten = f"{rewritten.rstrip()} --type user"
    return " ".join(rewritten.split())


def prepare_execute_command(command: str) -> str:
    """execute 入口规范化:剥 export 前缀、去掉 | head，再把解释器收到当前进程 Python。"""
    return normalize_ad_search_args(normalize_sandbox_executable(strip_skill_stdout_viewers(strip_leading_env_boilerplate(command))))


def _summarize_execute_output(text: str, exit_code: Any) -> dict[str, Any]:
    """把 execute 输出收成管理员排查摘要,避免成功时打印业务数据。"""
    process_ok = exit_code in (0, "0", None)
    stripped = (text or "").strip()
    if not stripped or stripped == "<no output>":
        return {
            "ok": bool(process_ok),
            "has_data": False,
            "detail": "empty_output" if process_ok else "failed_empty_output",
        }

    payload_text = stripped
    for marker in ("\n\nExit code:", "\nExit code:"):
        if marker in payload_text:
            payload_text = payload_text.split(marker, 1)[0].strip()

    # 去掉 LocalShellBackend 给 stderr 加的前缀,便于解析 JSON。
    if "[stderr]" in payload_text:
        payload_text = "\n".join(line[len("[stderr] ") :] if line.startswith("[stderr] ") else line for line in payload_text.splitlines()).strip()

    try:
        import json

        payload = json.loads(payload_text)
    except Exception:
        payload = None

    if isinstance(payload, dict) and "ok" in payload:
        ok = bool(payload.get("ok")) and process_ok
        data = payload.get("data")
        has_data = False
        detail = "ok" if ok else "skill_error"
        if isinstance(data, dict):
            entries = data.get("entries")
            count = data.get("count")
            if isinstance(entries, list):
                has_data = len(entries) > 0
                detail = f"count={len(entries)}" if has_data else "count=0"
            elif count is not None:
                try:
                    has_data = int(count) > 0
                    detail = f"count={int(count)}"
                except Exception:
                    has_data = bool(count)
                    detail = "has_count"
            elif data:
                has_data = True
                detail = "has_data"
        elif isinstance(data, list):
            has_data = len(data) > 0
            detail = f"list={len(data)}" if has_data else "list=0"
        elif data not in (None, "", {}, []):
            has_data = True
            detail = "has_data"
        if not ok:
            err = payload.get("error")
            if isinstance(err, dict) and err.get("code") is not None:
                detail = f"error_code={err.get('code')}"
            elif err:
                detail = "skill_error"
        return {"ok": ok, "has_data": has_data and ok, "detail": detail}

    # 非 JSON:成功只记有输出;失败给短摘要,不落大段正文。
    if process_ok:
        return {"ok": True, "has_data": True, "detail": f"output_chars={len(stripped)}"}
    preview = stripped.replace("\r", " ").replace("\n", " ")
    if len(preview) > 160:
        preview = preview[:160] + "..."
    return {"ok": False, "has_data": False, "detail": preview}


_SKILL_RESULT_HINT_MARKER = "[OPSPILOT_SKILL_RESULT]"
_SANDBOX_DENY_EXIT_CODE = 126


def _sandbox_deny_result(exc: PermissionError) -> Any:
    """把沙箱拒绝变成工具结果，避免 PermissionError 把整步 ainvoke 打爆并触发重规划。"""
    message = str(exc).strip() or "命令被沙箱拒绝"
    return SimpleNamespace(
        output=(
            f"{message}\n\n"
            f"{_SKILL_RESULT_HINT_MARKER} 该命令被沙箱拒绝。"
            "不要 --help，不要 2>&1 | head，不要重定向/管道。"
            "不要探测环境变量，不要 echo/$VAR，不要反复 read_file。"
            '直接再 execute：python3 /skills/ad-domain-ops/scripts/ad_search.py --query "*" --type user --limit 10 --attrs sAMAccountName'
        ),
        exit_code=_SANDBOX_DENY_EXIT_CODE,
        truncated=False,
    )


_SKILL_SCRIPT_CMD_RE = re.compile(r"/skills/[^/\s]+/scripts/[^/\s]+\.py")
_MISSING_SCRIPT_MARKERS = (
    "can't open file",
    "no such file or directory",
    "系统找不到指定的文件",
    "cannot find the file specified",
)


def list_skill_scripts_for_command(command: str, sandbox_dir: Path, skills_root: str = "/skills") -> list[str]:
    """列出命令命中的技能包 scripts/*.py（排除 _ 私有模块）。"""
    names = extract_skill_names_from_text(command or "", skills_root)
    if len(names) != 1:
        return []
    scripts_dir = Path(sandbox_dir) / "skills" / names[0] / "scripts"
    if not scripts_dir.is_dir():
        return []
    prefix = f"{skills_root.rstrip('/')}/{names[0]}/scripts"
    return sorted(f"{prefix}/{path.name}" for path in scripts_dir.glob("*.py") if path.is_file() and not path.name.startswith("_"))


def _is_missing_script_output(text: str) -> bool:
    blob = (text or "").casefold()
    return any(marker in blob for marker in _MISSING_SCRIPT_MARKERS)


def skill_execute_result_guidance(
    command: str,
    text: str,
    exit_code: Any,
    skills_root: str = "/skills",
    available_scripts: list[str] | None = None,
) -> str:
    """技能脚本 execute 后给模型的停手提示：成功(含空结果)不重试；凭据类失败禁止重试。"""
    if not _SKILL_SCRIPT_CMD_RE.search(command or ""):
        return ""
    summary = _summarize_execute_output(text or "", exit_code)
    if summary["ok"]:
        if summary["has_data"]:
            return (
                f"{_SKILL_RESULT_HINT_MARKER} 脚本已成功返回数据。"
                "这是最终结果：用一张简表直接回答用户（只含其要的字段），禁止再写第二份重复报告。"
                "禁止再次 execute 同类查询，禁止 read_file 扫技能包，禁止 python -c/env 探测变量。"
            )
        return f"{_SKILL_RESULT_HINT_MARKER} 脚本已成功结束且无匹配数据（空结果也是有效结论）。" "直接告知用户未查到，不要重试查询，不要 read_file，不要探测环境变量。"
    if _is_missing_script_output(text or ""):
        listed = available_scripts or []
        if listed:
            paths = "；".join(f"python3 {path}" for path in listed)
            return f"{_SKILL_RESULT_HINT_MARKER} 脚本不存在，不要 ls/glob/read_file。" f"请直接改跑：{paths}"
        return f"{_SKILL_RESULT_HINT_MARKER} 脚本不存在，不要 ls/glob/read_file。" "请改跑 `/skills/<包名>/scripts/` 下真实的 .py，不要发明文件名。"
    lowered = (text or "").casefold()
    if "arguments are required" in lowered or "unrecognized arguments" in lowered or "required: --query" in lowered:
        return (
            f"{_SKILL_RESULT_HINT_MARKER} 参数错误，禁止 read_file。"
            "立刻再 execute 一次，必须带 --query 和 --attrs（不要用 --field）："
            'python3 /skills/ad-domain-ops/scripts/ad_search.py --query "*" --type user --limit 10 --attrs sAMAccountName'
        )
    unrecoverable = unrecoverable_skill_result_hint(text or "")
    if unrecoverable:
        return unrecoverable
    return f"{_SKILL_RESULT_HINT_MARKER} 脚本失败。" "最多修正参数后重试 1 次；不要靠反复 read_file/探测变量绕过。" "仍失败则把错误原样反馈用户。"


def _with_skill_result_guidance(
    result: Any,
    command: str,
    skills_root: str = "/skills",
    available_scripts: list[str] | None = None,
) -> Any:
    """把停手提示追加到技能脚本 stdout，供模型下一轮看到。"""
    output = getattr(result, "output", None)
    if not isinstance(output, str):
        return result
    if _SKILL_RESULT_HINT_MARKER in output:
        return result
    hint = skill_execute_result_guidance(
        command,
        output,
        getattr(result, "exit_code", None),
        skills_root,
        available_scripts=available_scripts,
    )
    if not hint:
        return result
    new_output = f"{output.rstrip()}\n\n{hint}\n"
    try:
        result.output = new_output
        return result
    except Exception:
        return SimpleNamespace(
            output=new_output,
            exit_code=getattr(result, "exit_code", None),
            truncated=getattr(result, "truncated", False),
        )


def rewrite_skill_paths(command: str, sandbox_dir: Path, skills_root: str = "/skills") -> str:
    """把 command 字符串里以 ``/skills/`` 开头的路径 token 替换为物理路径。

    Args:
        command: LLM 写的 shell 命令字符串。
        sandbox_dir: 一次性沙箱物理根目录(传给 ``LocalShellBackend(root_dir=...)`` 的值)。
        skills_root: 虚拟根,默认 ``/skills``。

    Returns:
        替换后的命令字符串。其他 token(shell 控制符、参数值等)原样保留。
    """
    if not command:
        return command

    skills_prefix = skills_root.rstrip("/") + "/"
    if skills_prefix not in command:
        return command

    physical_prefix = str(sandbox_dir) + "/skills"
    rewritten = _SKILLS_PATH_PATTERN.sub(
        lambda match: physical_prefix + match.group(0)[len(skills_root) :],
        command,
    )
    if rewritten != command:
        logger.debug(
            "技能虚拟路径重写:\n  原: %s\n  新: %s",
            command,
            rewritten,
        )
    return rewritten


def rewrite_sandbox_paths(command: str, sandbox_dir: Path, skills_root: str = "/skills") -> str:
    """重写 execute 命令字符串中的多个沙箱外路径,让 execute 与 virtual_mode 路径域一致。

    L3 扩展:除 ``/skills/`` 外,也重写 ``/tmp/`` 让 execute 写入的临时文件能被
    read_file / ls / glob 在同一虚拟根看到。
    """
    if not command:
        return command

    rewritten = command
    skills_prefix = skills_root.rstrip("/") + "/"
    if skills_prefix in rewritten:
        physical_prefix = str(sandbox_dir) + "/skills"
        rewritten = _SKILLS_PATH_PATTERN.sub(
            lambda match: physical_prefix + match.group(0)[len(skills_root) :],
            rewritten,
        )

    if "/tmp/" in rewritten:
        physical_tmp = str(sandbox_dir) + "/tmp"
        rewritten = _TMP_PATH_PATTERN.sub(
            lambda match: physical_tmp + match.group(0)[len("/tmp") :],
            rewritten,
        )

    if rewritten != command:
        logger.debug(
            "沙箱虚拟路径重写:\n  原: %s\n  新: %s",
            command,
            rewritten,
        )
    return rewritten


class PathRewritingBackend(SandboxBackendProtocol):
    """包装 deepagents ``LocalShellBackend``(或任何 SandboxBackendProtocol),
    在 ``execute`` / ``aexecute`` 调用前重写 ``/skills/`` 虚拟路径。

    继承 ``SandboxBackendProtocol``(它已继承 BackendProtocol)是 deepagents 的硬要求:
      - ``_resolve_backend`` 用 ``isinstance(BackendProtocol)`` 校验,失败会把它当 callable 调而抛错
      - FilesystemMiddleware 用 ``SandboxBackendProtocol`` 校验决定是否注册 ``execute`` 工具,
        不继承则 LLM 拿不到 execute,只能 read_file/write_file

    其他方法(read/write/ls/glob/grep/upload_files/download_files/...)透传给底层
    backend,因为 deepagents ``LocalShellBackend`` 已经正确处理 virtual_mode。
    """

    def __init__(
        self,
        inner: Any,
        sandbox_dir: str | Path,
        skills_root: str = "/skills",
        on_skill_access: Callable[[Iterable[str]], None] | None = None,
        params_by_package: dict[str, dict[str, str]] | None = None,
        secret_values: list[str] | None = None,
    ) -> None:
        self._inner = inner
        self._sandbox_dir = Path(sandbox_dir)
        self._skills_root = skills_root
        # 渐进披露:仅在真正访问 /skills/<name>/... 时回调,用于按需装依赖。
        self._on_skill_access = on_skill_access
        self._params_by_package = params_by_package or {}
        self._secret_values = [value for value in (secret_values or []) if value]
        self._exec_lock = threading.Lock()
        self._fail_closed_hint = ""

    @property
    def id(self) -> str:
        """透传底层 backend 的 sandbox id(deepagents SandboxBackendProtocol 要求)。"""
        return getattr(self._inner, "id", f"path-rewriting-{id(self._inner)}")

    def _notify_skill_access(self, text: str) -> None:
        if not self._on_skill_access or not text:
            return
        names = extract_skill_names_from_text(text, self._skills_root)
        if names:
            self._on_skill_access(names)

    # ------------------------------------------------------------------
    # 重写的执行方法
    # ------------------------------------------------------------------

    def execute(self, command: str, *, timeout: int | None = None) -> Any:
        command = prepare_execute_command(command)
        self._notify_skill_access(command)
        rewritten = rewrite_sandbox_paths(command, self._sandbox_dir, self._skills_root)
        try:
            self._validate_command(rewritten, original=command)
        except PermissionError as exc:
            denied = _sandbox_deny_result(exc)
            self._log_execute_result(command, rewritten, denied)
            return denied
        self._ensure_sandbox_dirs(rewritten)
        with self._exec_lock:
            with self._scoped_env(command):
                result = self._inner.execute(rewritten, timeout=timeout)
        redacted = self._redact(result)
        scripts = list_skill_scripts_for_command(command, self._sandbox_dir, self._skills_root)
        guided = _with_skill_result_guidance(redacted, command, self._skills_root, available_scripts=scripts)
        # 摘要按原始脚本输出计（不含停手提示），避免 JSON 解析失败落到 output_chars
        self._log_execute_result(command, rewritten, redacted)
        return guided

    async def aexecute(self, command: str, *, timeout: int | None = None) -> Any:
        command = prepare_execute_command(command)
        self._notify_skill_access(command)
        rewritten = rewrite_sandbox_paths(command, self._sandbox_dir, self._skills_root)
        try:
            self._validate_command(rewritten, original=command)
        except PermissionError as exc:
            denied = _sandbox_deny_result(exc)
            self._log_execute_result(command, rewritten, denied)
            return denied
        self._ensure_sandbox_dirs(rewritten)
        await asyncio.to_thread(self._exec_lock.acquire)
        try:
            with self._scoped_env(command):
                result = await self._inner.aexecute(rewritten, timeout=timeout)
        finally:
            self._exec_lock.release()
        redacted = self._redact(result)
        scripts = list_skill_scripts_for_command(command, self._sandbox_dir, self._skills_root)
        guided = _with_skill_result_guidance(redacted, command, self._skills_root, available_scripts=scripts)
        self._log_execute_result(command, rewritten, redacted)
        return guided

    def _log_execute_result(self, command: str, rewritten: str, result: Any) -> None:
        """记录技能命令是否成功、是否有数据;成功路径不落具体业务内容。"""
        exit_code = getattr(result, "exit_code", None)
        output = getattr(result, "output", None)
        text = output if isinstance(output, str) else ""
        names = extract_skill_names_from_text(command, self._skills_root)
        summary = _summarize_execute_output(text, exit_code)
        logger.info(
            "技能沙箱 execute: skills=%s exit_code=%s ok=%s has_data=%s detail=%s cmd=%r",
            names or ["-"],
            exit_code,
            summary["ok"],
            summary["has_data"],
            summary["detail"],
            command[:200],
        )

    @contextmanager
    def _scoped_env(self, command: str):
        """按命令命中的技能包临时注入环境变量，退出后还原。"""
        inner = self._inner
        names = extract_skill_names_from_text(command, self._skills_root)
        original = dict(getattr(inner, "_env", None) or {}) if hasattr(inner, "_env") else None
        self._fail_closed_hint = ""
        try:
            if original is not None:
                if len(names) == 1:
                    package_env = self._params_by_package.get(names[0]) or {}
                    inner._env = {**original, **package_env}
                elif self._params_by_package:
                    if len(names) > 1:
                        self._fail_closed_hint = "请用 `/skills/<包名>/` 绝对路径调用对应技能包，以便注入该包参数。"
                    inner._env = original
            yield
        finally:
            if original is not None and hasattr(inner, "_env"):
                inner._env = original

    def _redact(self, result: Any) -> Any:
        output = getattr(result, "output", None)
        if not isinstance(output, str):
            if not self._fail_closed_hint:
                return result
            output = ""
        redacted = output
        for secret in sorted(self._secret_values, key=len, reverse=True):
            if secret:
                redacted = redacted.replace(secret, "***")
        if self._fail_closed_hint and self._fail_closed_hint not in redacted:
            redacted = f"{redacted.rstrip()}\n{self._fail_closed_hint}".lstrip()
        if redacted == output:
            return result
        if self._secret_values and any(secret and secret in output for secret in self._secret_values):
            logger.warning("技能包执行输出已脱敏加密变量")
        try:
            result.output = redacted
            return result
        except Exception:
            return SimpleNamespace(
                output=redacted,
                exit_code=getattr(result, "exit_code", None),
                truncated=getattr(result, "truncated", False),
            )

    def chmod(self, file_path: str, mode: int) -> None:
        """把虚拟路径落到沙箱物理文件后改权限。"""
        target = str(file_path or "")
        if not target.startswith("/"):
            target = f"/{target}"
        rewritten = rewrite_sandbox_paths(target, self._sandbox_dir, self._skills_root)
        path = Path(rewritten)
        if path.exists():
            path.chmod(mode)

    # 沙箱安全：可执行命令白名单(防止 LLM 误操作 host)。
    # 当前 sandbox 是 LocalShellBackend(virtual_mode),execute 直接跑 host shell,
    # 白名单是 P0 短期方案,Phase 1 NATS worker + Docker 沙箱是长期方案。
    # 安全约定:任何需要出网的命令(curl / wget / ssh / scp / rsync / nc)
    # 都不在白名单;对应的网络行为由工具函数显式提供(参考 SSRFValidator)。
    _ALLOWED_COMMANDS = frozenset(
        {
            # 文件/文本
            "ls",
            "cat",
            "head",
            "tail",
            "grep",
            "find",
            "wc",
            "echo",
            "pwd",
            "less",
            "more",
            "file",
            "stat",
            "diff",
            "sort",
            "uniq",
            "cut",
            "tr",
            "tee",
            "xargs",
            "tee",
            # 目录/文件操作(受限,见 _BLOCKED_PATTERNS 里的 rm 限制)
            "mkdir",
            "touch",
            "mv",
            "cp",
            "ln",
            "rm",
            "chmod",
            "chown",
            # 解压/归档
            "tar",
            "unzip",
            "zip",
            "gzip",
            "gunzip",
            "zcat",
            # Python / Node 工具链
            "python3",
            "python",
            "pip",
            "pip3",
            "uv",
            "uvx",
            "node",
            "npm",
            "npx",
            "node-gyp",
            # 浏览器 / 文档工具
            "agent-browser",
            "ab",
            "playwright",
            "chromium",
            "google-chrome",
            "pdftotext",
            "pdfinfo",
            "pdftoppm",
            "qpdf",
            "wkhtmltopdf",
            "pdf2htmlEX",
            "mutool",
            "pandoc",
            # k8s
            "kubectl",
            "helm",
            "kustomize",
            "kubectx",
            "kubens",
            # 网络工具(curl/wget/ssh 等)显式不在白名单。
            # 真正出网需求由业务工具(uvx / git / npm)或 SSRF 校验过的 fetch 工具处理。
            # 其他常用
            "git",
            "tar",
            "date",
            "echo",
            "true",
            "false",
            "test",
            "[",
            "which",
            "whereis",
            "type",
        }
    )
    # 黑名单正则(任何匹配都拒绝)
    # 收紧后比 L3 shell_tools 严:L3 只禁纯命令词,这层连管道 / 替换 / 展开一起拦。
    _BLOCKED_PATTERNS = (
        r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|-rf|-fr)\s+/\s*",  # rm -rf /
        r"\brm\s+-rf\s+/",
        r"\brm\s+-rf\s+~",  # rm -rf ~
        r"\brm\s+-rf\s+\$HOME",
        r"\brm\s+-rf\s+/\*",
        r"\bdd\s+",
        r"\bmkfs(\.\w+)?\s+",
        r"\bformat\s+",
        r"\bshutdown\s+",
        r"\breboot\s+",
        r"\bpoweroff\s+",
        r"\bhalt\s+",
        r"\bsudo\s+",
        r"\bsu\s+",
        r"\bssh\s+",  # 远程爆破
        r"\bscp\s+",
        r"\brsync\s+",
        r"\bnc\s+",  # netcat
        r"\|\s*sh\b",
        r"\|\s*bash\b",
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"\bsource\s+",
        r"\bchmod\s+(-R\s+)?777\b",
        r"\bchown\s+(-R\s+)?root\b",
        r"\buseradd\b",
        r"\buserdel\b",
        r"\bgroupadd\b",
        r"\bpasswd\s+",
        r"\bvisudo\b",
        r"\biptables\b",
        r"\bip\s+route\b",
        r"\bifconfig\b",
        r"\bmount\s+",
        r"\bumount\s+",
        r"\bswapon\s+",
        r"\bmkfs\.ext",
        r"\b>/dev/sd",
        r"\bcrontab\s+",
        r"\bat\s+now\b",  # at 立即执行
        # S4 防御:网络工具原命令被 _ALLOWED_COMMANDS 拿掉,这里再做一次
        # 黑名单兜底防止 LLM 通过管道 `cat|curl` / `echo|curl` 之类绕开
        r"\bcurl\b",
        r"\bwget\b",
        # M6 防御:路径展开绕开路径白名单(原正则只查 /xxx,LLM 写 ~/.ssh/id_rsa
        # / $HOME/.aws/credentials / `cat $(echo /etc/passwd)` 都不触发)
        r"\$\(",  # 命令替换 $(...) 任何出现都拦
        r"`[^`]*`",  # 反引号命令替换
        r"(?:^|\s)~/[^\s'\"]*",  # ~/path 任意字符(隐藏文件 / 任意位置展开)
        r"\$HOME\b",  # $HOME 环境变量展开
        r"\$\{[A-Z_][A-Z0-9_]*\}",  # ${HOME} ${PATH} 形式
        r"(?:^|\s|\|)\$[A-Z_][A-Z0-9_]*\b",  # $PATH $USER $SECRET 等无大括号形式
    )

    def _validate_command(self, rewritten_command: str, original: str) -> None:
        """命令安全校验:黑名单 + 白名单 + 路径沙箱。

        参数:
            rewritten_command: rewrite_sandbox_paths 重写后的命令(实际给 host 跑)
            original: LLM 原始写的命令(只含虚拟路径 /skills/ /tmp/)

        校验策略:
        - 黑名单查 original(防 LLM 用 curl|wget 等绕过白名单路径访问 host)
        - 首命令白名单查 rewritten 的首 token
        - 路径沙箱查 original(只允许 /skills/ /tmp/ 等虚拟根,不是物理 sandbox 路径)
        """
        # 1. 黑名单(防 LLM 用 sed/awk/python -c 等绕过)
        for pattern in self._BLOCKED_PATTERNS:
            if re.search(pattern, original) or re.search(pattern, rewritten_command):
                raise PermissionError(f"[sandbox] 命令被黑名单拦截(模式 {pattern!r}): {original!r}")

        # 1b. 禁止重定向/管道/串联:技能脚本 JSON 已在 stdout。
        # Windows 上 `> /tmp && cat` / heredoc 会连环失败,烧掉 model_calls。
        if re.search(r"(?:>>|<<|&&|\|\||(?<![\w])>(?!>)|(?<!\|)\|(?!\|))", original):
            raise PermissionError("[sandbox] 禁止重定向/管道/命令串联(> >> << | && ||)。" "技能脚本结果已在 stdout,直接解析 JSON 回答用户,不要写入 /tmp 再 cat。")
        # 2. 首命令白名单(查 rewritten 的首 token,去除路径前缀)
        stripped = rewritten_command.strip()
        if not stripped:
            raise PermissionError("[sandbox] 空命令")
        first_token, rest = _split_first_token(stripped)
        first_cmd = command_basename(first_token)
        tokens_rest = rest
        idx_guard = 0
        while first_cmd.lower() in _SKIP_EXEC_PREFIXES and tokens_rest and idx_guard < 16:
            idx_guard += 1
            first_token, tokens_rest = _split_first_token(tokens_rest)
            first_cmd = command_basename(first_token)
        while "=" in first_token and tokens_rest and idx_guard < 16:
            idx_guard += 1
            first_token, tokens_rest = _split_first_token(tokens_rest)
            first_cmd = command_basename(first_token)

        if first_cmd not in self._ALLOWED_COMMANDS and not is_python_interpreter(first_token):
            raise PermissionError(f"[sandbox] 命令 {first_cmd!r} 不在白名单。" f"允许的命令: {sorted(self._ALLOWED_COMMANDS)}")

        # 3. 路径沙箱(只查原 command,防止 LLM 访问 host 路径)
        # 允许: /skills/xxx, /tmp/xxx(虚拟根,会被重写到 sandbox_dir),
        # /dev/null, /dev/stdout, /dev/stderr, 纯环境变量赋值, 注释
        # M9 修复:删 /proc/self/(可读 host 进程 environ 拿 SECRET_KEY/DB_PASSWORD)、
        # /dev/fd/(可反推进程打开文件)、/dev/shm/(跨进程共享内存泄露)。整个 /proc
        # 前缀都不在白名单,堵死 /proc/cpuinfo /proc/meminfo /proc/net/tcp 等。
        allowed_path_prefixes = (
            "/skills/",
            "/tmp/",
            "/dev/null",
            "/dev/stdout",
            "/dev/stderr",
        )
        exe_token, _ = _split_first_token(original.strip())
        exe_unix = exe_token.strip("'\"").replace("\\", "/").rstrip("/")
        for match in re.finditer(r"(?:^|\s)(/[^\s'\"]+)", original):
            path = match.group(1)
            # 解释器自身的绝对路径(Linux 上的 /usr/bin/python3 或 venv/bin/python)
            # 不是 host 文件探测;脚本参数仍要过 /skills /tmp 白名单。
            if exe_unix and path.rstrip("/") == exe_unix and (is_python_interpreter(path) or command_basename(path) in self._ALLOWED_COMMANDS):
                continue
            if not any(path.startswith(p) for p in allowed_path_prefixes):
                raise PermissionError(f"[sandbox] 拒绝 host 路径 {path!r}。" f"只允许 {allowed_path_prefixes} 下的路径。")

        # 4. SSRF 兜底:扫命令字符串里所有 http(s):// URL,用 LLM 端点宽松模式
        # 校验(只挡云元数据,内网 / localhost 由 ops-system-mgmt 的内网白名单统一管)。
        # 即便 _ALLOWED_COMMANDS 拿掉了 curl/wget,LLM 还能走
        # `python3 -c "import urllib.request; ..."` 这类绕道,黑名单拦不住,这里兜底。
        # 严格 validate() 模式对 skill 沙箱太死板(企业 k8s、localhost 服务、内部 HTTP
        # 都会拒),用 validate_llm_endpoint 只挡云元数据,把"内网能不能走"留给系统
        # 白名单(apps/system_mgmt/viewsets/network_white_list_viewset.py + 缓存
        # apps/system_mgmt/utils/network_whitelist_cache.py)统一管。
        # deep_wrapper_node 是 async,但 _validate_command 是同步调用,
        # validate_llm_endpoint 内部用 socket.getaddrinfo 同步,host 解析在
        # 50ms 以内,可接受;Phase 1 容器化时再考虑包 to_thread。
        from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator

        for url in re.findall(r"https?://[^\s'\"|;&<>]+", original):
            try:
                SSRFValidator.validate_llm_endpoint(url)
            except SSRFError as e:
                raise PermissionError(f"[sandbox] 网络目标被 SSRF 拦截: {url!r}({e})") from e

    def _ensure_sandbox_dirs(self, rewritten_command: str) -> None:
        """提前 mkdir sandbox_dir 下可能被写到的子目录,避免 open() 因父目录不存在而失败。

        L3 修复:PathRewriting 重写 /tmp/<path> → sandbox_dir/tmp/<path> 后,
        sandbox_dir/tmp 可能不存在,Python ``open()`` 会 FileNotFoundError。
        这里从 rewritten_command 提取所有 ``<sandbox>/<sub>`` 前缀并 mkdir -p。
        """
        sandbox_str = str(self._sandbox_dir)
        for match in re.finditer(re.escape(sandbox_str) + r"/[^\s'\"\|;&<>()]+", rewritten_command):
            path = Path(match.group(0))
            # 只 mkdir 已有父级在 sandbox 下、当前还不存在的中间目录
            try:
                if not path.exists():
                    parent = path.parent
                    # 只往下 mkdir 到 sandbox 下,避免意外触碰 sandbox 外
                    if str(parent).startswith(sandbox_str) and not parent.exists():
                        parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                # 目录创建失败(如权限)交给后续 execute 自然报错,这里不阻断
                pass

    # ------------------------------------------------------------------
    # 透传给底层 backend(deepagents 已处理 virtual_mode)
    # ------------------------------------------------------------------

    def write(self, file_path: str, content: str) -> Any:
        # 不在 write 回调:建沙箱物化会 write SKILL.md,那不代表用户在用技能。
        return self._inner.write(file_path, content)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        # 读 SKILL.md / scripts 视为「开始使用该技能」,再装依赖。
        self._notify_skill_access(file_path)
        return self._inner.read(file_path, offset=offset, limit=limit)

    def ls(self, path: str) -> Any:
        return self._inner.ls(path)

    def glob(self, pattern: str, path: str | None = None) -> Any:
        return self._inner.glob(pattern, path=path)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._inner.grep(pattern, path=path, glob=glob, **kwargs)

    def ls_info(self, path: str) -> Any:
        return getattr(self._inner, "ls_info", lambda p: self._inner.ls(p))(path)

    def glob_info(self, pattern: str, path: str = "/") -> Any:
        return getattr(self._inner, "glob_info", lambda pat, p="/": self._inner.glob(pat, path=p))(pattern, path)

    def grep_raw(self, *args: Any, **kwargs: Any) -> Any:
        return getattr(self._inner, "grep_raw", lambda *a, **k: self._inner.grep(*a, **k))(*args, **kwargs)

    def upload_files(self, files: list[tuple[str, bytes]]) -> Any:
        return self._inner.upload_files(files)

    def download_files(self, paths: list[str]) -> Any:
        return self._inner.download_files(paths)
