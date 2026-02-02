"""高级Fetch工具 - 获取和格式化Web内容"""

from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.fetch.formatter import clean_whitespace, extract_main_content, html_to_markdown, html_to_text, parse_json
from apps.opspilot.metis.llm.tools.fetch.http import _http_get_impl
from apps.opspilot.metis.llm.tools.fetch.utils import is_valid_json_content_type, prepare_fetch_config, truncate_content


@tool()
def fetch_html(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    max_length: Optional[int] = None,
    start_index: int = 0,
    extract_main: bool = False,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    获取网页的HTML内容

    **何时使用此工具：**
    - 获取网页的原始HTML
    - 需要完整的HTML结构
    - 进行HTML解析或分析

    **工具能力：**
    - 获取完整的HTML内容
    - 支持分段获取（通过start_index和max_length）
    - 可选择性提取主要内容区域
    - 自动处理编码
    - 支持Bearer Token认证（通过独立参数传递）

    **🔐 Bearer Token 认证（推荐使用独立参数）：**
    当需要Bearer Token认证时，必须使用 bearer_token 参数：

    ```python
    # ✅ 正确示例
    fetch_html(
        url="https://api.example.com/page",
        bearer_token="your_token_here"
    )
    ```

    **典型使用场景：**
    1. 获取网页HTML：
       - url="https://example.com"
    2. 分段获取大页面：
       - max_length=5000, start_index=0  # 第一段
       - max_length=5000, start_index=5000  # 第二段
    3. 提取主要内容：
       - extract_main=True  # 移除导航、侧边栏等

    Args:
        url (str): 网页URL（必填）
        headers (dict, optional): 自定义请求头（不要在这里放 Authorization，请用 bearer_token 参数）
        max_length (int, optional): 最大内容长度，None表示不限制
        start_index (int): 内容起始位置，默认0
        extract_main (bool): 是否提取主要内容区域，默认False
        bearer_token (str, optional): Bearer Token，用于API认证
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: HTML内容和元信息
            - success (bool): 是否成功
            - content (str): HTML内容
            - url (str): 最终URL
            - total_length (int): 总长度
            - truncated (bool): 是否被截断
            - start_index (int): 起始位置
            - end_index (int): 结束位置
            - remaining (int): 剩余字符数

    **配合其他工具使用：**
    - 获取HTML后可用fetch_txt转换为纯文本
    - 获取HTML后可用fetch_markdown转换为Markdown

    **注意事项：**
    - 大页面建议使用max_length分段获取
    - extract_main可能误删某些内容，请谨慎使用
    - 🔐 Bearer Token 必须通过 bearer_token 参数传递
    """
    fetch_config = prepare_fetch_config(config)

    # 如果未指定max_length，使用配置的默认值
    if max_length is None:
        max_length = fetch_config.get("default_limit", 5000)

    # 发送HTTP GET请求
    response = _http_get_impl(url, headers=headers, bearer_token=bearer_token, config=config)

    if not response.get("success"):
        return response

    html_content = response["content"]

    # 如果需要，提取主要内容
    if extract_main:
        html_content = extract_main_content(html_content)

    # 截取内容
    result = truncate_content(html_content, max_length, start_index)

    return {
        "success": True,
        "content": result["content"],
        "url": response["url"],
        "total_length": result["total_length"],
        "truncated": result["truncated"],
        "start_index": result["start_index"],
        "end_index": result["end_index"],
        "remaining": result["remaining"],
    }


@tool()
def fetch_txt(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    max_length: Optional[int] = None,
    start_index: int = 0,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    获取网页内容并转换为纯文本（移除HTML标签）

    **何时使用此工具：**
    - 只需要网页的文本内容
    - 不需要HTML标签和格式
    - 提取可读的文本信息

    **工具能力：**
    - 自动移除HTML标签、脚本、样式
    - 清理多余空白
    - 保留文本结构
    - 支持分段获取
    - 支持Bearer Token认证（通过独立参数传递）

    **🔐 Bearer Token 认证（推荐使用独立参数）：**
    当需要Bearer Token认证时，必须使用 bearer_token 参数：

    ```python
    # ✅ 正确示例
    fetch_txt(
        url="https://api.example.com/page",
        bearer_token="your_token_here"
    )
    ```

    **典型使用场景：**
    1. 提取网页文本内容：
       - url="https://example.com/article"
    2. 获取文档内容：
       - url="https://docs.example.com/guide"

    Args:
        url (str): 网页URL（必填）
        headers (dict, optional): 自定义请求头（不要在这里放 Authorization，请用 bearer_token 参数）
        max_length (int, optional): 最大内容长度
        start_index (int): 内容起始位置，默认0
        bearer_token (str, optional): Bearer Token，用于API认证
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 纯文本内容和元信息
            - success (bool): 是否成功
            - content (str): 纯文本内容
            - url (str): 最终URL
            - total_length (int): 总长度
            - truncated (bool): 是否被截断
            - start_index (int): 起始位置
            - end_index (int): 结束位置
            - remaining (int): 剩余字符数

    **注意事项：**
    - 🔐 Bearer Token 必须通过 bearer_token 参数传递
    """
    fetch_config = prepare_fetch_config(config)

    if max_length is None:
        max_length = fetch_config.get("default_limit", 5000)

    # 获取HTML
    response = _http_get_impl(url, headers=headers, bearer_token=bearer_token, config=config)

    if not response.get("success"):
        return response

    # 转换为纯文本
    text_content = html_to_text(response["content"])

    # 清理空白
    text_content = clean_whitespace(text_content)

    # 截取内容
    result = truncate_content(text_content, max_length, start_index)

    return {
        "success": True,
        "content": result["content"],
        "url": response["url"],
        "total_length": result["total_length"],
        "truncated": result["truncated"],
        "start_index": result["start_index"],
        "end_index": result["end_index"],
        "remaining": result["remaining"],
    }


@tool()
def fetch_markdown(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    max_length: Optional[int] = None,
    start_index: int = 0,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    获取网页内容并转换为Markdown格式

    **何时使用此工具：**
    - 需要保留内容结构和格式
    - 转换网页为Markdown文档
    - 提取格式化的文本内容

    **工具能力：**
    - 将HTML转换为Markdown
    - 保留标题、列表、链接等结构
    - 移除脚本和样式
    - 支持分段获取
    - 支持Bearer Token认证（通过独立参数传递）

    **🔐 Bearer Token 认证（推荐使用独立参数）：**
    当需要Bearer Token认证时，必须使用 bearer_token 参数：

    ```python
    # ✅ 正确示例
    fetch_markdown(
        url="https://api.example.com/page",
        bearer_token="your_token_here"
    )
    ```

    **典型使用场景：**
    1. 转换文档页面：
       - url="https://docs.example.com/guide"
    2. 提取文章内容：
       - url="https://blog.example.com/post/123"

    Args:
        url (str): 网页URL（必填）
        headers (dict, optional): 自定义请求头（不要在这里放 Authorization，请用 bearer_token 参数）
        max_length (int, optional): 最大内容长度
        start_index (int): 内容起始位置，默认0
        bearer_token (str, optional): Bearer Token，用于API认证
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: Markdown内容和元信息
            - success (bool): 是否成功
            - content (str): Markdown内容
            - url (str): 最终URL
            - total_length (int): 总长度
            - truncated (bool): 是否被截断
            - start_index (int): 起始位置
            - end_index (int): 结束位置
            - remaining (int): 剩余字符数

    **注意事项：**
    - 🔐 Bearer Token 必须通过 bearer_token 参数传递
    """
    fetch_config = prepare_fetch_config(config)

    if max_length is None:
        max_length = fetch_config.get("default_limit", 5000)

    # 获取HTML
    response = _http_get_impl(url, headers=headers, bearer_token=bearer_token, config=config)

    if not response.get("success"):
        return response

    # 转换为Markdown
    markdown_content = html_to_markdown(response["content"])

    # 清理空白
    markdown_content = clean_whitespace(markdown_content)

    # 截取内容
    result = truncate_content(markdown_content, max_length, start_index)

    return {
        "success": True,
        "content": result["content"],
        "url": response["url"],
        "total_length": result["total_length"],
        "truncated": result["truncated"],
        "start_index": result["start_index"],
        "end_index": result["end_index"],
        "remaining": result["remaining"],
    }


@tool()
def fetch_json(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    max_length: Optional[int] = None,
    start_index: int = 0,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    获取JSON数据

    **何时使用此工具：**
    - 调用返回JSON的API
    - 获取JSON配置文件
    - 获取结构化数据

    **工具能力：**
    - 自动解析JSON
    - 验证JSON格式
    - 返回Python字典对象
    - 支持分段获取（针对JSON字符串）
    - 支持Bearer Token认证（通过独立参数传递）

    **🔐 Bearer Token 认证（推荐使用独立参数）：**
    当需要Bearer Token认证时，必须使用 bearer_token 参数：

    ```python
    # ✅ 正确示例
    fetch_json(
        url="https://api.example.com/users",
        bearer_token="your_token_here"
    )

    # ❌ 错误示例 - 不要这样做
    fetch_json(
        url="https://api.example.com/users",
        headers={"Authorization": "Bearer your_token"}  # Token可能被脱敏为***
    )
    ```

    **典型使用场景：**
    1. 获取API数据：
       - url="https://api.example.com/users"
    2. 获取配置文件：
       - url="https://example.com/config.json"
    3. 获取数据源：
       - url="https://data.example.com/dataset.json"
    4. 调用需要认证的API：
       - url="https://api.example.com/data", bearer_token="your_token"

    Args:
        url (str): JSON资源URL（必填）
        headers (dict, optional): 自定义请求头（不要在这里放 Authorization，请用 bearer_token 参数）
        max_length (int, optional): 最大内容长度（针对JSON字符串）
        start_index (int): 内容起始位置，默认0
        bearer_token (str, optional): Bearer Token，用于API认证
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: JSON数据和元信息
            - success (bool): 是否成功
            - data (dict or list): 解析后的JSON数据
            - content (str): JSON字符串（如果被截断）
            - url (str): 最终URL
            - total_length (int): JSON字符串总长度
            - truncated (bool): 是否被截断

    **注意事项：**
    - 如果响应不是有效的JSON，会返回错误
    - 被截断的JSON字符串可能无法解析，建议不截断或增加max_length
    - 🔐 Bearer Token 必须通过 bearer_token 参数传递
    """
    fetch_config = prepare_fetch_config(config)

    if max_length is None:
        max_length = fetch_config.get("default_limit", 5000)

    # 获取内容
    response = _http_get_impl(url, headers=headers, bearer_token=bearer_token, config=config)

    if not response.get("success"):
        return response

    json_str = response["content"]

    # 验证Content-Type
    content_type = response.get("content_type", "")
    if not is_valid_json_content_type(content_type):
        # 尝试解析，如果失败则警告
        try:
            parse_json(json_str)
        except Exception:
            return {
                "success": False,
                "error": f"响应的Content-Type不是JSON: {content_type}",
                "url": response["url"],
            }

    # 截取内容（如果需要）
    result = truncate_content(json_str, max_length, start_index)

    # 尝试解析JSON
    try:
        json_data = parse_json(result["content"])
        return {
            "success": True,
            "data": json_data,
            "url": response["url"],
            "total_length": result["total_length"],
            "truncated": result["truncated"],
        }
    except Exception as e:
        # 如果解析失败且内容被截断，返回原始字符串
        if result["truncated"]:
            return {
                "success": True,
                "content": result["content"],
                "url": response["url"],
                "total_length": result["total_length"],
                "truncated": True,
                "warning": f"JSON被截断，无法解析: {str(e)}",
                "start_index": result["start_index"],
                "end_index": result["end_index"],
                "remaining": result["remaining"],
            }
        else:
            return {
                "success": False,
                "error": f"JSON解析失败: {str(e)}",
                "url": response["url"],
            }
