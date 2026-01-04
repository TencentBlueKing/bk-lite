"""浏览器操作工具 - 使用Browser-Use进行网页自动化"""
import asyncio
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from browser_use import Agent
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

# 安全配置
DEFAULT_TIMEOUT = 60
MAX_RETRIES = 2


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


@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=4, max=10), reraise=True)
async def _browse_website_async(
    url: str,
    task: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    llm=None,
) -> Dict[str, Any]:
    """
    异步浏览网站并执行任务

    Args:
        url: 目标网站URL
        task: 可选的任务描述，如"提取标题"、"点击登录按钮"等
        timeout: 超时时间（秒）
        llm: LLM实例，如果不提供则使用默认的 gpt-4o

    Returns:
        Dict[str, Any]: 执行结果
            - success: 是否成功
            - content: 页面内容或提取的信息
            - error: 错误信息（如果失败）

    Raises:
        ValueError: 参数错误或执行失败
    """
    try:
        logger.info(f"开始浏览网站: {url}, 任务: {task or '无特定任务'}")

        # 如果没有提供LLM，使用默认的
        if llm is None:
            llm = ChatOpenAI(model="gpt-4o")
            logger.debug("使用默认LLM: gpt-4o")
        else:
            logger.debug(f"使用自定义LLM: {llm.__class__.__name__}")

        # 创建Browser-Use Agent
        agent = Agent(
            task=task or f"访问 {url} 并提取页面主要内容",
            llm=llm,
        )

        # 执行浏览任务
        result = await agent.run()

        logger.info(f"浏览任务完成: {url}")

        # 提取结果
        if result:
            return {
                "success": True,
                "content": str(result),
                "url": url,
                "task": task,
            }
        else:
            return {
                "success": False,
                "error": "未获取到有效结果",
                "url": url,
            }

    except ImportError as e:
        error_msg = "browser-use 包未安装，请先安装: pip install browser-use"
        logger.error(error_msg)
        raise ValueError(error_msg) from e

    except Exception as e:
        error_msg = f"浏览器操作失败: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg) from e


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
def browse_website(url: str, task: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT, config: RunnableConfig = None) -> Dict[str, Any]:
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
        timeout (int): 超时时间（秒），默认60秒
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
    - 确保任务描述清晰具体
    - 自动使用调用它的Agent的LLM，如果没有则使用 gpt-4o

    **与其他工具的区别：**
    - fetch_html: 仅获取静态HTML，不执行JavaScript
    - http_get: 仅发送HTTP请求，不渲染页面
    - browse_website: 完整的浏览器环境，可执行复杂交互
    """
    try:
        # 验证URL
        _validate_url(url)

        # 记录日志
        user_id = config.get("configurable", {}).get("user_id", "unknown") if config else "unknown"
        logger.info(f"用户:[{user_id}] 执行工具[浏览网站], URL:[{url}], 任务:[{task or '无'}]")

        # 尝试从 config 中获取 LLM 实例
        llm = None
        if config and "configurable" in config:
            llm = config["configurable"].get("llm")

        # 执行异步浏览任务
        result = _run_async_task(
            _browse_website_async(
                url=url,
                task=task,
                timeout=timeout,
                llm=llm,
            )
        )

        logger.info(f"用户:[{user_id}] 工具执行完成, 成功:[{result.get('success')}]")
        return result

    except ValueError as e:
        error_msg = str(e)
        logger.error(f"参数验证失败: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "url": url,
        }
    except Exception as e:
        error_msg = f"浏览器操作异常: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "url": url,
        }


@tool()
def extract_webpage_info(
    url: str, selectors: Optional[Dict[str, str]] = None, timeout: int = DEFAULT_TIMEOUT, config: RunnableConfig = None
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
        timeout (int): 超时时间（秒），默认60秒
        config (RunnableConfig): 工具配置（自动传递）

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
        # 验证URL
        _validate_url(url)

        # 构建提取任务
        if selectors:
            task_parts = ["从页面中提取以下信息："]
            for field, description in selectors.items():
                task_parts.append(f"- {field}: {description}")
            task = "\n".join(task_parts)
        else:
            task = "提取页面的主要内容，包括标题、正文和关键信息"

        # 记录日志
        user_id = config.get("configurable", {}).get("user_id", "unknown") if config else "unknown"
        logger.info(f"用户:[{user_id}] 执行工具[提取网页信息], URL:[{url}]")

        # 尝试从 config 中获取 LLM 实例
        llm = None
        if config and "configurable" in config:
            llm = config["configurable"].get("llm")

        # 执行浏览任务
        result = _run_async_task(
            _browse_website_async(
                url=url,
                task=task,
                timeout=timeout,
                llm=llm,
            )
        )

        if result.get("success"):
            return {
                "success": True,
                "data": result.get("content"),
                "url": url,
                "selectors": selectors,
            }
        else:
            return result

    except ValueError as e:
        error_msg = str(e)
        logger.error(f"参数验证失败: {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "url": url,
        }
    except Exception as e:
        error_msg = f"信息提取异常: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "url": url,
        }
