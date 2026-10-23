"""执行前把平台内置变量写进脚本副本。

脚本库保存的原文不改。只有脚本按对应语言引用了变量名时才插入赋值，
值一律作为字面量，避免用户中文名里的引号或换行变成命令。
"""

import json
import re
import shlex

from django.db import DatabaseError

from apps.job_mgmt.constants import ScriptType

BUILTIN_SCRIPT_VAR_USER = "BK_JOB_USER"
BUILTIN_SCRIPT_VAR_USER_NAME = "BK_JOB_USER_NAME"
BUILTIN_SCRIPT_VAR_JOB_ID = "BK_JOB_ID"

BUILTIN_SCRIPT_VAR_NAMES = (
    BUILTIN_SCRIPT_VAR_USER,
    BUILTIN_SCRIPT_VAR_USER_NAME,
    BUILTIN_SCRIPT_VAR_JOB_ID,
)

_SHELL_PATTERNS = {
    BUILTIN_SCRIPT_VAR_USER_NAME: re.compile(r"\$\{BK_JOB_USER_NAME\b|\$BK_JOB_USER_NAME\b"),
    BUILTIN_SCRIPT_VAR_USER: re.compile(r"\$\{BK_JOB_USER\b|\$BK_JOB_USER\b"),
    BUILTIN_SCRIPT_VAR_JOB_ID: re.compile(r"\$\{BK_JOB_ID\b|\$BK_JOB_ID\b"),
}
_PYTHON_PATTERNS = {name: re.compile(rf"(?<!\$)\b{name}\b") for name in BUILTIN_SCRIPT_VAR_NAMES}
_POWERSHELL_PATTERNS = _SHELL_PATTERNS
_BAT_PATTERNS = {name: re.compile(rf"%{name}%") for name in BUILTIN_SCRIPT_VAR_NAMES}

_PATTERNS_BY_TYPE = {
    ScriptType.SHELL: _SHELL_PATTERNS,
    ScriptType.PYTHON: _PYTHON_PATTERNS,
    ScriptType.POWERSHELL: _POWERSHELL_PATTERNS,
    ScriptType.BAT: _BAT_PATTERNS,
}


def referenced_builtin_script_vars(script_content: str, script_type: str) -> tuple[str, ...]:
    """按脚本类型返回被引用的内置变量，顺序固定。"""
    patterns = _PATTERNS_BY_TYPE.get(script_type)
    if not patterns or not script_content:
        return ()
    return tuple(name for name in BUILTIN_SCRIPT_VAR_NAMES if patterns[name].search(script_content))


def resolve_builtin_script_var_values(execution) -> dict[str, str]:
    """从执行记录取用户名、中文名和作业 ID。查不到中文名时用空字符串。"""
    username = str(execution.executor_user or execution.created_by or "")
    domain = str(execution.domain or "")
    return {
        BUILTIN_SCRIPT_VAR_USER: username,
        BUILTIN_SCRIPT_VAR_USER_NAME: _lookup_display_name(username, domain),
        BUILTIN_SCRIPT_VAR_JOB_ID: str(execution.id),
    }


def render_builtin_script_vars(script_content: str, script_type: str, values: dict[str, str]) -> str:
    """返回插入赋值后的脚本副本。未引用变量时原样返回。"""
    content = script_content or ""
    referenced = referenced_builtin_script_vars(content, script_type)
    if not referenced:
        return content
    lines = [_assign(script_type, name, values.get(name, "")) for name in referenced]
    preamble = "\n".join(lines) + "\n"
    return _insert_after_shebang(content, preamble)


def _lookup_display_name(username: str, domain: str) -> str:
    if not username or not domain:
        return ""
    from apps.system_mgmt.models.user import User

    try:
        row = User.objects.filter(username=username, domain=domain).only("display_name").first()
    except DatabaseError:
        return ""
    if row is None or not row.display_name:
        return ""
    return str(row.display_name)


def _assign(script_type: str, name: str, value: str) -> str:
    if script_type == ScriptType.SHELL:
        return f"{name}={shlex.quote(_strip_nul(value))}"
    if script_type == ScriptType.PYTHON:
        return f"{name} = {json.dumps(_strip_nul(value), ensure_ascii=False)}"
    if script_type == ScriptType.POWERSHELL:
        literal = _strip_nul(value).replace("'", "''")
        return f"${name} = '{literal}'"
    if script_type == ScriptType.BAT:
        return _bat_assign(name, value)
    return ""


def _bat_assign(name: str, value: str) -> str:
    """生成 bat 文件里的 set。cmd.exe /c 脚本文件会展开 %，所以百分号写成 %%。"""
    cleaned = _strip_nul(value).replace("\r", " ").replace("\n", " ")
    cleaned = cleaned.replace("%", "%%").replace('"', "'")
    if cleaned.endswith("\\"):
        cleaned += "\\"
    return f'set "{name}={cleaned}"'


def _strip_nul(value: str) -> str:
    return str(value).replace("\x00", "")


def _insert_after_shebang(script_content: str, preamble: str) -> str:
    if script_content.startswith("#!"):
        newline_at = script_content.find("\n")
        if newline_at == -1:
            return script_content + "\n" + preamble
        return script_content[: newline_at + 1] + preamble + script_content[newline_at + 1 :]
    return preamble + script_content
