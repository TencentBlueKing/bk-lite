"""ShellGuardMiddleware：给 deepagents 的 ``execute`` shell 工具加「高危命令黑名单」。

背景：deepagents 的 ``execute`` 工具本身**没有命令范围限制**（其 FilesystemPermission
只管文件工具的路径，源码注释明确写 permissions for the execute tool are not
implemented）。LangChain v1 提供 ``AgentMiddleware.wrap_tool_call`` 拦截点，可在工具
真正执行前检查/改写/拒绝调用——本中间件即用它给 ``execute`` 接一层黑名单策略。

策略（黑名单，默认放行）：
    - 仅作用于名为 ``execute`` 的工具调用，其余工具一律放行。
    - 命中高危/破坏性模式（rm -rf、mkfs、dd、shutdown、fork 炸弹、curl|bash、写系统
      目录、读 /etc/shadow、sudo 提权等）的命令直接拒绝，返回 error ToolMessage，
      不真正执行；技能正常 CLI（uvx/npx/curl 下载等）不受影响。
    - 可通过环境变量 ``OPSPILOT_SHELL_DENY_EXTRA`` 追加自定义正则（``;;`` 或换行分隔），
      ``OPSPILOT_SHELL_GUARD_DISABLE=1`` 可整体关闭（仅限明确知道风险时）。

注意：这是「命令字符串层面的黑名单」，是纵深防御的一层（配合一次性沙箱、文件工具
关笼、环境变量白名单），**不是**容器级强隔离——绕过黑名单的奇技淫巧总归存在。要强
隔离仍需 NATS executor / 容器沙箱后端。
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from apps.core.logger import opspilot_logger as logger

# 受管控的工具名（deepagents 的 shell 工具固定叫 execute）
GUARDED_TOOL_NAME = "execute"

# (规则名, 正则)。正则对整条命令字符串做大小写不敏感搜索。
# 设计取向：拦「破坏性 / 提权 / 读系统机密 / 管道执行远端脚本 / 写系统目录」这些
# 不懂的人最容易顺手踩的雷；普通技能命令（下载、转换、读写沙箱内文件）不误伤。
_DEFAULT_DENY_RULES: tuple[tuple[str, str], ...] = (
    ("递归强制删除 (rm -rf/-fr)", r"\brm\b(?=[^\n]*\s-)[^\n]*\b(?:rf|fr)\b|\brm\b\s+-[a-z]*r[a-z]*f|\brm\b\s+-[a-z]*f[a-z]*r"),
    ("删除根/家目录/通配", r"\brm\b\s+-[a-z]*\s*(?:/|~|\$HOME|/\*|\*)(?:\s|$)"),
    ("格式化文件系统 (mkfs)", r"\bmkfs(\.\w+)?\b"),
    ("裸写块设备 (dd if=)", r"\bdd\b[^\n]*\bif="),
    ("写/dev块设备", r">\s*/dev/(sd|nvme|disk|rdisk|hd)\w*"),
    ("关机/重启", r"\b(shutdown|reboot|halt|poweroff)\b|\binit\s+0\b"),
    ("强杀进程", r"\bkill\b\s+-9\b|\bkillall\b|\bpkill\b"),
    ("递归改权限/属主", r"\bch(mod|own)\b\s+-[a-z]*R"),
    ("挂载/卸载", r"\b(u?mount)\b"),
    ("fork 炸弹", r":\s*\(\s*\)\s*\{.*\|\s*:\s*&\s*\}\s*;\s*:|:\(\)\{:"),
    ("管道执行远端脚本 (curl|wget | sh)", r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|d)?sh\b"),
    ("提权 (sudo/su/doas)", r"(^|[\s;&|])(sudo|doas)\b|(^|[\s;&|])su\s+"),
    ("改账户/密码", r"\b(useradd|userdel|usermod|groupadd|passwd|chpasswd|visudo)\b"),
    ("读系统机密 (/etc/shadow|passwd)", r"/etc/(shadow|gshadow|sudoers)\b|(cat|less|more|head|tail|grep|awk|sed|cp|scp|tee)\b[^\n]*/etc/passwd\b"),
    ("重定向写系统目录", r">>?\s*/(etc|usr|bin|sbin|boot|lib|lib64|sys|proc|var/lib|var/run)(/|\b)"),
    ("写/删系统目录", r"\b(tee|cp|mv|install|rm|ln)\b[^\n]*\s/(etc|usr|bin|sbin|boot|lib|lib64|sys|proc|var/lib|var/run)(/|\b)"),
    ("停服务/改自启", r"\bsystemctl\b\s+(stop|disable|mask|kill)\b|\bservice\b\s+\S+\s+(stop|restart)\b"),
    ("改防火墙/网络", r"\b(iptables|ip6tables|nft|ufw|firewall-cmd)\b"),
    ("覆盖磁盘填零/熵", r"\b(shred|wipefs|blkdiscard)\b"),
)


def _load_deny_rules() -> list[tuple[str, "re.Pattern[str]"]]:
    """编译默认黑名单 + 环境变量追加的自定义规则。"""
    rules: list[tuple[str, re.Pattern[str]]] = []
    for name, pattern in _DEFAULT_DENY_RULES:
        try:
            rules.append((name, re.compile(pattern, re.IGNORECASE)))
        except re.error as e:  # pragma: no cover - 静态正则不应出错
            logger.warning("[ShellGuard] 默认规则编译失败(%s): %r", name, e)
    extra = os.getenv("OPSPILOT_SHELL_DENY_EXTRA", "").strip()
    if extra:
        # 支持 ;; 或换行分隔多条
        for raw in re.split(r";;|\n", extra):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rules.append(("自定义规则", re.compile(raw, re.IGNORECASE)))
            except re.error as e:
                logger.warning("[ShellGuard] 自定义规则编译失败(%r): %r", raw, e)
    return rules


def match_denied_rule(command: str, rules: list[tuple[str, "re.Pattern[str]"]]) -> str | None:
    """返回第一个命中的规则名；未命中返回 None。纯函数，便于单测。"""
    if not command:
        return None
    for name, pattern in rules:
        if pattern.search(command):
            return name
    return None


class ShellGuardMiddleware(AgentMiddleware):
    """拦截 ``execute`` 工具的高危命令（黑名单，默认放行其余）。"""

    def __init__(self, deny_rules: list[tuple[str, "re.Pattern[str]"]] | None = None) -> None:
        super().__init__()
        self._enabled = os.getenv("OPSPILOT_SHELL_GUARD_DISABLE", "0") != "1"
        self._rules = deny_rules if deny_rules is not None else _load_deny_rules()

    # ---- 内部：判定 + 拒绝消息 ---------------------------------------- #
    def _deny_message_or_none(self, request) -> ToolMessage | None:
        """命中黑名单则返回 error ToolMessage；否则 None（放行）。"""
        if not self._enabled:
            return None
        call = getattr(request, "tool_call", None) or {}
        if call.get("name") != GUARDED_TOOL_NAME:
            return None
        command = str((call.get("args") or {}).get("command") or "")
        hit = match_denied_rule(command, self._rules)
        if hit is None:
            return None
        logger.warning("[ShellGuard] 拦截高危命令[%s]: %s", hit, command[:300])
        return ToolMessage(
            content=(
                f"⛔ 命令被安全策略拦截（命中：{hit}）。该命令属于高危/破坏性操作，已拒绝执行。\n"
                f"如确需执行，请改用更小范围、可逆的命令，或联系管理员调整策略。"
            ),
            tool_call_id=call.get("id", ""),
            name=GUARDED_TOOL_NAME,
            status="error",
        )

    # ---- LangChain 拦截钩子（同步 + 异步都实现） ---------------------- #
    def wrap_tool_call(self, request, handler: Callable[[Any], Any]) -> Any:
        denied = self._deny_message_or_none(request)
        if denied is not None:
            return denied
        return handler(request)

    async def awrap_tool_call(self, request, handler: Callable[[Any], Any]) -> Any:
        denied = self._deny_message_or_none(request)
        if denied is not None:
            return denied
        return await handler(request)
