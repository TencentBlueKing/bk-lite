"""HTTP请求工具 - 使用requests库"""

from typing import Any, Dict, Optional, Union

import requests
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.fetch.utils import (
    format_error_response,
    parse_content_type_encoding,
    prepare_fetch_config,
    prepare_headers,
    validate_url,
)

# ============================================================================
# 内部实现函数 (供 fetch.py 等模块直接调用)
# ============================================================================


def _http_get_impl(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    HTTP GET 请求的内部实现。

    此函数是实际的请求逻辑，供其他模块（如 fetch.py）直接调用。
    @tool() 装饰的 http_get 函数会调用此函数。
    """
    fetch_config = prepare_fetch_config(config)

    # 验证URL
    url = validate_url(url)

    # 准备请求头
    req_headers = prepare_headers(headers, fetch_config.get("user_agent"))

    # 如果提供了 bearer_token，自动添加 Authorization header
    if bearer_token:
        req_headers["Authorization"] = f"Bearer {bearer_token}"

    # 超时配置 - 确保是有效的数值类型
    request_timeout = fetch_config.get("timeout", 30)
    if timeout is not None and timeout != "":
        try:
            request_timeout = int(timeout) if isinstance(timeout, str) else timeout
        except (ValueError, TypeError):
            pass  # 使用默认值

    try:
        response = requests.get(
            url,
            headers=req_headers,
            params=params,
            timeout=request_timeout,
            verify=verify_ssl,
            allow_redirects=True,
        )

        # 检查响应状态
        response.raise_for_status()

        # 获取编码
        encoding = response.encoding or parse_content_type_encoding(response.headers.get("Content-Type", "")) or "utf-8"

        return {
            "success": True,
            "status_code": response.status_code,
            "content": response.text,
            "headers": dict(response.headers),
            "url": response.url,
            "encoding": encoding,
            "content_type": response.headers.get("Content-Type", "unknown"),
        }

    except requests.exceptions.Timeout:
        return format_error_response(Exception(f"请求超时（{request_timeout}秒）"), url)
    except requests.exceptions.SSLError as e:
        return format_error_response(Exception(f"SSL证书验证失败: {str(e)}"), url)
    except requests.exceptions.HTTPError as e:
        return {
            "success": False,
            "status_code": e.response.status_code if e.response else 0,
            "error": f"HTTP错误: {str(e)}",
            "url": url,
        }
    except Exception as e:
        return format_error_response(e, url)


def _http_post_impl(
    url: str,
    data: Optional[Union[Dict[str, Any], str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """HTTP POST 请求的内部实现。"""
    fetch_config = prepare_fetch_config(config)
    url = validate_url(url)
    req_headers = prepare_headers(headers, fetch_config.get("user_agent"))

    if bearer_token:
        req_headers["Authorization"] = f"Bearer {bearer_token}"

    # 超时配置 - 确保是有效的数值类型
    request_timeout = fetch_config.get("timeout", 30)
    if timeout is not None and timeout != "":
        try:
            request_timeout = int(timeout) if isinstance(timeout, str) else timeout
        except (ValueError, TypeError):
            pass  # 使用默认值

    try:
        response = requests.post(
            url,
            data=data,
            json=json_data,
            headers=req_headers,
            timeout=request_timeout,
            verify=verify_ssl,
            allow_redirects=True,
        )

        response.raise_for_status()
        encoding = response.encoding or "utf-8"

        return {
            "success": True,
            "status_code": response.status_code,
            "content": response.text,
            "headers": dict(response.headers),
            "url": response.url,
            "encoding": encoding,
            "content_type": response.headers.get("Content-Type", "unknown"),
        }

    except requests.exceptions.Timeout:
        return format_error_response(Exception(f"请求超时（{request_timeout}秒）"), url)
    except requests.exceptions.HTTPError as e:
        return {
            "success": False,
            "status_code": e.response.status_code if e.response else 0,
            "error": f"HTTP错误: {str(e)}",
            "url": url,
        }
    except Exception as e:
        return format_error_response(e, url)


def _http_put_impl(
    url: str,
    data: Optional[Union[Dict[str, Any], str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """HTTP PUT 请求的内部实现。"""
    fetch_config = prepare_fetch_config(config)
    url = validate_url(url)
    req_headers = prepare_headers(headers, fetch_config.get("user_agent"))

    if bearer_token:
        req_headers["Authorization"] = f"Bearer {bearer_token}"

    # 超时配置 - 确保是有效的数值类型
    request_timeout = fetch_config.get("timeout", 30)
    if timeout is not None and timeout != "":
        try:
            request_timeout = int(timeout) if isinstance(timeout, str) else timeout
        except (ValueError, TypeError):
            pass  # 使用默认值

    try:
        response = requests.put(
            url,
            data=data,
            json=json_data,
            headers=req_headers,
            timeout=request_timeout,
            verify=verify_ssl,
            allow_redirects=True,
        )

        response.raise_for_status()

        return {
            "success": True,
            "status_code": response.status_code,
            "content": response.text,
            "headers": dict(response.headers),
            "url": response.url,
            "encoding": response.encoding or "utf-8",
            "content_type": response.headers.get("Content-Type", "unknown"),
        }

    except requests.exceptions.Timeout:
        return format_error_response(Exception(f"请求超时（{request_timeout}秒）"), url)
    except requests.exceptions.HTTPError as e:
        return {
            "success": False,
            "status_code": e.response.status_code if e.response else 0,
            "error": f"HTTP错误: {str(e)}",
            "url": url,
        }
    except Exception as e:
        return format_error_response(e, url)


def _http_delete_impl(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """HTTP DELETE 请求的内部实现。"""
    fetch_config = prepare_fetch_config(config)
    url = validate_url(url)
    req_headers = prepare_headers(headers, fetch_config.get("user_agent"))

    if bearer_token:
        req_headers["Authorization"] = f"Bearer {bearer_token}"

    # 超时配置 - 确保是有效的数值类型
    request_timeout = fetch_config.get("timeout", 30)
    if timeout is not None and timeout != "":
        try:
            request_timeout = int(timeout) if isinstance(timeout, str) else timeout
        except (ValueError, TypeError):
            pass  # 使用默认值

    try:
        response = requests.delete(
            url,
            headers=req_headers,
            params=params,
            timeout=request_timeout,
            verify=verify_ssl,
            allow_redirects=True,
        )

        response.raise_for_status()

        return {
            "success": True,
            "status_code": response.status_code,
            "content": response.text,
            "headers": dict(response.headers),
            "url": response.url,
            "encoding": response.encoding or "utf-8",
            "content_type": response.headers.get("Content-Type", "unknown"),
        }

    except requests.exceptions.Timeout:
        return format_error_response(Exception(f"请求超时（{request_timeout}秒）"), url)
    except requests.exceptions.HTTPError as e:
        return {
            "success": False,
            "status_code": e.response.status_code if e.response else 0,
            "error": f"HTTP错误: {str(e)}",
            "url": url,
        }
    except Exception as e:
        return format_error_response(e, url)


def _http_patch_impl(
    url: str,
    data: Optional[Union[Dict[str, Any], str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """HTTP PATCH 请求的内部实现。"""
    fetch_config = prepare_fetch_config(config)
    url = validate_url(url)
    req_headers = prepare_headers(headers, fetch_config.get("user_agent"))

    if bearer_token:
        req_headers["Authorization"] = f"Bearer {bearer_token}"

    # 超时配置 - 确保是有效的数值类型
    request_timeout = fetch_config.get("timeout", 30)
    if timeout is not None and timeout != "":
        try:
            request_timeout = int(timeout) if isinstance(timeout, str) else timeout
        except (ValueError, TypeError):
            pass  # 使用默认值

    try:
        response = requests.patch(
            url,
            data=data,
            json=json_data,
            headers=req_headers,
            timeout=request_timeout,
            verify=verify_ssl,
            allow_redirects=True,
        )

        response.raise_for_status()

        return {
            "success": True,
            "status_code": response.status_code,
            "content": response.text,
            "headers": dict(response.headers),
            "url": response.url,
            "encoding": response.encoding or "utf-8",
            "content_type": response.headers.get("Content-Type", "unknown"),
        }

    except requests.exceptions.Timeout:
        return format_error_response(Exception(f"请求超时（{request_timeout}秒）"), url)
    except requests.exceptions.HTTPError as e:
        return {
            "success": False,
            "status_code": e.response.status_code if e.response else 0,
            "error": f"HTTP错误: {str(e)}",
            "url": url,
        }
    except Exception as e:
        return format_error_response(e, url)


# ============================================================================
# LangChain Tool 包装函数 (供 LLM 调用)
# ============================================================================


@tool()
def http_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    发送HTTP GET请求

    **何时使用此工具：**
    - 获取网页内容
    - 调用REST API的GET端点
    - 下载数据
    - 查询资源信息

    **工具能力：**
    - 支持自定义请求头
    - 支持查询参数
    - 自动处理重定向
    - 返回响应内容和元信息
    - 支持Bearer Token认证（通过独立参数传递）

    **🔐 Bearer Token 认证（推荐使用独立参数）：**
    当需要Bearer Token认证时，必须使用 bearer_token 参数，不要写在 headers 里：

    ```python
    # ✅ 正确示例
    http_get(
        url="https://api.example.com/data",
        bearer_token="your_token_here"  # ← Token 放这里
    )

    # ❌ 错误示例 - 不要这样做
    http_get(
        url="https://api.example.com/data",
        headers={"Authorization": "Bearer your_token"}  # ← Token 可能被脱敏！
    )
    ```

    **典型使用场景：**
    1. 获取需要认证的API数据：
       - url="https://api.example.com/users"
       - bearer_token="your_api_token"
       - params={"page": 1, "limit": 10}
    2. 获取网页内容：
       - url="https://example.com/page.html"
    3. 下载JSON数据：
       - url="https://api.example.com/data.json"

    Args:
        url (str): 请求URL（必填）
        headers (dict, optional): 自定义请求头（不要在这里放 Authorization，请用 bearer_token 参数）
        params (dict, optional): URL查询参数
        timeout (int, optional): 请求超时时间（秒）
        verify_ssl (bool): 是否验证SSL证书，默认True
        bearer_token (str, optional): Bearer Token，用于API认证。会自动构建 Authorization: Bearer {token} 请求头
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 响应结果
            - success (bool): 请求是否成功
            - status_code (int): HTTP状态码
            - content (str): 响应内容
            - headers (dict): 响应头
            - url (str): 最终请求的URL（处理重定向后）
            - encoding (str): 响应编码
            - content_type (str): 内容类型

    **注意事项：**
    - 默认会跟随重定向
    - 超时时间过短可能导致请求失败
    - 对于大文件，建议增加超时时间
    - 🔐 Bearer Token 必须通过 bearer_token 参数传递，不要写在 headers 中
    """
    return _http_get_impl(
        url=url,
        headers=headers,
        params=params,
        timeout=timeout,
        verify_ssl=verify_ssl,
        bearer_token=bearer_token,
        config=config,
    )


@tool()
def http_post(
    url: str,
    data: Optional[Union[Dict[str, Any], str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    发送HTTP POST请求

    **何时使用此工具：**
    - 提交表单数据
    - 调用REST API的POST端点
    - 创建新资源
    - 上传数据

    **工具能力：**
    - 支持表单数据（application/x-www-form-urlencoded）
    - 支持JSON数据（application/json）
    - 支持自定义请求头
    - 自动设置Content-Type
    - 支持Bearer Token认证（通过独立参数传递）

    **🔐 Bearer Token 认证（推荐使用独立参数）：**
    当需要Bearer Token认证时，必须使用 bearer_token 参数：

    ```python
    # ✅ 正确示例
    http_post(
        url="https://api.example.com/users",
        json_data={"name": "John"},
        bearer_token="your_token_here"
    )
    ```

    **典型使用场景：**
    1. 提交JSON数据：
       - url="https://api.example.com/users"
       - json_data={"name": "John", "email": "john@example.com"}
       - bearer_token="your_api_token"
    2. 提交表单数据：
       - url="https://example.com/form"
       - data={"username": "john", "password": "secret"}

    Args:
        url (str): 请求URL（必填）
        data (dict or str, optional): 表单数据
        json_data (dict, optional): JSON数据（会自动设置Content-Type）
        headers (dict, optional): 自定义请求头（不要在这里放 Authorization，请用 bearer_token 参数）
        timeout (int, optional): 请求超时时间（秒）
        verify_ssl (bool): 是否验证SSL证书，默认True
        bearer_token (str, optional): Bearer Token，用于API认证
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 响应结果（格式同http_get）

    **注意事项：**
    - data和json_data参数不能同时使用
    - json_data参数会自动设置Content-Type为application/json
    - data参数默认Content-Type为application/x-www-form-urlencoded
    - 🔐 Bearer Token 必须通过 bearer_token 参数传递
    """
    return _http_post_impl(
        url=url,
        data=data,
        json_data=json_data,
        headers=headers,
        timeout=timeout,
        verify_ssl=verify_ssl,
        bearer_token=bearer_token,
        config=config,
    )


@tool()
def http_put(
    url: str,
    data: Optional[Union[Dict[str, Any], str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    发送HTTP PUT请求

    **何时使用此工具：**
    - 更新资源
    - 替换整个资源
    - 调用REST API的PUT端点

    **工具能力：**
    - 支持表单数据和JSON数据
    - 支持自定义请求头
    - 幂等操作（多次调用结果相同）
    - 支持Bearer Token认证（通过独立参数传递）

    Args:
        url (str): 请求URL（必填）
        data (dict or str, optional): 表单数据
        json_data (dict, optional): JSON数据
        headers (dict, optional): 自定义请求头（不要在这里放 Authorization，请用 bearer_token 参数）
        timeout (int, optional): 请求超时时间（秒）
        verify_ssl (bool): 是否验证SSL证书，默认True
        bearer_token (str, optional): Bearer Token，用于API认证
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 响应结果（格式同http_get）
    """
    return _http_put_impl(
        url=url,
        data=data,
        json_data=json_data,
        headers=headers,
        timeout=timeout,
        verify_ssl=verify_ssl,
        bearer_token=bearer_token,
        config=config,
    )


@tool()
def http_delete(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    发送HTTP DELETE请求

    **何时使用此工具：**
    - 删除资源
    - 调用REST API的DELETE端点

    **工具能力：**
    - 支持查询参数
    - 支持自定义请求头
    - 幂等操作
    - 支持Bearer Token认证（通过独立参数传递）

    Args:
        url (str): 请求URL（必填）
        headers (dict, optional): 自定义请求头（不要在这里放 Authorization，请用 bearer_token 参数）
        params (dict, optional): URL查询参数
        timeout (int, optional): 请求超时时间（秒）
        verify_ssl (bool): 是否验证SSL证书，默认True
        bearer_token (str, optional): Bearer Token，用于API认证
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 响应结果（格式同http_get）
    """
    return _http_delete_impl(
        url=url,
        headers=headers,
        params=params,
        timeout=timeout,
        verify_ssl=verify_ssl,
        bearer_token=bearer_token,
        config=config,
    )


@tool()
def http_patch(
    url: str,
    data: Optional[Union[Dict[str, Any], str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    bearer_token: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    发送HTTP PATCH请求

    **何时使用此工具：**
    - 部分更新资源
    - 调用REST API的PATCH端点

    **工具能力：**
    - 支持表单数据和JSON数据
    - 支持自定义请求头
    - 用于部分更新（与PUT的完全替换不同）
    - 支持Bearer Token认证（通过独立参数传递）

    **典型使用场景：**
    1. 部分更新用户信息：
       - url="https://api.example.com/users/123"
       - json_data={"email": "newemail@example.com"}
       - bearer_token="your_api_token"

    Args:
        url (str): 请求URL（必填）
        data (dict or str, optional): 表单数据
        json_data (dict, optional): JSON数据
        headers (dict, optional): 自定义请求头（不要在这里放 Authorization，请用 bearer_token 参数）
        timeout (int, optional): 请求超时时间（秒）
        verify_ssl (bool): 是否验证SSL证书，默认True
        bearer_token (str, optional): Bearer Token，用于API认证
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 响应结果（格式同http_get）
    """
    return _http_patch_impl(
        url=url,
        data=data,
        json_data=json_data,
        headers=headers,
        timeout=timeout,
        verify_ssl=verify_ssl,
        bearer_token=bearer_token,
        config=config,
    )
