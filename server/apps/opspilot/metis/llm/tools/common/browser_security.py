"""浏览器工具共享安全辅助函数。

集中处理 browser_use 与 agent_browser 两个工具共有的安全关注点，避免在多处
重复实现（band-aid）：

1. SSRF 防护：所有浏览器导航 URL 统一走 ``apps.core.utils.ssrf_validator``
   中的 ``SSRFValidator``（与 fetch 工具同一个校验器），阻断私网 / 链路本地 /
   回环 / 云元数据地址以及非 http(s) 协议（含 ``file://``）。
2. 敏感值脱敏：在写入任何日志前，将凭据等敏感值替换为占位符。
3. sensitive_data 注入：仅接受足够长的敏感值，拒绝过短 / 常见值，避免在任务
   文本中做"盲目字符串替换"导致过度替换或静默失效。
4. 临时 Chrome 用户数据目录的生命周期管理：在缺少持久会话标识时使用上下文
   管理器，确保 ``finally`` 中清理，防止进程频繁创建 / 缺失 trace_id 时泄漏。
"""

import contextlib
import os
import shutil
import tempfile
from typing import Dict, Iterator, List, Optional

from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator

# 注入 sensitive_data 时允许的最小值长度。
# 过短 / 过于常见的值（如 'admin'、'123'）如果用于盲目字符串替换，
# 既可能过度替换页面中的正常文本，也可能因 LLM 未原样输出而静默失效。
# 这里仅作为"是否安全可用于占位"的阈值，真正的注入交由 browser-use 的
# sensitive_data 结构化映射完成。
MIN_SENSITIVE_VALUE_LEN = 4


def validate_browser_url(url: str) -> str:
    """对浏览器导航目标 URL 进行 SSRF 校验。

    复用 fetch 工具同款 ``SSRFValidator``，统一阻断私网 / 链路本地 / 回环 /
    云元数据（169.254.169.254 等）地址以及非 http(s) 协议（含 file://）。

    Args:
        url: 待校验的目标 URL。

    Returns:
        规范化后的 URL。

    Raises:
        ValueError: URL 为空、格式非法或指向被禁止的地址（SSRFError 是
            ValueError 的子类，调用方既可统一捕获 ValueError，也可单独区分）。
    """
    if not url or not url.strip():
        raise ValueError("URL 不能为空")
    # SSRFValidator.validate 抛出的 SSRFError 继承自 ValueError，
    # 这里直接向上抛出，保持与历史 _validate_url 的 ValueError 契约一致。
    return SSRFValidator.validate(url.strip())


def is_safe_browser_url(url: str) -> bool:
    """返回 URL 是否通过 SSRF 校验（不抛异常的便捷判断）。"""
    try:
        validate_browser_url(url)
        return True
    except (ValueError, SSRFError):
        return False


def build_sensitive_data(
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """从独立参数构建 browser-use 的 sensitive_data 占位映射。

    仅接受长度达到 ``MIN_SENSITIVE_VALUE_LEN`` 的值；过短 / 常见值会被跳过，
    避免后续用于盲目字符串替换时过度替换或静默失效。

    Returns:
        {占位符名: 实际值}，例如 {"x_username": "admin01", "x_password": "..."}。
        没有可用凭据时返回 None。
    """
    sensitive_data: Dict[str, str] = {}
    if username and len(username) >= MIN_SENSITIVE_VALUE_LEN:
        sensitive_data["x_username"] = username
    if password and len(password) >= MIN_SENSITIVE_VALUE_LEN:
        sensitive_data["x_password"] = password

    return sensitive_data or None


def collect_sensitive_values(*values: Optional[str]) -> List[str]:
    """收集需要脱敏的敏感值列表，过滤空值与过短值。

    过短的值（如 '123'）不参与日志脱敏替换，否则会把日志里大量正常数字 / 短词
    误替换为占位符，反而干扰排障。
    """
    result: List[str] = []
    for value in values:
        if value and len(value) >= MIN_SENSITIVE_VALUE_LEN and value not in result:
            result.append(value)
    # 长值优先替换，避免一个值是另一个值子串时出现部分替换。
    result.sort(key=len, reverse=True)
    return result


def redact_secrets(text: Optional[str], secret_values: Optional[List[str]]) -> Optional[str]:
    """在写入日志前，将文本中出现的敏感值替换为占位符。

    仅用于"日志输出"脱敏，不用于构造交给 browser-use 执行的任务文本
    （那条路径应使用结构化 sensitive_data，而非字符串替换）。
    """
    if not text or not secret_values:
        return text
    redacted = text
    for value in secret_values:
        if value:
            redacted = redacted.replace(value, "***")
    return redacted


def redact_command_args(
    command_args: Optional[List[str]],
    secret_values: Optional[List[str]] = None,
) -> List[str]:
    """对将要打印到日志的 CLI 参数列表做脱敏。

    除了显式提供的 ``secret_values``，还会对紧跟在敏感动作（type/fill）之后的
    取值参数做保守脱敏，避免凭据通过 ``type``/``fill`` 等命令泄漏到日志。
    """
    if not command_args:
        return list(command_args or [])

    sensitive_actions = {"type", "fill", "press", "secret"}
    redacted: List[str] = []
    prev_is_action = False
    for arg in command_args:
        text = str(arg)
        if secret_values:
            text = redact_secrets(text, secret_values)
        # type/fill <selector> <value> —— 取值通常是第二个参数，
        # 这里对动作后的非 selector（不以 @ 开头）参数做保守脱敏。
        if prev_is_action and not text.startswith("@") and not text.startswith("-"):
            redacted.append("***")
        else:
            redacted.append(text)
        prev_is_action = str(arg).lower() in sensitive_actions
    return redacted


@contextlib.contextmanager
def browser_user_data_dir(persistent_dir: Optional[str]) -> Iterator[str]:
    """提供浏览器用户数据目录，并在无持久会话时确保清理。

    - 当存在持久会话目录（``persistent_dir`` 非空，由调用方基于
      trace_id/thread_id/run_id 维护）时，直接复用该目录，``finally`` 不清理，
      由会话缓存的 TTL 机制负责回收。
    - 当没有持久会话标识时（进程频繁创建 / 缺失 trace_id），创建一个临时目录并
      在退出时无条件删除，避免临时 Chrome profile 泄漏。
    """
    if persistent_dir:
        yield persistent_dir
        return

    temp_dir = tempfile.mkdtemp(prefix="browser_use_session_")
    try:
        yield temp_dir
    finally:
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
