"""浏览器操作工具 - 使用Browser-Use进行网页自动化"""

import asyncio
import os
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

from apps.opspilot.utils.execution_interrupt import is_interrupt_requested

# 安全配置
MAX_RETRIES = 2
MAX_LOGIN_FAILURES = 2  # 登录失败最大重试次数

# 浏览器超时配置（秒），可通过环境变量调整
BROWSER_LLM_TIMEOUT = int(os.getenv("BROWSER_LLM_TIMEOUT", "30"))  # LLM 调用超时
BROWSER_STEP_TIMEOUT = int(os.getenv("BROWSER_STEP_TIMEOUT", "60"))  # 单步执行超时（包含导航、页面加载等）
BROWSER_TASK_EVENT_MAX_LEN = int(os.getenv("BROWSER_TASK_EVENT_MAX_LEN", "4000"))

# 页面加载等待配置（秒），避免截图时页面仍在 loading
# minimum_wait_page_load_time: 页面加载后最小等待时间，确保页面渲染完成后再截图
# wait_for_network_idle_page_load_time: 等待网络请求完成的时间
BROWSER_MIN_WAIT_PAGE_LOAD = float(os.getenv("BROWSER_MIN_WAIT_PAGE_LOAD", "1"))
BROWSER_WAIT_NETWORK_IDLE = float(os.getenv("BROWSER_WAIT_NETWORK_IDLE", "1"))

# 智能等待功能开关（默认关闭，保持向后兼容）
BROWSER_SMART_WAIT_ENABLED = os.getenv("BROWSER_SMART_WAIT_ENABLED", "false").lower() == "true"

# DOM 错误检测功能开关（默认开启，用于巡检任务中检测 Toast/错误提示）
BROWSER_DOM_ERROR_DETECTION_ENABLED = os.getenv("BROWSER_DOM_ERROR_DETECTION_ENABLED", "true").lower() == "true"

# 智能等待配置参数
# 注意：智能等待采用"固定等待+检测"模式，而非"等待加载完成"模式
# 这样可以检测出"页面加载太慢"的场景
SMART_WAIT_DETECTION_TIME = float(os.getenv("SMART_WAIT_DETECTION_TIME", "3.0"))  # 固定等待时间（秒），等待后检测加载状态
SMART_WAIT_RENDER_DELAY = float(os.getenv("SMART_WAIT_RENDER_DELAY", "0.3"))  # 额外渲染等待时间（秒）

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


class BrowserExecutionInterruptedError(Exception):
    """浏览器执行被中断异常"""


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
CustomEventCallbackType = Callable[[Dict[str, Any]], None] | Callable[[Dict[str, Any]], Awaitable[None]]

LOW_SIGNAL_MESSAGES = {
    "执行作业",
    "执行",
    "开始",
    "开始执行",
    "运行",
    "运行一下",
    "按要求执行",
    "go",
    "run",
    "start",
}

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


def _build_sensitive_data(username: Optional[str] = None, password: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    从独立参数构建 sensitive_data 字典

    browser-use 的 sensitive_data 参数工作原理:
    1. Task 中使用 <secret>占位符名</secret> 格式
    2. sensitive_data = {占位符名: 实际值}
    3. LLM 输出 <secret>占位符</secret>，browser-use 在执行动作时替换为实际值
    4. 日志/输出中始终显示 <secret>占位符</secret>，保护真实凭证

    注意：凭据应通过 browse_website 的 username/password 参数传递，
    而不是写在 task 文本中。LLM 已在 react_agent_system_message.jinja2
    中被严格约束使用参数传递方式。

    Args:
        username: 用户名（可选）
        password: 密码（可选）

    Returns:
        Dict mapping placeholder to actual value, e.g., {"x_password": "123456", "x_username": "admin"}
        如果没有凭据则返回 None
    """
    if not username and not password:
        return None

    sensitive_data: Dict[str, str] = {}
    if username:
        sensitive_data["x_username"] = username
    if password:
        sensitive_data["x_password"] = password

    return sensitive_data


def _build_browser_task_event_payload(tool_name: str, url: str, final_task: str) -> Dict[str, Any]:
    """构建 browser_task_received 事件负载（含长度保护）"""
    task_text = final_task or ""
    if len(task_text) > BROWSER_TASK_EVENT_MAX_LEN:
        return {
            "tool": tool_name,
            "url": url,
            "task_final": task_text[:BROWSER_TASK_EVENT_MAX_LEN],
            "truncated": True,
            "timestamp_ms": int(time.time() * 1000),
        }
    return {
        "tool": tool_name,
        "url": url,
        "task_final": task_text,
        "truncated": False,
        "timestamp_ms": int(time.time() * 1000),
    }


def _is_low_signal_message(message: Optional[str]) -> bool:
    if not message:
        return True

    text = message.strip()
    if not text:
        return True

    normalized = text.lower()
    if len(normalized) <= 12 and normalized in LOW_SIGNAL_MESSAGES:
        return True

    return False


def _build_forced_browser_task(base_task: Optional[str], user_message: Optional[str], llm_task: Optional[str]) -> Optional[str]:
    base_text = (base_task or "").strip()
    delta_text = (user_message or "").strip()

    if not base_text:
        return llm_task

    if not delta_text or _is_low_signal_message(delta_text) or delta_text in base_text:
        return base_text

    return f"""请严格按以下要求执行，不得省略或改写。

【基础任务】
{base_text}

【本轮用户补充要求】
{delta_text}"""


def _apply_secret_placeholders(task: Optional[str], sensitive_data: Optional[Dict[str, str]]) -> Optional[str]:
    if not task or not sensitive_data:
        return task

    replaced_task = task
    for secret_key, actual_value in sensitive_data.items():
        if not actual_value:
            continue
        placeholder = f"<secret>{secret_key}</secret>"
        replaced_task = replaced_task.replace(actual_value, placeholder)

    return replaced_task


def _create_smart_wait_hook() -> tuple[Callable, dict]:
    """
    创建智能页面加载检测的 on_step_start hook

    采用"固定等待+检测"模式：
    1. 固定等待 SMART_WAIT_DETECTION_TIME（默认 2s）
    2. 等待结束后检测图片加载状态
    3. 如果有未加载完成的图片，记录到状态中作为"加载慢"的证据
    4. 不会等待图片加载完成，让 browser-use 直接截图

    这样可以检测出"页面加载太慢"的场景，而不是掩盖问题。

    Returns:
        Tuple of:
        - 异步 hook 函数
        - 状态字典（包含检测到的慢加载信息）
    """
    state = {
        "step_count": 0,
        "total_wait_time": 0.0,
        "slow_load_detected": [],  # 检测到的慢加载页面列表
    }

    async def smart_wait_hook(agent) -> None:
        """固定等待后检测页面加载状态"""
        import asyncio

        state["step_count"] += 1
        step_num = state["step_count"]
        start_time = time.time()

        try:
            # 获取当前页面
            page = await agent.browser_session.get_current_page()
            if page is None:
                logger.warning(f"[Step {step_num}] 智能等待: 无法获取页面对象")
                return

            # 先清理上一步可能遗留的警告元素（页面可能已经变化）
            try:
                await page.evaluate(
                    """
                    () => {
                        const warning = document.getElementById('__slow_load_warning__');
                        if (warning) warning.remove();
                        const style = document.getElementById('__slow_load_warning_style__');
                        if (style) style.remove();
                    }
                """
                )
            except Exception:
                pass  # 忽略清理错误

            # 固定等待指定时间
            total_wait = SMART_WAIT_DETECTION_TIME + SMART_WAIT_RENDER_DELAY
            await asyncio.sleep(total_wait)

            # 等待结束后检测图片加载状态
            try:
                images_status = await page.evaluate(
                    """
                    () => {
                        const images = document.querySelectorAll('img');
                        if (images.length === 0) return { loaded: true, total: 0, pending: 0, pendingImages: [] };

                        let loaded = 0;
                        let pending = 0;
                        let noSrc = 0;
                        const pendingImages = [];

                        for (const img of images) {
                            // 检查图片是否在可视区域内
                            const rect = img.getBoundingClientRect();
                            const isVisible = rect.top < window.innerHeight && rect.bottom > 0 &&
                                              rect.left < window.innerWidth && rect.right > 0;

                            // 只检查可见的图片
                            if (!isVisible) {
                                loaded++;
                                continue;
                            }

                            // 检查是否有有效的 src
                            const hasSrc = img.src && img.src.startsWith('http');

                            if (!hasSrc) {
                                noSrc++;
                                continue;
                            }

                            // 检查图片是否真正加载完成
                            const isLoaded = img.complete &&
                                             img.naturalWidth > 0 &&
                                             img.naturalHeight > 0;

                            if (isLoaded) {
                                loaded++;
                            } else {
                                pending++;
                                // 记录未加载图片的信息
                                pendingImages.push({
                                    src: img.src.substring(0, 100),
                                    alt: img.alt || '',
                                    position: `(${Math.round(rect.left)}, ${Math.round(rect.top)})`
                                });
                            }
                        }

                        return {
                            loaded: pending === 0,
                            total: images.length,
                            pending: pending,
                            loadedCount: loaded,
                            noSrc: noSrc,
                            pendingImages: pendingImages.slice(0, 10)  // 最多返回10个
                        };
                    }
                """
                )

                # 处理返回值
                if isinstance(images_status, str):
                    import json

                    images_status = json.loads(images_status)

                pending_count = images_status.get("pending", 0)
                total_count = images_status.get("total", 0)

                # 如果有未加载完成的图片，记录为慢加载
                if pending_count > 0:
                    # 获取当前 URL
                    current_url = ""
                    try:
                        browser_state = await agent.browser_session.get_browser_state_summary()
                        current_url = browser_state.url if browser_state else ""
                    except Exception:
                        pass

                    slow_load_info = {
                        "step": step_num,
                        "url": current_url,
                        "pending_images": pending_count,
                        "total_images": total_count,
                        "wait_time": total_wait,
                        "details": images_status.get("pendingImages", []),
                    }
                    state["slow_load_detected"].append(slow_load_info)

                    logger.warning(f"[Step {step_num}] 页面加载检测: 发现 {pending_count}/{total_count} 张图片未加载完成 " f"(等待 {total_wait:.1f}s 后)，可能存在性能问题")

                    # 在页面上注入一个可见的错误提示元素，让 LLM 在截图中看到
                    # 这比修改 agent 状态更可靠，因为 LLM 会直接看到截图
                    try:
                        await page.evaluate(
                            f"""
                            () => {{
                                // 先移除已存在的提示元素（每次都重新创建，确保显示最新信息）
                                const existing = document.getElementById('__slow_load_warning__');
                                if (existing) existing.remove();

                                const warning = document.createElement('div');
                                warning.id = '__slow_load_warning__';
                                warning.style.cssText = `
                                    position: fixed;
                                    top: 10px;
                                    right: 10px;
                                    background: linear-gradient(135deg, #ff4d4f 0%, #cf1322 100%);
                                    color: white;
                                    padding: 16px 20px;
                                    border-radius: 8px;
                                    font-size: 16px;
                                    font-weight: bold;
                                    z-index: 2147483647;
                                    box-shadow: 0 4px 20px rgba(255, 77, 79, 0.5), 0 0 0 3px rgba(255, 77, 79, 0.3);
                                    max-width: 400px;
                                    border: 2px solid #fff;
                                    animation: pulse 1s ease-in-out infinite;
                                `;

                                // 添加脉冲动画样式
                                if (!document.getElementById('__slow_load_warning_style__')) {{
                                    const style = document.createElement('style');
                                    style.id = '__slow_load_warning_style__';
                                    style.textContent = `
                                        @keyframes pulse {{
                                            0%, 100% {{ transform: scale(1); opacity: 1; }}
                                            50% {{ transform: scale(1.02); opacity: 0.9; }}
                                        }}
                                    `;
                                    document.head.appendChild(style);
                                }}

                                warning.innerHTML = `
                                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                                        <span style="font-size: 24px; margin-right: 10px;">🚨</span>
                                        <span style="font-size: 18px;">页面加载异常 - 巡检发现问题</span>
                                    </div>
                                    <div style="font-weight: normal; font-size: 14px; line-height: 1.5;
                                        background: rgba(0,0,0,0.2); padding: 10px; border-radius: 4px;">
                                        ⏱️ 等待 <b>{total_wait:.1f}s</b> 后仍有 <b style="color: #ffeb3b;">{pending_count}/{total_count}</b> 张图片未加载完成<br>
                                        📋 这是一个需要记录的性能问题
                                    </div>
                                `;
                                document.body.appendChild(warning);

                                // 注意：不设置自动移除，让警告持续显示直到下一步开始时被清理
                                // 这样确保 LLM 在截图时一定能看到这个警告
                            }}
                        """
                        )
                        logger.info(f"[Step {step_num}] ✅ 已在页面注入慢加载警告提示 (DOM 注入成功)")
                    except Exception as e:
                        logger.warning(f"[Step {step_num}] ❌ 注入慢加载警告失败: {e}")
                else:
                    logger.debug(f"[Step {step_num}] 页面加载检测: 所有 {total_count} 张图片已加载完成")

            except Exception as e:
                logger.debug(f"[Step {step_num}] 页面加载检测异常: {e}")

            wait_time = time.time() - start_time
            state["total_wait_time"] += wait_time
            logger.debug(f"[Step {step_num}] 智能等待完成，本次耗时 {wait_time:.2f}s，累计 {state['total_wait_time']:.2f}s")

        except Exception as e:
            logger.warning(f"[Step {step_num}] 智能等待异常: {e}")

    return smart_wait_hook, state


# DOM 错误检测：Toast/通知/错误提示的关键词和选择器
DOM_ERROR_KEYWORDS_CN = [
    "系统异常",
    "请联系管理员",
    "错误",
    "失败",
    "异常",
    "操作失败",
    "请求失败",
    "服务异常",
    "加载失败",
    "网络错误",
    "服务不可用",
    "超时",
]

DOM_ERROR_KEYWORDS_EN = [
    "error",
    "failed",
    "failure",
    "exception",
    "system error",
    "contact administrator",
    "load failed",
    "network error",
    "service unavailable",
    "timeout",
    "500",
    "502",
    "503",
    "504",
    "404",
    "403",
]


def _create_dom_error_detection_hook(
    is_inspection_task: bool = False,
) -> tuple[Callable, dict]:
    """
    创建 DOM 错误检测的 on_step_end hook

    通过 JavaScript 检测页面中的 Toast、通知、错误提示等元素，
    将检测结果记录到日志中，供后续分析使用。

    Args:
        is_inspection_task: 是否为巡检任务（巡检任务会更严格地检测错误）

    Returns:
        Tuple of:
        - 异步 hook 函数
        - 状态字典（用于跟踪检测到的错误）
    """
    state = {
        "step_count": 0,
        "detected_errors": [],  # 检测到的错误列表
        "last_error": None,
    }

    async def dom_error_detection_hook(agent) -> None:
        """检测页面中的 Toast/错误提示元素"""
        state["step_count"] += 1
        step_num = state["step_count"]

        try:
            # 获取当前页面
            page = await agent.browser_session.get_current_page()
            if page is None:
                return

            # 使用 JavaScript 检测页面中的错误提示元素
            # 这个脚本会检测常见的 Toast/Notification/Alert 组件
            detection_result = await page.evaluate(
                """
                () => {
                    const errors = [];

                    // 错误关键词（中英文）
                    const errorKeywords = [
                        '系统异常', '请联系管理员', '错误', '失败', '异常',
                        '操作失败', '请求失败', '服务异常', '加载失败', '网络错误',
                        '服务不可用', '超时', 'error', 'failed', 'failure',
                        'exception', 'timeout', '500', '502', '503', '504'
                    ];

                    // 常见的 Toast/Notification 选择器
                    const toastSelectors = [
                        // Ant Design
                        '.ant-message', '.ant-notification', '.ant-alert',
                        '.ant-message-notice', '.ant-notification-notice',
                        // Element UI / Element Plus
                        '.el-message', '.el-notification', '.el-alert',
                        '.el-message--error', '.el-notification--error',
                        // 通用选择器
                        '.toast', '.notification', '.alert', '.message',
                        '[class*="toast"]', '[class*="notification"]',
                        '[class*="message-"]', '[class*="alert-"]',
                        '[role="alert"]', '[role="status"]',
                        // 错误样式
                        '.error', '.danger', '.warning',
                        '[class*="error"]', '[class*="danger"]',
                        // 浮层/弹框
                        '.popup', '.modal-error', '.dialog-error'
                    ];

                    // 检测所有匹配的元素
                    for (const selector of toastSelectors) {
                        try {
                            const elements = document.querySelectorAll(selector);
                            for (const el of elements) {
                                // 检查元素是否可见
                                const style = window.getComputedStyle(el);
                                const isVisible = style.display !== 'none' &&
                                                  style.visibility !== 'hidden' &&
                                                  style.opacity !== '0' &&
                                                  el.offsetParent !== null;

                                if (!isVisible) continue;

                                const text = el.innerText || el.textContent || '';
                                const textLower = text.toLowerCase();

                                // 检查是否包含错误关键词
                                for (const keyword of errorKeywords) {
                                    if (textLower.includes(keyword.toLowerCase())) {
                                        // 获取元素位置
                                        const rect = el.getBoundingClientRect();
                                        const position = rect.top < 200 ? 'top' :
                                                        rect.top > window.innerHeight - 200 ? 'bottom' : 'middle';
                                        const horizontalPos = rect.left > window.innerWidth * 0.7 ? 'right' :
                                                              rect.left < window.innerWidth * 0.3 ? 'left' : 'center';

                                        // 检查是否有错误样式（红色）
                                        const hasErrorStyle = style.color.includes('rgb(255') ||
                                                             style.backgroundColor.includes('rgb(255') ||
                                                             el.classList.toString().includes('error') ||
                                                             el.classList.toString().includes('danger');

                                        errors.push({
                                            text: text.trim().substring(0, 200),
                                            keyword: keyword,
                                            selector: selector,
                                            position: `${position}-${horizontalPos}`,
                                            hasErrorStyle: hasErrorStyle,
                                            tagName: el.tagName.toLowerCase()
                                        });
                                        break;  // 一个元素只记录一次
                                    }
                                }
                            }
                        } catch (e) {
                            // 忽略选择器错误
                        }
                    }

                    // 去重（基于文本内容）
                    const uniqueErrors = [];
                    const seenTexts = new Set();
                    for (const err of errors) {
                        const key = err.text.substring(0, 50);
                        if (!seenTexts.has(key)) {
                            seenTexts.add(key);
                            uniqueErrors.push(err);
                        }
                    }

                    return {
                        hasErrors: uniqueErrors.length > 0,
                        errors: uniqueErrors,
                        timestamp: new Date().toISOString()
                    };
                }
            """
            )

            # 处理返回值
            if isinstance(detection_result, str):
                import json

                detection_result = json.loads(detection_result)

            if detection_result and detection_result.get("hasErrors"):
                detected_errors = detection_result.get("errors", [])
                state["detected_errors"].extend(detected_errors)
                state["last_error"] = detected_errors[0] if detected_errors else None

                # 记录检测到的错误（重要：这些信息会在日志中显示，供调试使用）
                for err in detected_errors:
                    error_msg = (
                        f"[Step {step_num}] DOM检测到错误提示: "
                        f"位置={err.get('position')}, "
                        f"关键词='{err.get('keyword')}', "
                        f"内容='{err.get('text', '')[:100]}'"
                    )
                    logger.warning(error_msg)

                    # 如果是巡检任务，将检测结果注入到 agent 的消息历史中
                    # 这样 LLM 在下一步就能看到这个信息
                    if is_inspection_task and hasattr(agent, "message_manager"):
                        try:
                            # 构造提示信息，让 LLM 知道页面有错误
                            hint = f"【系统自动检测】页面{err.get('position', '')}区域发现错误提示: '{err.get('text', '')[:100]}'"
                            # 注入到 agent 的 injected_agent_state
                            if hasattr(agent, "injected_agent_state"):
                                current_state = agent.injected_agent_state or ""
                                agent.injected_agent_state = f"{current_state}\n{hint}"
                        except Exception as e:
                            logger.debug(f"无法注入错误提示到 agent: {e}")

        except Exception as e:
            logger.debug(f"[Step {step_num}] DOM 错误检测异常: {e}")

    return dom_error_detection_hook, state


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
                    logger.error(f"[Step {step_num}] 登录失败次数已达 {max_failures} 次，停止执行。匹配关键词: '{matched_pattern}', 页面标题: '{page_title}'")
                    # 暂停 agent 执行
                    agent.pause()
                    # 抛出异常以确保停止
                    raise LoginFailureError(
                        f"登录失败次数超过限制({max_failures}次)，已停止执行。页面标题: {state['last_failure_reason']}",
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
    execution_id: str = "",
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

        if execution_id and is_interrupt_requested(execution_id):
            raise BrowserExecutionInterruptedError("浏览器执行已中断")

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
    custom_event_callback: Optional[CustomEventCallbackType] = None,
    sensitive_data: Optional[Dict[str, str]] = None,
    masked_task: Optional[str] = None,
    user_data_dir: Optional[str] = None,
    locale: str = "en",
    tool_name: str = "browse_website",
    execution_id: str = "",
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
        # 配置页面加载等待时间，确保截图时页面已完成渲染（避免截到 loading 状态）
        browser_init_kwargs = {
            "executable_path": executable_path,
            "headless": actual_headless,
            "enable_default_extensions": False,
            "user_data_dir": user_data_dir,  # 使用共享的用户数据目录保持会话状态
            # 截图延迟配置：确保页面加载完成后再截图
            "minimum_wait_page_load_time": BROWSER_MIN_WAIT_PAGE_LOAD,  # 默认 1.5 秒
            "wait_for_network_idle_page_load_time": BROWSER_WAIT_NETWORK_IDLE,  # 默认 1.0 秒
        }

        browser = Browser(**browser_init_kwargs)

        # 创建 browser-use agent
        # 判断task中是否已经明确包含了URL信息（使用脱敏后的任务判断，避免泄露）
        # 只有当task中包含完整URL或明确提到该URL时，才认为已包含导航信息
        task_to_check = masked_task or task

        if task_to_check and url.lower() in task_to_check.lower():
            final_task = task or ""
        else:
            final_task = f"首先，导航到 {url} \n 然后，{task}" if task else f"导航到 {url}"

        # 创建步骤回调适配器
        register_callback = _create_step_callback_adapter(step_callback, max_steps, execution_id=execution_id)

        # 回传 browser_use 实际接收任务（final_task），用于前端展示
        if custom_event_callback is not None:
            task_payload = _build_browser_task_event_payload(tool_name=tool_name, url=url, final_task=final_task)
            try:
                if asyncio.iscoroutinefunction(custom_event_callback):
                    await custom_event_callback(task_payload)
                else:
                    custom_event_callback(task_payload)
            except Exception as e:
                logger.warning(f"browser task custom event 回调执行失败: {e}")

        # 创建登录失败检测 hook（仅当任务包含账号密码时启用）
        has_credentials = sensitive_data is not None and len(sensitive_data) > 0
        login_failure_hook, login_state = _create_login_failure_hook(has_credentials)

        # 检测是否为巡检任务（用于 DOM 错误检测）
        inspection_keywords = [
            "巡检",
            "检查",
            "健康检查",
            "功能验证",
            "inspect",
            "check",
            "health check",
            "verification",
            "audit",
            "patrol",
        ]
        task_lower = (task or "").lower()
        is_inspection_task = any(kw in task_lower for kw in inspection_keywords)

        # 创建 DOM 错误检测 hook（仅当启用且为巡检任务时）
        dom_error_hook = None
        dom_error_state = None
        if BROWSER_DOM_ERROR_DETECTION_ENABLED and is_inspection_task:
            dom_error_hook, dom_error_state = _create_dom_error_detection_hook(is_inspection_task=True)
            logger.info("DOM 错误检测已启用（巡检任务）")

        # 组合多个 on_step_end hooks
        async def combined_step_end_hook(agent) -> None:
            """组合执行所有 on_step_end hooks"""
            # 先执行 DOM 错误检测（不会抛异常）
            if dom_error_hook:
                await dom_error_hook(agent)
            # 再执行登录失败检测（可能抛 LoginFailureError）
            if has_credentials:
                await login_failure_hook(agent)

        # 创建智能等待 hook（仅当启用时）
        smart_wait_hook = None
        smart_wait_state = None
        if BROWSER_SMART_WAIT_ENABLED:
            smart_wait_hook, smart_wait_state = _create_smart_wait_hook()
            logger.info(f"智能等待已启用: 固定等待 {SMART_WAIT_DETECTION_TIME:.1f}s 后检测加载状态")

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
8. 重要 - 页面异常检测规则（仅巡检任务适用）：
   【触发条件】：仅当任务包含"巡检"、"检查"、"健康检查"、"功能验证"等关键词时，才需要执行此规则。
   普通浏览、数据提取等任务无需执行此规则，页面弹框不影响正常操作流程。

   在巡检任务中，必须判断页面是否存在异常。以下情况必须记录为【异常】：

   (1) 错误弹框/提示（必须检查，重点关注页面右上角区域）：
        - 红色背景、红色边框、红色文字的弹框、Toast、通知、Alert
        - 带有红色图标（❌、⊗、×、圆形感叹号）的 Toast 或通知，即使背景是浅色
        - 包含以下关键词的任何提示（即使样式不明显也必须识别）：
          * 中文：系统异常、请联系管理员、错误、失败、异常、操作失败、请求失败、服务异常
          * 英文：Error、Failed、Exception、Fail、System Error、Contact Administrator
        - 包含 HTTP 状态码的提示：500、502、503、504、404、403、超时、timeout
        - 页面右上角的 Toast/通知条（这是最常见的错误提示位置，必须仔细检查）
        - 页面中央、底部出现的错误通知条
        - 感叹号图标（⚠️、❗、!）配合的警告/错误提示

    (2) 页面加载失败：
        - 页面显示"加载失败"、"网络错误"、"服务不可用"、"请求失败"
        - 页面长时间显示空白、骨架屏、加载动画不消失
        - 出现"重试"、"刷新"、"重新加载"按钮提示
        - 页面内容区域显示"暂无数据"配合错误图标

    (3) 页面加载速度过慢 / 内容未加载完成（重要 - 必须仔细检查）：
        - 【卡片/列表检查】：如果页面是卡片列表或网格布局，必须检查每张卡片：
          * 有些卡片有缩略图，有些卡片是空白/纯色背景 → 记录为【异常 - 部分内容未加载】
          * 卡片内只有文字标题，图片区域是空白 → 异常
          * 对比：正常的卡片应该都有完整的缩略图/预览图
        - 【通用 loading 样式】：
          * 旋转图标/spinner（圆形旋转动画）
          * 骨架屏（灰色占位块）
          * 进度条动画
          * "加载中..."、"Loading..." 文字提示
        - 注意：这是性能问题，需要单独标注为【异常 - 页面加载速度过慢】或【异常 - 部分内容未加载】
        - 可继续执行后续检查，但必须记录此异常

    (4) 系统错误展示：
       - 页面直接显示报错堆栈信息（Stack Trace）
       - 显示 JSON 格式的错误响应
       - 控制台错误直接展示在页面上

   【判断为正常】：页面主要内容正常显示，无上述任何异常情况

    【记录格式】：在 memory 中记录每个页面状态，如：
    - "首页: 正常"
    - "监控: 异常 - 右上角出现红色提示'数据加载失败'"
    - "告警: 异常 - 页面中央弹框显示'服务器错误 500'"
    - "数字大屏: 异常 - 部分内容未加载（13张卡片中有4张缩略图为空白）"
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
8. CRITICAL - Page Error Detection:
    [TRIGGER CONDITION]: Only apply this rule when task contains keywords like "inspect", "check", "health check", "verification", "audit", "patrol".
    For normal browsing or data extraction tasks, this rule does NOT apply - page popups should not interrupt normal operation flow.

    When inspecting or checking page functionality, you MUST detect page anomalies. The following situations MUST be recorded as [ABNORMAL]:

   (1) Error Popups/Notifications (MUST CHECK, pay special attention to the top-right corner):
        - Popups, Toasts, Notifications, Alerts with red background, red border, or red text
        - Toasts or notifications with red icons (❌, ⊗, ×, circled exclamation), even if background is light-colored
        - Any prompt containing these keywords (must detect even if styling is subtle):
          * Chinese: 系统异常, 请联系管理员, 错误, 失败, 异常, 操作失败, 请求失败, 服务异常
          * English: Error, Failed, Exception, Fail, Failure, System Error, Contact Administrator
        - Prompts containing HTTP status codes: 500, 502, 503, 504, 404, 403, timeout
        - Toast/notification bars at top-right corner (most common error location, must check carefully)
        - Error notification bars at center or bottom of page
        - Warning/error prompts with exclamation icons (⚠️, ❗, !)

    (2) Page Load Failures:
        - Page displays "Load Failed", "Network Error", "Service Unavailable", "Request Failed"
        - Page shows blank content, skeleton screen, or loading animation that never completes
        - "Retry", "Refresh", "Reload" button prompts appear
        - Content area shows "No Data" with error icon

    (3) Slow Page Load / Incomplete Content (IMPORTANT - Must check carefully):
        - [Card/List Check]: If page shows card list or grid layout, must inspect each card:
          * Some cards have thumbnails, some cards are blank/solid color → record as [ABNORMAL - Partial content not loaded]
          * Card only shows text title, image area is blank → Abnormal
          * Compare: Normal cards should all have complete thumbnails/preview images
        - [Common loading styles]:
          * Spinning icons/spinners (circular rotating animation)
          * Skeleton screens (gray placeholder blocks)
          * Progress bar animations
          * "Loading...", "加载中..." text prompts
        - Note: This is a performance issue, mark as [ABNORMAL - Slow page load] or [ABNORMAL - Partial content not loaded]
        - Continue with subsequent checks, but must record this anomaly

    (4) System Error Display:
        - Page directly displays error stack traces
        - JSON format error responses shown on page
        - Console errors displayed directly on page

    [NORMAL]: Main page content displays correctly without any of the above anomalies

    [Recording Format]: Record each page status in memory, e.g.:
    - "Homepage: Normal"
    - "Monitor: Abnormal - Red toast appeared at top-right showing 'Data load failed'"
    - "Alerts: Abnormal - Modal in center showing 'Server Error 500'"
    - "Digital Dashboard: Abnormal - Partial content not loaded (4 of 13 card thumbnails are blank)"
"""

        # 创建 browser-use agent（带回调支持和优化配置）
        browser_agent = BrowserAgent(
            task=final_task,
            llm=llm,
            browser=browser,
            register_new_step_callback=register_callback,
            extend_system_message=extend_system_message,
            max_actions_per_step=5,  # 每步最多5个动作，避免过度操作
            max_failures=2,  # 最大失败重试次数
            sensitive_data=sensitive_data,  # 敏感数据脱敏
            llm_timeout=BROWSER_LLM_TIMEOUT,  # LLM 调用超时
            step_timeout=BROWSER_STEP_TIMEOUT,  # 单步执行超时（包含导航等待）
        )

        # 执行浏览任务（使用组合的 on_step_end hook 和智能等待 hook）
        # combined_step_end_hook 包含: DOM 错误检测 + 登录失败检测
        agent_result = await browser_agent.run(
            max_steps=max_steps,
            on_step_start=smart_wait_hook,
            on_step_end=combined_step_end_hook if (dom_error_hook or has_credentials) else None,
        )
        # 提取结果
        final_result = agent_result.final_result()
        result_text = str(final_result) if final_result else "未获取到有效结果"

        # 如果 DOM 错误检测发现了错误，将其附加到结果中
        dom_detected_errors = []
        if dom_error_state and dom_error_state.get("detected_errors"):
            dom_detected_errors = [f"[DOM检测] {err.get('position', '')}: {err.get('text', '')[:100]}" for err in dom_error_state["detected_errors"]]
            logger.info(f"DOM 错误检测结果: 发现 {len(dom_detected_errors)} 个错误提示")

        # 如果智能等待检测到慢加载，将其附加到结果中
        slow_load_detected = []
        if smart_wait_state and smart_wait_state.get("slow_load_detected"):
            slow_load_detected = [
                f"[慢加载] Step {info.get('step')}: {info.get('pending_images')}/{info.get('total_images')} 张图片未加载 (URL: {info.get('url', '')[:80]})"
                for info in smart_wait_state["slow_load_detected"]
            ]
            logger.info(f"慢加载检测结果: 发现 {len(slow_load_detected)} 个页面加载过慢")

        return {
            "success": agent_result.is_successful(),
            "content": result_text,
            "url": url,
            "task": task,
            "has_errors": agent_result.has_errors(),
            "errors": [str(err) for err in agent_result.errors() if err],
            "steps_taken": agent_result.number_of_steps(),
            "dom_detected_errors": dom_detected_errors,  # DOM 检测到的错误
            "slow_load_detected": slow_load_detected,  # 慢加载检测结果
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

    except BrowserExecutionInterruptedError as e:
        logger.info(f"浏览器执行被中断: {e}")
        return {
            "success": False,
            "content": None,
            "url": url,
            "task": task,
            "has_errors": True,
            "errors": [str(e)],
            "steps_taken": 0,
            "interrupted": True,
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

    **[警告] 重要：一次调用完成所有任务 [警告]**
    此工具内置完整的AI Agent，能够自动执行多步骤的复杂任务序列。
    请在一次调用中描述完整的任务流程，不要拆分成多次调用！
    每次调用结束后浏览器会关闭，多次调用会导致登录状态丢失。

    **[凭据] 凭据传递方式（必须使用 username/password 参数）：**
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
    - [X] task="输入用户名admin和密码123456登录" （凭据不要写在task里！）
    - [X] 拆分成多次调用（会丢失登录状态）

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
    - [警告] 不要将连续任务拆分成多次调用，这会导致登录状态丢失
    - [凭据] 凭据必须通过 username/password 参数传递，不要写在 task 中
    """
    configurable = config.get("configurable", {}) if config else {}
    llm_config = configurable.get("graph_request")
    step_callback: Optional[StepCallbackType] = configurable.get("browser_step_callback")
    custom_event_callback: Optional[CustomEventCallbackType] = configurable.get("browser_custom_event_callback")
    execution_id = configurable.get("execution_id") or getattr(llm_config, "thread_id", "")
    forced_base_task = configurable.get("browser_use_base_task")
    forced_user_message = configurable.get("browser_use_user_message")
    force_browser_task = configurable.get("browser_use_force_task", False)
    try:
        # 验证URL
        _validate_url(url)
        llm = ChatOpenAI(
            model=llm_config.model,
            temperature=0.3,
            api_key=llm_config.openai_api_key,
            base_url=llm_config.openai_api_base,
        )
        # logger.info(f"task: {task}\n username: {username}\n password: {password}")

        original_llm_task = task
        if force_browser_task:
            task = _build_forced_browser_task(
                base_task=forced_base_task,
                user_message=forced_user_message,
                llm_task=task,
            )

        # 从独立参数构建 sensitive_data（凭据应通过 username/password 参数传递）
        sensitive_data = _build_sensitive_data(username=username, password=password)
        task = _apply_secret_placeholders(task, sensitive_data)

        # 如果有凭据，在 task 开头添加提示，让浏览器 agent 知道有凭据可用
        masked_task = task
        if sensitive_data and task:
            credential_hint = "【凭据已提供】用户名: <secret>x_username</secret>"
            if "x_password" in sensitive_data:
                credential_hint += ", 密码: <secret>x_password</secret>"
            masked_task = f"{credential_hint}。{task}"
            logger.info("凭据已通过 username/password 参数传递: x_username=***, x_password=***")

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
                custom_event_callback=custom_event_callback,
                sensitive_data=sensitive_data,
                masked_task=masked_task,
                user_data_dir=user_data_dir,
                locale=locale,
                tool_name="browse_website",
                execution_id=execution_id,
            )
        )
        if force_browser_task and isinstance(result, dict):
            result["task_source"] = "forced_from_skill_prompt"
            result["llm_task_original"] = original_llm_task
        return result

    except ValueError as e:
        return {"success": False, "error": str(e), "url": url}
    except Exception as e:
        logger.exception(f"浏览器操作异常: {e}")
        return {"success": False, "error": str(e), "url": url}


@tool()
def extract_webpage_info(
    url: str,
    selectors: Optional[Dict[str, str]] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
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

    4. 提取需要登录的页面信息：
       - url="https://admin.example.com/dashboard"
       - username="admin"
       - password="123456"
       - selectors={"stats": "统计数据", "alerts": "告警信息"}

    Args:
        url (str): 目标网站URL（必填）
        selectors (dict, optional): 要提取的信息字典
            键：字段名，值：字段描述
        username (str, optional): 登录用户名。当页面需要登录时使用
        password (str, optional): 登录密码。当页面需要登录时使用
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
        custom_event_callback: Optional[CustomEventCallbackType] = configurable.get("browser_custom_event_callback")
        execution_id = configurable.get("execution_id") or getattr(llm_config, "thread_id", "")

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

        # 从独立参数构建 sensitive_data（凭据应通过 username/password 参数传递）
        sensitive_data = _build_sensitive_data(username=username, password=password)

        # 如果有凭据，在 task 开头添加提示，让浏览器 agent 知道有凭据可用
        masked_task = task
        if sensitive_data and task:
            credential_hint = "【凭据已提供】用户名: <secret>x_username</secret>"
            if "x_password" in sensitive_data:
                credential_hint += ", 密码: <secret>x_password</secret>"
            masked_task = f"{credential_hint}。{task}"
            logger.info("凭据已通过 username/password 参数传递: x_username=***, x_password=***")

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
                custom_event_callback=custom_event_callback,
                sensitive_data=sensitive_data,
                masked_task=masked_task,
                user_data_dir=user_data_dir,
                locale=locale,
                tool_name="extract_webpage_info",
                execution_id=execution_id,
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
