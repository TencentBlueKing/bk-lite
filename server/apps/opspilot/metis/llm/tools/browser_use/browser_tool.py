"""浏览器操作工具 - 使用Browser-Use进行网页自动化"""

import asyncio
import os
import re
from typing import Any, Awaitable, Callable, Dict, Optional, TypedDict
from urllib.parse import urlparse

from browser_use import Agent as BrowserAgent
from browser_use import Browser
from browser_use.agent.views import AgentOutput
from browser_use.browser.views import BrowserStateSummary
from browser_use.llm import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

# 安全配置
DEFAULT_TIMEOUT = 60
MAX_RETRIES = 4


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
        (
            r"(密码\s*(?:是|为)?\s*[:：]?\s*)(\S+?)(\s*[（(].*?[)）])?(?=[\s,，。、;；]|$)",
            "x_password",
        ),
        # 英文：password: xxx / password=xxx / password xxx
        (
            r"(password\s*[:=]?\s*[\"']?)(\S+?)([\"']?)(?=[\s,，。;；]|$)",
            "x_password",
        ),
        # pwd: xxx / pwd=xxx / pwd xxx
        (r"(pwd\s*[:=]?\s*[\"']?)(\S+?)([\"']?)(?=[\s,，。;；]|$)", "x_password"),
        # === 用户名相关 ===
        # 中文：用户名是xxx / 账号是xxx / 用户名：xxx 等
        # 注意：需要在"和"、"以及"、"密码"等词前停止匹配
        (
            r"((?:用户名|用户|账号|帐号)\s*(?:是|为)?\s*[:：]?\s*)(\S+?)()(?=[\s,，。、;；]|和|以及|密码|pwd|password|$)",
            "x_username",
        ),
        # 英文：username / user + 分隔符 + 值
        (
            r"((?:username|user)\s*[:=]?\s*[\"']?)(\S+?)([\"']?)(?=[\s,，。;；]|and|password|pwd|$)",
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
            llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
        executable_path = os.getenv("EXECUTABLE_PATH", None) or None
        # 初始化 Browser
        browser = Browser(
            executable_path=executable_path,
            headless=headless,
            # headless=False,
            enable_default_extensions=False,
        )

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

        # 扩展系统提示 - 简化版，核心规则已在任务前缀中
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
        )

        # 执行浏览任务
        agent_result = await browser_agent.run(max_steps=max_steps)
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
def browse_website(url: str, task: Optional[str] = None, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    使用AI驱动的浏览器打开网站并执行操作

    **何时使用此工具：**
    - 需要与网页进行交互（点击、填表等）
    - 需要从动态加载的网页中提取信息
    - 需要执行复杂的网页自动化任务
    - 普通的HTTP请求无法获取所需内容

    **工具能力：**
    - AI理解任务描述，自动执行网页操作
    - 处理JavaScript渲染的动态内容
    - 支持点击、输入、滚动等交互
    - 智能提取页面信息
    - 自动处理常见的网页元素
    - 自动使用调用它的Agent的LLM模型
    - 支持流式传递执行进度（通过 step_callback）

    **典型使用场景：**
    1. 提取页面内容：
       - url="https://example.com"
       - task="提取页面标题和主要内容"

    2. 执行搜索操作：
       - url="https://www.google.com"
       - task="搜索'Python教程'并返回前3个结果"

    3. 表单填写：
       - url="https://example.com/form"
       - task="填写用户名为'test'，密码为'test123'，然后点击登录"

    4. 数据提取：
       - url="https://example.com/products"
       - task="提取所有产品的名称和价格"

    Args:
        url (str): 目标网站URL（必填）
        task (str, optional): 任务描述，告诉AI需要做什么
        config (RunnableConfig): 工具配置（自动传递）
            - 可通过 config["configurable"]["browser_step_callback"] 传递步骤回调函数

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
    - 确保任务描述清晰具体
    - 自动使用调用它的Agent的LLM，如果没有则使用 gpt-4o

    **与其他工具的区别：**
    - fetch_html: 仅获取静态HTML，不执行JavaScript
    - http_get: 仅发送HTTP请求，不渲染页面
    - browse_website: 完整的浏览器环境，可执行复杂交互
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
        sensitive_data, masked_task = _extract_sensitive_data(task) if task else (None, task)
        result = _run_async_task(
            _browse_website_async(
                url=url,
                task=masked_task,
                llm=llm,
                step_callback=step_callback,
                sensitive_data=sensitive_data,
                masked_task=masked_task,
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
        if selectors:
            task_parts = ["从页面中提取以下信息："]
            for field, description in selectors.items():
                task_parts.append(f"- {field}: {description}")
            task = "\n".join(task_parts)
        else:
            task = "提取页面的主要内容，包括标题、正文和关键信息"

        sensitive_data, masked_task = _extract_sensitive_data(task) if task else (None, task)

        result = _run_async_task(
            _browse_website_async(
                url=url,
                task=masked_task,
                llm=llm,
                step_callback=step_callback,
                sensitive_data=sensitive_data,
                masked_task=masked_task,
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
