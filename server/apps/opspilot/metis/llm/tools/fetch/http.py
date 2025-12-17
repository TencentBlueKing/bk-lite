"""HTTP请求工具 - 使用requests库"""
import requests
import json as json_lib
from typing import Optional, Dict, Any, Union
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.fetch.utils import (
    prepare_fetch_config,
    validate_url,
    prepare_headers,
    format_response_info,
    format_error_response,
    parse_content_type_encoding,
)


@tool()
def http_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    config: RunnableConfig = None
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

    **典型使用场景：**
    1. 获取API数据：
       - url="https://api.example.com/users"
       - params={"page": 1, "limit": 10}
    2. 获取网页内容：
       - url="https://example.com/page.html"
    3. 下载JSON数据：
       - url="https://api.example.com/data.json"

    Args:
        url (str): 请求URL（必填）
        headers (dict, optional): 自定义请求头
        params (dict, optional): URL查询参数
        timeout (int, optional): 请求超时时间（秒）
        verify_ssl (bool): 是否验证SSL证书，默认True
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
    """
    fetch_config = prepare_fetch_config(config)

    # 验证URL
    url = validate_url(url)

    # 准备请求头
    req_headers = prepare_headers(headers, fetch_config.get('user_agent'))

    # 超时配置
    request_timeout = timeout if timeout is not None else fetch_config.get(
        'timeout', 30)

    try:
        response = requests.get(
            url,
            headers=req_headers,
            params=params,
            timeout=request_timeout,
            verify=verify_ssl,
            allow_redirects=True
        )

        # 检查响应状态
        response.raise_for_status()

        # 获取编码
        encoding = response.encoding or parse_content_type_encoding(
            response.headers.get('Content-Type', '')
        ) or 'utf-8'

        return {
            'success': True,
            'status_code': response.status_code,
            'content': response.text,
            'headers': dict(response.headers),
            'url': response.url,
            'encoding': encoding,
            'content_type': response.headers.get('Content-Type', 'unknown'),
        }

    except requests.exceptions.Timeout:
        return format_error_response(
            Exception(f"请求超时（{request_timeout}秒）"),
            url
        )
    except requests.exceptions.SSLError as e:
        return format_error_response(
            Exception(f"SSL证书验证失败: {str(e)}"),
            url
        )
    except requests.exceptions.HTTPError as e:
        return {
            'success': False,
            'status_code': e.response.status_code if e.response else 0,
            'error': f"HTTP错误: {str(e)}",
            'url': url,
        }
    except Exception as e:
        return format_error_response(e, url)


@tool()
def http_post(
    url: str,
    data: Optional[Union[Dict[str, Any], str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    config: RunnableConfig = None
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

    **典型使用场景：**
    1. 提交JSON数据：
       - url="https://api.example.com/users"
       - json_data={"name": "John", "email": "john@example.com"}
    2. 提交表单数据：
       - url="https://example.com/form"
       - data={"username": "john", "password": "secret"}
    3. 自定义请求：
       - headers={"Authorization": "Bearer token"}

    Args:
        url (str): 请求URL（必填）
        data (dict or str, optional): 表单数据
        json_data (dict, optional): JSON数据（会自动设置Content-Type）
        headers (dict, optional): 自定义请求头
        timeout (int, optional): 请求超时时间（秒）
        verify_ssl (bool): 是否验证SSL证书，默认True
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 响应结果（格式同http_get）

    **注意事项：**
    - data和json_data参数不能同时使用
    - json_data参数会自动设置Content-Type为application/json
    - data参数默认Content-Type为application/x-www-form-urlencoded
    """
    fetch_config = prepare_fetch_config(config)
    url = validate_url(url)
    req_headers = prepare_headers(headers, fetch_config.get('user_agent'))
    request_timeout = timeout if timeout is not None else fetch_config.get(
        'timeout', 30)

    try:
        response = requests.post(
            url,
            data=data,
            json=json_data,
            headers=req_headers,
            timeout=request_timeout,
            verify=verify_ssl,
            allow_redirects=True
        )

        response.raise_for_status()

        encoding = response.encoding or 'utf-8'

        return {
            'success': True,
            'status_code': response.status_code,
            'content': response.text,
            'headers': dict(response.headers),
            'url': response.url,
            'encoding': encoding,
            'content_type': response.headers.get('Content-Type', 'unknown'),
        }

    except requests.exceptions.Timeout:
        return format_error_response(
            Exception(f"请求超时（{request_timeout}秒）"),
            url
        )
    except requests.exceptions.HTTPError as e:
        return {
            'success': False,
            'status_code': e.response.status_code if e.response else 0,
            'error': f"HTTP错误: {str(e)}",
            'url': url,
        }
    except Exception as e:
        return format_error_response(e, url)


@tool()
def http_put(
    url: str,
    data: Optional[Union[Dict[str, Any], str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    config: RunnableConfig = None
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

    Args:
        url (str): 请求URL（必填）
        data (dict or str, optional): 表单数据
        json_data (dict, optional): JSON数据
        headers (dict, optional): 自定义请求头
        timeout (int, optional): 请求超时时间（秒）
        verify_ssl (bool): 是否验证SSL证书，默认True
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 响应结果（格式同http_get）
    """
    fetch_config = prepare_fetch_config(config)
    url = validate_url(url)
    req_headers = prepare_headers(headers, fetch_config.get('user_agent'))
    request_timeout = timeout if timeout is not None else fetch_config.get(
        'timeout', 30)

    try:
        response = requests.put(
            url,
            data=data,
            json=json_data,
            headers=req_headers,
            timeout=request_timeout,
            verify=verify_ssl,
            allow_redirects=True
        )

        response.raise_for_status()

        return {
            'success': True,
            'status_code': response.status_code,
            'content': response.text,
            'headers': dict(response.headers),
            'url': response.url,
            'encoding': response.encoding or 'utf-8',
            'content_type': response.headers.get('Content-Type', 'unknown'),
        }

    except requests.exceptions.Timeout:
        return format_error_response(
            Exception(f"请求超时（{request_timeout}秒）"),
            url
        )
    except requests.exceptions.HTTPError as e:
        return {
            'success': False,
            'status_code': e.response.status_code if e.response else 0,
            'error': f"HTTP错误: {str(e)}",
            'url': url,
        }
    except Exception as e:
        return format_error_response(e, url)


@tool()
def http_delete(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    config: RunnableConfig = None
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

    Args:
        url (str): 请求URL（必填）
        headers (dict, optional): 自定义请求头
        params (dict, optional): URL查询参数
        timeout (int, optional): 请求超时时间（秒）
        verify_ssl (bool): 是否验证SSL证书，默认True
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 响应结果（格式同http_get）
    """
    fetch_config = prepare_fetch_config(config)
    url = validate_url(url)
    req_headers = prepare_headers(headers, fetch_config.get('user_agent'))
    request_timeout = timeout if timeout is not None else fetch_config.get(
        'timeout', 30)

    try:
        response = requests.delete(
            url,
            headers=req_headers,
            params=params,
            timeout=request_timeout,
            verify=verify_ssl,
            allow_redirects=True
        )

        response.raise_for_status()

        return {
            'success': True,
            'status_code': response.status_code,
            'content': response.text,
            'headers': dict(response.headers),
            'url': response.url,
            'encoding': response.encoding or 'utf-8',
            'content_type': response.headers.get('Content-Type', 'unknown'),
        }

    except requests.exceptions.Timeout:
        return format_error_response(
            Exception(f"请求超时（{request_timeout}秒）"),
            url
        )
    except requests.exceptions.HTTPError as e:
        return {
            'success': False,
            'status_code': e.response.status_code if e.response else 0,
            'error': f"HTTP错误: {str(e)}",
            'url': url,
        }
    except Exception as e:
        return format_error_response(e, url)


@tool()
def http_patch(
    url: str,
    data: Optional[Union[Dict[str, Any], str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    verify_ssl: bool = True,
    config: RunnableConfig = None
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

    **典型使用场景：**
    1. 部分更新用户信息：
       - url="https://api.example.com/users/123"
       - json_data={"email": "newemail@example.com"}

    Args:
        url (str): 请求URL（必填）
        data (dict or str, optional): 表单数据
        json_data (dict, optional): JSON数据
        headers (dict, optional): 自定义请求头
        timeout (int, optional): 请求超时时间（秒）
        verify_ssl (bool): 是否验证SSL证书，默认True
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 响应结果（格式同http_get）
    """
    fetch_config = prepare_fetch_config(config)
    url = validate_url(url)
    req_headers = prepare_headers(headers, fetch_config.get('user_agent'))
    request_timeout = timeout if timeout is not None else fetch_config.get(
        'timeout', 30)

    try:
        response = requests.patch(
            url,
            data=data,
            json=json_data,
            headers=req_headers,
            timeout=request_timeout,
            verify=verify_ssl,
            allow_redirects=True
        )

        response.raise_for_status()

        return {
            'success': True,
            'status_code': response.status_code,
            'content': response.text,
            'headers': dict(response.headers),
            'url': response.url,
            'encoding': response.encoding or 'utf-8',
            'content_type': response.headers.get('Content-Type', 'unknown'),
        }

    except requests.exceptions.Timeout:
        return format_error_response(
            Exception(f"请求超时（{request_timeout}秒）"),
            url
        )
    except requests.exceptions.HTTPError as e:
        return {
            'success': False,
            'status_code': e.response.status_code if e.response else 0,
            'error': f"HTTP错误: {str(e)}",
            'url': url,
        }
    except Exception as e:
        return format_error_response(e, url)
