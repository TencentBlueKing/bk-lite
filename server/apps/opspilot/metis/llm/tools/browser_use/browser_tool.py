"""浏览器操作工具 - 使用Browser-Use进行网页自动化"""

import asyncio
import os
import re
import tempfile
import threading
import time
from typing import Any, Awaitable, Callable, Dict, Optional, TypedDict
from urllib.parse import urlparse

from browser_use import Agent as BrowserAgent
from browser_use import Browser
from browser_use.agent.views import AgentOutput
from browser_use.browser.views import BrowserStateSummary
from browser_use.llm import ChatOpenAI
from django.conf import settings
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from loguru import logger
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

# 安全配置
DEFAULT_TIMEOUT = 60
MAX_RETRIES = 4
MAX_LOGIN_FAILURES = 2  # 登录失败最大重试次数

# 浏览器超时配置（秒），可通过环境变量调整
BROWSER_LLM_TIMEOUT = int(os.getenv("BROWSER_LLM_TIMEOUT", "60"))  # LLM 调用超时
BROWSER_STEP_TIMEOUT = int(os.getenv("BROWSER_STEP_TIMEOUT", "60"))  # 单步执行超时（包含导航、页面加载等）

# 会话缓存：用于在同一个 Agent 运行周期内共享浏览器用户数据目录
# 键: thread_id 或 run_id, 值: {"user_data_dir": str, "created_at": float}
_SESSION_CACHE: Dict[str, Dict[str, Any]] = {}
_SESSION_CACHE_LOCK = threading.Lock()
_SESSION_CACHE_TTL = 3600  # 缓存过期时间（秒），1小时


class LoginFailureError(Exception):
    """登录失败异常，当检测到登录失败超过最大重试次数时抛出"""

    def __init__(self, message: str, failure_count: int):
        self.message = message
        self.failure_count = failure_count
        super().__init__(message)


class BrowserStepInfo(TypedDict):
    """浏览器执行步骤信息，用于流式传递给前端"""

    step_number: int
    max_steps: int
    url: str
    title: str
    thinking: Optional[str]
    evaluation: Optional[str]
    memory: Optional[str]
    next_goal: Optional[str]
    actions: list[Dict[str, Any]]
    screenshot: Optional[str]  # base64 编码的截图


# 步骤回调类型定义
StepCallbackType = Callable[[BrowserStepInfo], None] | Callable[[BrowserStepInfo], Awaitable[None]]

# 登录失败检测关键词（中英文）
# 注意：这些关键词必须是页面上实际显示的错误消息，而不是 LLM 思考过程中的描述
# 为了避免误判，使用更精确的短语
LOGIN_FAILURE_PATTERNS = [
    # 中文 - 页面实际显示的错误消息
    "密码错误",
    "密码不正确",
    "用户名或密码错误",
    "账号或密码错误",
    "认证失败",
    "账号不存在",
    "用户不存在",
    "账户已锁定",
    "账号已锁定",
    "密码已过期",
    "登录信息错误",
    # 英文 - 页面实际显示的错误消息
    "invalid password",
    "incorrect password",
    "wrong password",
    "invalid credentials",
    "bad credentials",
    "username or password is incorrect",
    "invalid username or password",
    "account locked",
    "account disabled",
]

# 排除列表：这些短语出现时，即使包含失败关键词也不应触发检测
# 用于过滤 LLM 思考过程中的假设性描述
LOGIN_FAILURE_EXCLUSIONS = [
    "if login fail",
    "if the login fail",
    "in case of fail",
    "when login fail",
    "login might fail",
    "login may fail",
    "login could fail",
    "check if",
    "verify if",
    "whether the login",
    "handle fail",
    "error handling",
    "try again if",
    "retry if",
    "登录可能失败",
    "如果登录失败",
    "假设登录失败",
    "处理登录失败",
]


def _detect_login_failure(text: str) -> tuple[bool, str | None]:
    """
    检测文本中是否包含登录失败的关键词

    Args:
        text: 待检测的文本（可能是页面内容、evaluation、thinking 等）

    Returns:
        tuple[bool, str | None]: (是否检测到登录失败, 匹配到的关键词)
    """
    if not text:
        return False, None

    text_lower = text.lower()

    # 首先检查排除列表 - 如果包含假设性描述，则不触发检测
    for exclusion in LOGIN_FAILURE_EXCLUSIONS:
        if exclusion.lower() in text_lower:
            logger.debug(f"登录失败检测: 跳过，文本包含排除短语 '{exclusion}'")
            return False, None

    # 检测失败关键词
    for pattern in LOGIN_FAILURE_PATTERNS:
        if pattern.lower() in text_lower:
            return True, pattern
    return False, None


def _get_session_key(config: Optional[RunnableConfig]) -> Optional[str]:
    """
    从 config 中提取会话标识符

    优先使用 trace_id，其次使用 thread_id/run_id，用于在同一个 Agent 运行周期内共享状态。

    Args:
        config: 工具配置

    Returns:
        会话标识符，如果无法提取则返回 None
    """
    if not config:
        logger.debug("_get_session_key: config 为 None")
        return None

    # graph.py 将 trace_id 放在 config 顶层，所以先检查顶层
    logger.debug(f"_get_session_key: config top-level keys = {list(config.keys())}")

    # 优先使用顶层 trace_id（graph.py 设置的位置）
    trace_id = config.get("trace_id")
    if trace_id:
        logger.debug(f"_get_session_key: 使用顶层 trace_id = {trace_id}")
        return f"trace_{trace_id}"

    # 其次检查 configurable 内的 trace_id（兼容其他调用方式）
    configurable = config.get("configurable", {})
    logger.debug(f"_get_session_key: configurable keys = {list(configurable.keys())}")

    trace_id = configurable.get("trace_id")
    if trace_id:
        logger.debug(f"_get_session_key: 使用 configurable.trace_id = {trace_id}")
        return f"trace_{trace_id}"

    # 其次使用 thread_id（同一个对话线程）
    thread_id = configurable.get("thread_id")
    if thread_id:
        logger.debug(f"_get_session_key: 使用 thread_id = {thread_id}")
        return f"thread_{thread_id}"

    # 最后使用 run_id（同一次运行）
    run_id = configurable.get("run_id")
    if run_id:
        logger.debug(f"_get_session_key: 使用 run_id = {run_id}")
        return f"run_{run_id}"

    logger.warning("_get_session_key: 未找到任何会话标识符 (trace_id/thread_id/run_id)")
    return None


def _cleanup_expired_sessions() -> None:
    """清理过期的会话缓存"""
    current_time = time.time()
    expired_keys = []

    with _SESSION_CACHE_LOCK:
        for key, value in _SESSION_CACHE.items():
            if current_time - value.get("created_at", 0) > _SESSION_CACHE_TTL:
                expired_keys.append(key)

        for key in expired_keys:
            logger.debug(f"清理过期的浏览器会话缓存: {key}")
            del _SESSION_CACHE[key]


def _get_or_create_user_data_dir(config: Optional[RunnableConfig] = None) -> str:
    """
    获取或创建浏览器用户数据目录

    用于在同一个请求周期内的多次浏览器调用之间共享会话状态（cookies、localStorage等）。
    使用基于 thread_id 或 run_id 的缓存机制，确保同一个 Agent 运行周期内共享同一个目录。

    Args:
        config: 工具配置，包含 thread_id 或 run_id 用于标识会话

    Returns:
        str: 用户数据目录路径
    """
    # 定期清理过期缓存
    _cleanup_expired_sessions()

    # 尝试从缓存获取
    session_key = _get_session_key(config)
    if session_key:
        with _SESSION_CACHE_LOCK:
            cached = _SESSION_CACHE.get(session_key)
            if cached:
                user_data_dir = cached.get("user_data_dir")
                if user_data_dir and os.path.isdir(user_data_dir):
                    logger.info(f"复用已有的浏览器用户数据目录: {user_data_dir} (session_key={session_key})")
                    return user_data_dir

    # 创建新的临时目录
    user_data_dir = tempfile.mkdtemp(prefix="browser_use_session_")
    logger.info(f"创建新的浏览器用户数据目录: {user_data_dir} (session_key={session_key})")

    # 存入缓存
    if session_key:
        with _SESSION_CACHE_LOCK:
            _SESSION_CACHE[session_key] = {
                "user_data_dir": user_data_dir,
                "created_at": time.time(),
            }
            logger.debug(f"浏览器会话已缓存: {session_key} -> {user_data_dir}")

    return user_data_dir


def _validate_url(url: str) -> bool:
    """
    验证URL的安全性

    Args:
        url: 待验证的URL

    Returns:
        bool: URL是否安全

    Raises:
        ValueError: URL不安全时抛出异常
    """
    try:
        parsed = urlparse(url)

        # 检查协议
        if parsed.scheme not in ["http", "https"]:
            raise ValueError("仅支持HTTP/HTTPS协议")

        # 检查是否有有效的netloc
        if not parsed.netloc:
            raise ValueError("无效的URL格式")

        return True

    except Exception as e:
        raise ValueError(f"URL验证失败: {e}")


def _extract_sensitive_data(task: str) -> tuple[Optional[Dict[str, str]], str]:
    """
    从任务描述中提取敏感数据（如用户名、密码），用于执行时使用实际值，输出时脱敏

    browser-use 的 sensitive_data 参数工作原理:
    1. Task 中使用 <secret>占位符名</secret> 格式
    2. sensitive_data = {占位符名: 实际值}
    3. LLM 输出 <secret>占位符</secret>，browser-use 在执行动作时替换为实际值
    4. 日志/输出中始终显示 <secret>占位符</secret>，保护真实凭证

    Args:
        task: 任务描述字符串

    Returns:
        Tuple of:
        - Dict mapping placeholder to actual value, e.g., {"x_password": "WeOps2023", "x_username": "admin"}
          如果没有检测到敏感数据则返回 None
        - 脱敏后的任务文本（敏感信息被替换为 <secret>占位符</secret> 格式）
    """
    if not task:
        return None, task
    logger.info(f"全文task: {task}")
    sensitive_data: Dict[str, str] = {}
    masked_task = task

    # 敏感数据检测模式（支持中英文）
    # 格式: (pattern, placeholder)
    # pattern 中: group(1)=前缀, group(2)=敏感值, group(3)=可选后缀
    # 注意：占位符会被包裹成 <secret>placeholder</secret> 格式
    # 分隔符说明：支持空白、逗号、句号、顿号、"和"、"以及"等作为值的结束边界
    sensitive_patterns = [
        # === 密码相关 ===
        # 中文：密码是xxx / 密码：xxx / 密码:xxx / 密码 xxx（支持括号内的说明）
        # 密码值只匹配非空白、非中文字符（即只匹配ASCII字符、数字、常见符号）
        # [^\s\u4e00-\u9fff] 匹配非空白且非中文的字符
        (
            r"(密码\s*(?:是|为)?\s*[:：]?\s*)([^\s\u4e00-\u9fff]+)(\s*[（(].*?[)）])?(?=[\s\u4e00-\u9fff,，。、;；]|$)",
            "x_password",
        ),
        # 英文：password: xxx / password=xxx / password xxx
        # 同样排除中文字符
        (
            r"(password\s*[:=]?\s*[\"']?)([^\s\u4e00-\u9fff]+?)([\"']?)(?=[\s\u4e00-\u9fff,，。;；]|$)",
            "x_password",
        ),
        # pwd: xxx / pwd=xxx / pwd xxx
        (
            r"(pwd\s*[:=]?\s*[\"']?)([^\s\u4e00-\u9fff]+?)([\"']?)(?=[\s\u4e00-\u9fff,，。;；]|$)",
            "x_password",
        ),
        # === 用户名相关 ===
        # 中文：用户名是xxx / 账号是xxx / 用户名：xxx 等
        # 注意：需要在"和"、"以及"、"密码"等词前停止匹配
        # 用户名值只匹配非空白、非中文字符
        (
            r"((?:用户名|用户|账号|帐号)\s*(?:是|为)?\s*[:：]?\s*)([^\s\u4e00-\u9fff]+)()(?=[\s\u4e00-\u9fff,，。、;；]|和|以及|密码|pwd|password|$)",
            "x_username",
        ),
        # 英文：username / user + 分隔符 + 值
        (
            r"((?:username|user)\s*[:=]?\s*[\"']?)([^\s\u4e00-\u9fff]+?)([\"']?)(?=[\s\u4e00-\u9fff,，。;；]|and|password|pwd|$)",
            "x_username",
        ),
    ]

    # 遍历所有模式，提取并替换敏感数据
    for pattern, placeholder in sensitive_patterns:
        # 如果该占位符已存在（同类型的敏感数据已处理），跳过
        if placeholder in sensitive_data:
            continue

        match = re.search(pattern, masked_task, re.IGNORECASE)
        if match:
            # 获取完整匹配和敏感值
            if len(match.groups()) >= 2:
                actual_value = match.group(2).strip("\"'")  # 实际敏感值
            else:
                actual_value = match.group(1).strip("\"'")

            # 避免捕获到标点符号
            actual_value = actual_value.rstrip("，。,.")
            if actual_value:
                sensitive_data[placeholder] = actual_value
                # 在任务文本中替换敏感值为 <secret>占位符</secret> 格式
                # 这样 LLM 会输出相同格式，browser-use 在执行时替换为实际值
                secret_placeholder = f"<secret>{placeholder}</secret>"
                masked_task = re.sub(
                    pattern,
                    lambda m: f"{m.group(1)}{secret_placeholder}{m.group(3) if len(m.groups()) >= 3 and m.group(3) else ''}",
                    masked_task,
                    count=1,
                    flags=re.IGNORECASE,
                )

    return (sensitive_data if sensitive_data else None, masked_task)


def _create_login_failure_hook(
    has_credentials: bool,
    max_failures: int = MAX_LOGIN_FAILURES,
) -> tuple[Callable, dict]:
    """
    创建登录失败检测的 on_step_end hook

    当任务包含账号密码信息时，此 hook 会检测每个步骤后的页面状态，
    如果检测到登录失败超过指定次数，则暂停 agent 执行。

    注意：只检测页面标题中的登录失败信息，不检测 LLM 的思考过程，
    因为 LLM 可能在思考中描述 "如果登录失败会怎样" 等假设性内容。

    Args:
        has_credentials: 任务是否包含账号密码信息
        max_failures: 最大允许的登录失败次数

    Returns:
        Tuple of:
        - 异步 hook 函数
        - 状态字典（用于跟踪登录失败次数和检测结果）
    """
    # 使用字典来存储状态，以便在闭包中修改
    state = {
        "login_failure_count": 0,
        "last_failure_reason": None,
        "last_matched_pattern": None,
        "stopped_due_to_login_failure": False,
        "step_count": 0,
    }

    async def login_failure_hook(agent) -> None:
        """检测登录失败并在超过阈值时停止 agent"""
        state["step_count"] += 1
        step_num = state["step_count"]

        # 如果任务不包含账号密码，跳过检测
        if not has_credentials:
            logger.debug(f"[Step {step_num}] 登录失败检测: 跳过（无凭证信息）")
            return

        # 如果已经因登录失败停止，不再检测
        if state["stopped_due_to_login_failure"]:
            return

        try:
            # 获取当前浏览器状态
            browser_state = await agent.browser_session.get_browser_state_summary()
            page_title = browser_state.title if browser_state else ""

            # 只检测页面标题，不检测 LLM 思考过程（避免误判）
            # LLM 可能在 thinking/evaluation 中描述 "if login fails..." 等假设性内容
            failure_detected, matched_pattern = _detect_login_failure(page_title)

            if failure_detected:
                state["login_failure_count"] += 1
                state["last_failure_reason"] = page_title[:200]
                state["last_matched_pattern"] = matched_pattern
                logger.warning(
                    f"[Step {step_num}] 检测到登录失败 ({state['login_failure_count']}/{max_failures}): " f"匹配关键词='{matched_pattern}', 页面标题='{page_title}'"
                )

                # 如果失败次数达到阈值，停止 agent
                if state["login_failure_count"] >= max_failures:
                    state["stopped_due_to_login_failure"] = True
                    logger.error(f"[Step {step_num}] 登录失败次数已达 {max_failures} 次，停止执行。" f"匹配关键词: '{matched_pattern}', 页面标题: '{page_title}'")
                    # 暂停 agent 执行
                    agent.pause()
                    # 抛出异常以确保停止
                    raise LoginFailureError(
                        f"登录失败次数超过限制({max_failures}次)，已停止执行。" f"页面标题: {state['last_failure_reason']}",
                        state["login_failure_count"],
                    )

        except LoginFailureError:
            # 重新抛出登录失败异常
            raise
        except Exception:
            # 其他异常只记录日志，不影响主流程
            pass

    return login_failure_hook, state


def _create_step_callback_adapter(
    step_callback: Optional[StepCallbackType],
    max_steps: int,
) -> Optional[Callable[[BrowserStateSummary, AgentOutput, int], Awaitable[None]]]:
    """
    创建一个适配器，将用户回调转换为 browser-use 需要的回调格式

    Args:
        step_callback: 用户提供的步骤回调函数
        max_steps: 最大步骤数

    Returns:
        适配后的回调函数，或 None（如果未提供回调）
    """
    if step_callback is None:
        return None

    async def adapter(browser_state: BrowserStateSummary, model_output: AgentOutput, step_number: int) -> None:
        """适配器：将 browser-use 的回调参数转换为 BrowserStepInfo"""
        import inspect

        # 提取动作信息
        actions = []
        if model_output.action:
            for action in model_output.action:
                action_data = action.model_dump(exclude_unset=True)
                actions.append(action_data)

        # 构建步骤信息
        step_info: BrowserStepInfo = {
            "step_number": step_number,
            "max_steps": max_steps,
            "url": browser_state.url,
            "title": browser_state.title,
            "thinking": model_output.current_state.thinking if hasattr(model_output.current_state, "thinking") else None,
            "evaluation": model_output.current_state.evaluation_previous_goal,
            "memory": model_output.current_state.memory,
            "next_goal": model_output.current_state.next_goal,
            "actions": actions,
            "screenshot": browser_state.screenshot,
        }

        # 调用用户回调（支持同步和异步）
        try:
            if inspect.iscoroutinefunction(step_callback):
                await step_callback(step_info)
            else:
                step_callback(step_info)
        except Exception as e:
            logger.warning(f"步骤回调执行失败: {e}")

    return adapter


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_not_exception_type(LoginFailureError),  # 登录失败异常不重试
    reraise=True,
)
async def _browse_website_async(
    url: str,
    task: Optional[str] = None,
    max_steps: int = 100,
    headless: bool = True,
    llm: ChatOpenAI = None,
    step_callback: Optional[StepCallbackType] = None,
    sensitive_data: Optional[Dict[str, str]] = None,
    masked_task: Optional[str] = None,
    user_data_dir: Optional[str] = None,
    locale: str = "en",
) -> Dict[str, Any]:
    """
    异步浏览网站并执行任务

    Args:
        url: 目标网站URL
        task: 可选的任务描述，如"提取标题"、"点击登录按钮"等
        max_steps: 最大执行步骤数
        headless: 是否无头模式
        llm: 语言模型实例
        step_callback: 步骤回调函数，每完成一个步骤时调用，用于流式传递进度信息
        sensitive_data: 敏感数据字典，用于在输出中脱敏。格式: {"<secret>": "actual_value"}
                       任务中使用占位符 <secret>，执行时替换为实际值，输出时显示占位符
        masked_task: 脱敏后的任务文本（用于日志输出），如果为 None 则使用原始 task
        user_data_dir: 浏览器用户数据目录，用于在多次调用间保持会话状态（cookies、localStorage等）
        locale: 用户语言设置，用于控制 browser-use 输出语言（如 "zh-Hans" 使用中文，其他使用英文）

    Returns:
        Dict[str, Any]: 执行结果
            - success: 是否成功
            - content: 页面内容或提取的信息
            - error: 错误信息（如果失败）

    Raises:
        ValueError: 参数错误或执行失败
    """
    browser = None
    try:
        logger.info(f"开始浏览网站: {url}, 任务: {task or '无特定任务'}")

        # 初始化 LLM（使用 browser_use.llm.ChatOpenAI）
        if not llm:
            llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        executable_path = os.getenv("EXECUTABLE_PATH", None) or None

        # DEBUG 模式下显示浏览器窗口，方便调试
        # 可通过环境变量 BROWSER_HEADLESS 强制覆盖
        browser_headless_env = os.getenv("BROWSER_HEADLESS")
        if browser_headless_env is not None:
            # 环境变量优先级最高
            actual_headless = browser_headless_env.lower() not in ("false", "0", "no")
        elif getattr(settings, "DEBUG", False):
            # DEBUG 模式下默认显示浏览器窗口
            actual_headless = False
            logger.info("DEBUG 模式: 浏览器将以可见模式运行，便于调试")
        else:
            # 生产环境使用传入的 headless 参数（默认 True）
            actual_headless = headless

        # 初始化 Browser
        browser_init_kwargs = {
            "executable_path": executable_path,
            "headless": actual_headless,
            "enable_default_extensions": False,
            "user_data_dir": user_data_dir,  # 使用共享的用户数据目录保持会话状态
        }

        browser = Browser(**browser_init_kwargs)

        # 创建 browser-use agent
        # 判断task中是否已经明确包含了URL信息（使用脱敏后的任务判断，避免泄露）
        # 只有当task中包含完整URL或明确提到该URL时，才认为已包含导航信息
        task_to_check = masked_task or task

        if task_to_check and url.lower() in task_to_check.lower():
            final_task = task or ""
        else:
            final_task = f"首先，导航到 {url}。然后，{task}" if task else f"导航到 {url}"

        # 创建步骤回调适配器
        register_callback = _create_step_callback_adapter(step_callback, max_steps)

        # 创建登录失败检测 hook（仅当任务包含账号密码时启用）
        has_credentials = sensitive_data is not None and len(sensitive_data) > 0
        login_failure_hook, login_state = _create_login_failure_hook(has_credentials)

        # 扩展系统提示 - 根据用户语言设置选择输出语言
        # 中文 locale（如 "zh-Hans", "zh-CN", "zh"）使用中文输出
        if locale.startswith("zh"):
            extend_system_message = """
【语言要求】你的所有思考(thinking)、评估(evaluation)、记忆(memory)、下一步目标(next_goal)输出必须使用中文。

核心规则（必须遵守）：
1. 同一元素最多点击2次。点击2次后视为成功，继续下一步。
2. 在记忆中跟踪已点击的元素："已点击: [索引1, 索引2, ...]"
3. 提取操作最多尝试2次，之后切换到截图/视觉方式。
4. 重要 - 凭据处理：
   当任务中出现 <secret>xxx</secret> 时，在操作中必须原样输出。
   不要去掉标签或只输出占位符名称。
   系统会在执行时自动替换为实际值。
   - 正确: input_text(..., text="<secret>x_password</secret>")
   - 错误: input_text(..., text="x_password")
   - 错误: input_text(..., text="actual_password_here")
5. 重要 - URL导航规则：
   当任务明确要求"更改网址"、"跳转到URL"、"导航到"、"访问URL"时，必须使用 navigate action 直接跳转，禁止通过点击页面元素来实现导航。
   - 正确: {"navigate": {"url": "https://example.com/target"}}
   - 错误: 通过点击菜单、链接等元素来跳转到目标URL
   记住：任务说"将网址更改为 xxx"时，直接使用 navigate 跳转，不要尝试点击任何元素。
6. 重要 - 顺序执行规则：
   当任务需要依次检查多个元素时（如巡检、遍历列表），每一步只执行一个点击操作，等待页面加载完成并观察结果后，再进行下一个点击。
   - 禁止：一次性点击多个元素（如同时点击 #3937, #3938, #3939）
   - 正确：点击 #3937 → 等待加载 → 记录结果 → 下一步点击 #3938 → 等待加载 → 记录结果 → ...
   这样可以确保每个元素的响应都被正确观察和记录。
7. 重要 - 完整遍历规则：
   当任务要求"遍历所有"、"检查所有"、"巡检所有"节点时，必须完整遍历，不能提前结束。
   - 在 memory 中记录："待检查节点: [A, B, C, ...]，已完成: [A]，剩余: [B, C, ...]"
   - 每完成一个节点后，检查是否还有剩余未检查的节点
   - 如果列表有滚动条，必须向下滚动查看是否有更多节点
   - 只有当所有可见节点都已检查完毕后，才能进入下一步骤
   - 禁止：只检查了部分节点就生成报告
"""
        else:
            extend_system_message = """
CORE RULES (MUST FOLLOW):
1. NEVER click same element more than 2 times. After 2 clicks, treat as SUCCESS and move on.
2. Track clicked elements in memory: "Clicked: [index1, index2, ...]"
3. For extract action: max 2 attempts, then switch to screenshot/visual approach.
4. CRITICAL - Credentials handling:
   When you see <secret>xxx</secret> in the task, output it EXACTLY as-is in your actions.
   Do NOT strip the tags or output just the placeholder name.
   The system will automatically replace it with the actual value during execution.
   - CORRECT: input_text(..., text="<secret>x_password</secret>")
   - WRONG: input_text(..., text="x_password")
   - WRONG: input_text(..., text="actual_password_here")
5. CRITICAL - URL Navigation:
   When task explicitly requires "change URL to", "navigate to", "go to URL",
   or "visit URL", you MUST use the navigate action to jump directly.
   DO NOT click page elements to navigate.
   - CORRECT: {"navigate": {"url": "https://example.com/target"}}
   - WRONG: Clicking menus, links, or buttons to reach the target URL
   Remember: When task says "change URL to xxx", use navigate action directly,
   do NOT attempt to click any elements.
6. CRITICAL - Sequential Execution:
   When task requires checking multiple elements sequentially
   (e.g., inspection, traversing a list), execute only ONE click per step.
   Wait for page to load and observe the result before clicking next element.
   - FORBIDDEN: Clicking multiple elements at once
     (e.g., clicking #3937, #3938, #3939 in the same step)
   - CORRECT: Click #3937 → wait for load → record result →
     next step click #3938 → wait for load → record result → ...
   This ensures each element's response is properly observed and recorded.
7. CRITICAL - Complete Traversal:
   When task requires "traverse all", "check all", or "inspect all" nodes, you MUST complete the full traversal without stopping early.
   - Track in memory: "Pending nodes: [A, B, C, ...], Completed: [A], Remaining: [B, C, ...]"
   - After each node, check if there are remaining unchecked nodes
   - If the list has a scrollbar, scroll down to check for more nodes
   - Only proceed to the next step after ALL visible nodes have been checked
   - FORBIDDEN: Generating report after checking only a few nodes
"""

        # 创建 browser-use agent（带回调支持和优化配置）
        browser_agent = BrowserAgent(
            task=final_task,
            llm=llm,
            browser=browser,
            register_new_step_callback=register_callback,
            extend_system_message=extend_system_message,
            max_actions_per_step=5,  # 每步最多5个动作，避免过度操作
            max_failures=3,  # 最大失败重试次数
            sensitive_data=sensitive_data,  # 敏感数据脱敏
            llm_timeout=BROWSER_LLM_TIMEOUT,  # LLM 调用超时
            step_timeout=BROWSER_STEP_TIMEOUT,  # 单步执行超时（包含导航等待）
        )

        # 执行浏览任务（使用登录失败检测 hook）
        agent_result = await browser_agent.run(
            max_steps=max_steps,
            on_step_end=login_failure_hook if has_credentials else None,
        )
        # 提取结果
        final_result = agent_result.final_result()
        result_text = str(final_result) if final_result else "未获取到有效结果"

        return {
            "success": agent_result.is_successful(),
            "content": result_text,
            "url": url,
            "task": task,
            "has_errors": agent_result.has_errors(),
            "errors": [str(err) for err in agent_result.errors() if err],
            "steps_taken": agent_result.number_of_steps(),
        }

    except ImportError as e:
        error_msg = "browser-use 包未安装，请先安装: pip install browser-use"
        logger.exception(error_msg)
        raise ValueError(error_msg) from e

    except LoginFailureError as e:
        # 登录失败异常：返回友好的错误信息，不再重试
        logger.warning(f"登录失败，停止执行: {e.message}")
        return {
            "success": False,
            "content": None,
            "url": url,
            "task": task,
            "has_errors": True,
            "errors": [e.message],
            "steps_taken": 0,
            "login_failure": True,
            "login_failure_count": e.failure_count,
        }

    except Exception as e:
        error_msg = f"浏览器操作失败: {str(e)}"
        logger.exception(error_msg)
        raise ValueError(error_msg) from e

    finally:
        if browser:
            try:
                await browser.kill()
            except Exception:
                pass


def _run_async_task(coro):
    """
    在同步上下文中运行异步任务

    Args:
        coro: 协程对象

    Returns:
        协程的返回值
    """
    try:
        # 尝试获取当前事件循环
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果循环正在运行，创建新的事件循环（在新线程中）
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # 没有事件循环，创建新的
        return asyncio.run(coro)


@tool()
def browse_website(
    url: str,
    task: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    使用AI驱动的浏览器打开网站并执行操作

    **⚠️ 重要：一次调用完成所有任务 ⚠️**
    此工具内置完整的AI Agent，能够自动执行多步骤的复杂任务序列。
    请在一次调用中描述完整的任务流程，不要拆分成多次调用！
    每次调用结束后浏览器会关闭，多次调用会导致登录状态丢失。

    **🔐 凭据传递方式（必须使用 username/password 参数）：**
    当任务需要登录时，必须将用户名密码放在独立参数中，不要写在 task 里：

    ```python
    browse_website(
        url="https://example.com/login",
        username="admin",
        password="mypassword123",
        task="使用提供的凭据登录系统，登录成功后点击'系统巡检'菜单，执行巡检并返回结果"
    )
    ```

    这样做的好处：
    1. 凭据会自动安全地传递给浏览器，不会在日志中暴露
    2. 避免凭据在任务描述中被意外修改或脱敏
    3. 浏览器会在需要时自动填入正确的用户名和密码

    **错误用法（不要这样做）：**
    - ❌ task="输入用户名admin和密码123456登录" （凭据不要写在task里！）
    - ❌ 拆分成多次调用（会丢失登录状态）

    **何时使用此工具：**
    - 需要与网页进行交互（点击、填表等）
    - 需要从动态加载的网页中提取信息
    - 需要执行复杂的网页自动化任务
    - 普通的HTTP请求无法获取所需内容

    **工具能力：**
    - 内置AI Agent自动执行多步骤任务（登录→导航→操作→提取）
    - 处理JavaScript渲染的动态内容
    - 支持点击、输入、滚动等交互
    - 智能提取页面信息
    - 自动处理常见的网页元素
    - 支持流式传递执行进度（通过 step_callback）

    **典型使用场景：**
    1. 登录并执行操作：
       browse_website(
           url="https://example.com/login",
           username="admin",
           password="123456",
           task="使用提供的凭据登录，登录成功后点击'系统巡检'菜单，执行巡检并返回巡检结果"
       )

    2. 执行搜索并提取结果（无需登录）：
       browse_website(
           url="https://www.google.com",
           task="搜索'Python教程'，等待结果加载，提取前3个结果的标题和链接"
       )

    Args:
        url (str): 目标网站URL（必填）
        task (str, optional): 完整的任务描述，应包含所有需要执行的步骤。
            注意：不要在task中包含用户名密码，请使用username/password参数
        username (str, optional): 登录用户名。当任务需要登录时必填
        password (str, optional): 登录密码。当任务需要登录时必填
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 执行结果
            - success (bool): 是否成功
            - content (str): 提取的内容或执行结果
            - url (str): 访问的URL
            - task (str): 执行的任务
            - error (str): 错误信息（如果失败）

    **注意事项：**
    - 此工具需要安装 browser-use 包
    - 执行时间可能较长，取决于网页复杂度和任务
    - 需要稳定的网络连接
    - 某些网站可能有反爬虫机制
    - 确保任务描述清晰具体，包含完整流程
    - ⚠️ 不要将连续任务拆分成多次调用，这会导致登录状态丢失
    - 🔐 凭据必须通过 username/password 参数传递，不要写在 task 中
    """
    configurable = config.get("configurable", {}) if config else {}
    llm_config = configurable.get("graph_request")
    step_callback: Optional[StepCallbackType] = configurable.get("browser_step_callback")

    try:
        # 验证URL
        _validate_url(url)
        llm = ChatOpenAI(
            model=llm_config.model,
            temperature=0.3,
            api_key=llm_config.openai_api_key,
            base_url=llm_config.openai_api_base,
        )

        # 从 task 中提取敏感数据
        sensitive_data, masked_task = _extract_sensitive_data(task) if task else (None, task)

        # 合并独立参数中的凭据（优先级更高）
        # username/password 参数直接传入的凭据会覆盖 task 中提取的同名凭据
        if username or password:
            if sensitive_data is None:
                sensitive_data = {}
            if username:
                sensitive_data["x_username"] = username
                logger.info("从 username 参数添加凭据: x_username=***")
            if password:
                sensitive_data["x_password"] = password
                logger.info("从 password 参数添加凭据: x_password=***")

            # 如果 task 中没有提及凭据占位符，自动添加提示
            # 这样浏览器 agent 知道有凭据可用
            if masked_task and "x_username" in sensitive_data and "<secret>x_username</secret>" not in masked_task:
                # 在 task 开头添加凭据提示
                credential_hint = "【凭据已提供】用户名: <secret>x_username</secret>"
                if "x_password" in sensitive_data:
                    credential_hint += ", 密码: <secret>x_password</secret>"
                masked_task = f"{credential_hint}。{masked_task}"

        # 获取或创建共享的浏览器用户数据目录（基于 thread_id/run_id 缓存，用于保持会话状态）
        user_data_dir = _get_or_create_user_data_dir(config)

        # 获取用户语言设置，用于控制 browser-use 输出语言
        locale = getattr(llm_config, "locale", "en") if llm_config else "en"

        result = _run_async_task(
            _browse_website_async(
                url=url,
                task=masked_task,
                llm=llm,
                step_callback=step_callback,
                sensitive_data=sensitive_data,
                masked_task=masked_task,
                user_data_dir=user_data_dir,
                locale=locale,
            )
        )
        return result

    except ValueError as e:
        return {"success": False, "error": str(e), "url": url}
    except Exception as e:
        logger.exception(f"浏览器操作异常: {e}")
        return {"success": False, "error": str(e), "url": url}


@tool()
def extract_webpage_info(url: str, selectors: Optional[Dict[str, str]] = None, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    从网页中提取特定信息

    **何时使用此工具：**
    - 需要从网页中提取特定的结构化数据
    - 知道要提取的内容类型但不知道具体位置
    - 需要AI智能识别页面元素

    **工具能力：**
    - AI自动识别和提取指定类型的信息
    - 处理动态加载的内容
    - 支持结构化数据提取
    - 自动处理各种页面布局
    - 支持流式传递执行进度（通过 step_callback）

    **典型使用场景：**
    1. 提取文章信息：
       - url="https://blog.example.com/post/123"
       - selectors={"title": "文章标题", "author": "作者", "content": "正文"}

    2. 提取商品信息：
       - url="https://shop.example.com/product/456"
       - selectors={"name": "商品名称", "price": "价格", "stock": "库存"}

    3. 提取列表数据：
       - url="https://example.com/list"
       - selectors={"items": "所有列表项"}

    Args:
        url (str): 目标网站URL（必填）
        selectors (dict, optional): 要提取的信息字典
            键：字段名，值：字段描述
        config (RunnableConfig): 工具配置（自动传递）
            - 可通过 config["configurable"]["browser_step_callback"] 传递步骤回调函数

    Returns:
        dict: 提取结果
            - success (bool): 是否成功
            - data (dict): 提取的数据
            - url (str): 访问的URL
            - error (str): 错误信息（如果失败）

    **注意事项：**
    - selectors 的描述应该清晰具体
    - 如果不提供 selectors，将提取页面主要内容
    - 提取结果取决于页面结构和AI理解能力
    """
    try:
        _validate_url(url)
        configurable = config.get("configurable", {}) if config else {}
        llm_config = configurable.get("graph_request")
        step_callback: Optional[StepCallbackType] = configurable.get("browser_step_callback")

        llm = ChatOpenAI(
            model=llm_config.model,
            temperature=0.3,
            api_key=llm_config.openai_api_key,
            base_url=llm_config.openai_api_base,
        )
        logger.info(f"selectors: {selectors}")
        if selectors:
            task_parts = ["从页面中提取以下信息："]
            for field, description in selectors.items():
                task_parts.append(f"- {field}: {description}")
            task = "\n".join(task_parts)
        else:
            task = "提取页面的主要内容，包括标题、正文和关键信息"

        sensitive_data, masked_task = _extract_sensitive_data(task) if task else (None, task)

        # 获取或创建共享的浏览器用户数据目录（基于 thread_id/run_id 缓存，用于保持会话状态）
        user_data_dir = _get_or_create_user_data_dir(config)

        # 获取用户语言设置，用于控制 browser-use 输出语言
        locale = getattr(llm_config, "locale", "en") if llm_config else "en"

        result = _run_async_task(
            _browse_website_async(
                url=url,
                task=masked_task,
                llm=llm,
                step_callback=step_callback,
                sensitive_data=sensitive_data,
                masked_task=masked_task,
                user_data_dir=user_data_dir,
                locale=locale,
            )
        )

        if result.get("success"):
            return {
                "success": True,
                "data": result.get("content"),
                "url": url,
                "selectors": selectors,
            }
        return result

    except ValueError as e:
        return {"success": False, "error": str(e), "url": url}
    except Exception as e:
        logger.exception(f"信息提取异常: {e}")
        return {"success": False, "error": str(e), "url": url}
