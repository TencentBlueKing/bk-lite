from typing import Dict, Optional
import re
from urllib.parse import urlparse

import requests
import json_repair
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

# 安全配置
ALLOWED_SCHEMES = {'http', 'https'}
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
SENSITIVE_HEADERS = {'authorization', 'x-api-key', 'cookie', 'x-auth-token'}


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
        if parsed.scheme not in ALLOWED_SCHEMES:
            raise ValueError(f"不支持的协议: {parsed.scheme}")

        # 检查主机名
        if not parsed.netloc:
            raise ValueError("无效的主机名")

        # 防止内网访问
        if parsed.hostname in ('localhost', '127.0.0.1', '0.0.0.0'):
            logger.warning(f"尝试访问本地地址: {parsed.hostname}")

        return True

    except Exception as e:
        raise ValueError(f"URL验证失败: {e}")


def _mask_sensitive_data(data: Dict) -> Dict:
    """
    脱敏敏感信息用于日志记录

    Args:
        data: 原始数据字典

    Returns:
        Dict: 脱敏后的数据字典
    """
    if not isinstance(data, dict):
        return data

    masked_data = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in SENSITIVE_HEADERS):
            masked_data[key] = "***MASKED***"
        else:
            masked_data[key] = value
    return masked_data


def update_api_config(dynamics: Dict, config: RunnableConfig) -> Dict:
    """
    更新API配置,用params进行参数替换

    Args:
        dynamics: 动态参数字典
        config: 运行时配置

    Returns:
        Dict: 更新后的API配置

    Raises:
        ValueError: 配置参数无效时抛出异常
    """
    if not isinstance(dynamics, dict):
        raise ValueError("dynamics 参数必须是字典类型")

    if 'configurable' not in config:
        raise ValueError("config 中缺少 configurable 字段")

    configurable = config['configurable']
    url = configurable.get('url', '')
    headers = configurable.get("headers", '{}')
    api_params = configurable.get("params", '{}')
    data = configurable.get("data", '{}')

    if not url:
        raise ValueError("URL 不能为空")

    # 替换url中的参数
    for key, value in dynamics.items():
        if not isinstance(key, str):
            continue
        safe_value = str(value)
        url = url.replace(f'{{{{{key}}}}}', safe_value)
        headers = headers.replace(f'{{{{{key}}}}}', safe_value)
        api_params = api_params.replace(f'{{{{{key}}}}}', safe_value)
        data = data.replace(f'{{{{{key}}}}}', safe_value)

    # 验证URL安全性
    _validate_url(url)

    try:
        headers_dict = json_repair.loads(headers)
        data_dict = json_repair.loads(data)

        # 验证headers格式
        if not isinstance(headers_dict, dict):
            raise ValueError("headers 必须是有效的JSON对象")
        if not isinstance(data_dict, dict):
            raise ValueError("data 必须是有效的JSON对象")

    except Exception as e:
        raise ValueError(f"JSON解析失败: {e}")

    return {
        'url': url,
        'headers': headers_dict,
        'params': api_params,
        'data': data_dict
    }


@tool()
def http_get(dynamics: str, config: RunnableConfig) -> str:
    """
    这是一个HTTP GET请求的工具，用户可以通过这个工具向指定的URL发送GET请求，并获取响应数据。

    Args:
        dynamics (str): 包含请求的动态参数，例如 {"id": 123}。
        config (RunnableConfig): 包含请求的配置参数。
            - configurable (dict): 包含以下字段：
                - url (str): 请求的URL，如果有路径参数需要使用{{}}进行替换，例如 http://example.com/{{id}}。
                - headers (str): 请求头，如果有参数需要使用{{}}进行替换，例如 {"contentType":"Application/json"}。
                - params (str): 请求参数，如果有参数需要使用{{}}进行替换，例如 {"uuid": "{{uuid}}" }。
                - data (str): 请求体，如果有参数需要使用{{}}进行替换，例如 {"name": "{{name}}" }。

    Returns:
        str: 响应数据。

    Raises:
        ValueError: 当请求参数无效或请求失败时抛出
    """
    try:
        dynamics_dict = json_repair.loads(dynamics)
        api_kwargs = update_api_config(dynamics_dict, config)
        api_kwargs.update(data=None)
        return _request("GET", **api_kwargs)
    except Exception as e:
        logger.error(f"HTTP GET请求失败: {e}")
        raise


@tool()
def http_post(dynamics: str, config: RunnableConfig) -> str:
    """
    这是一个HTTP POST请求的工具，用户可以通过这个工具向指定的URL发送POST请求，并获取响应数据。

    Args:
        dynamics (str): 包含请求的动态参数，例如 {"id": 123}。
        config (RunnableConfig): 包含请求的配置参数。
            - configurable (dict): 包含以下字段：
                - url (str): 请求的URL，如果有路径参数需要使用{{}}进行替换，例如 http://example.com/{{id}}。
                - headers (str): 请求头，如果有参数需要使用{{}}进行替换，例如 {"contentType":"Application/json"}。
                - params (str): 请求参数，如果有参数需要使用{{}}进行替换，例如 {"uuid": "{{uuid}}" }。
                - data (str): 请求体，如果有参数需要使用{{}}进行替换，例如 {"name": "{{name}}" }。

    Returns:
        str: 响应数据。

    Raises:
        ValueError: 当请求参数无效或请求失败时抛出
    """
    try:
        dynamics_dict = json_repair.loads(dynamics)
        api_kwargs = update_api_config(dynamics_dict, config)
        return _request("POST", **api_kwargs)
    except Exception as e:
        logger.error(f"HTTP POST请求失败: {e}")
        raise


@tool()
def http_put(dynamics: str, config: RunnableConfig) -> str:
    """
    这是一个HTTP PUT请求的工具，用户可以通过这个工具向指定的URL发送PUT请求，并获取响应数据。

    Args:
        dynamics (str): 包含请求的动态参数，例如 {"id": 123}。
        config (RunnableConfig): 包含请求的配置参数。
            - configurable (dict): 包含以下字段：
                - url (str): 请求的URL，如果有路径参数需要使用{{}}进行替换，例如 http://example.com/{{id}}。
                - headers (str): 请求头，如果有参数需要使用{{}}进行替换，例如 {"contentType":"Application/json"}。
                - params (str): 请求参数，如果有参数需要使用{{}}进行替换，例如 {"uuid": "{{uuid}}" }。
                - data (str): 请求体，如果有参数需要使用{{}}进行替换，例如 {"name": "{{name}}" }。

    Returns:
        str: 响应数据。

    Raises:
        ValueError: 当请求参数无效或请求失败时抛出
    """
    try:
        dynamics_dict = json_repair.loads(dynamics)
        api_kwargs = update_api_config(dynamics_dict, config)
        return _request("PUT", **api_kwargs)
    except Exception as e:
        logger.error(f"HTTP PUT请求失败: {e}")
        raise


@tool()
def http_delete(dynamics: str, config: RunnableConfig) -> str:
    """
    这是一个HTTP DELETE请求的工具，用户可以通过这个工具向指定的URL发送DELETE请求，并获取响应数据。

    Args:
        dynamics (str): 包含请求的动态参数，例如 {"id": 123}。
        config (RunnableConfig): 包含请求的配置参数。
            - configurable (dict): 包含以下字段：
                - url (str): 请求的URL，如果有路径参数需要使用{{}}进行替换，例如 http://example.com/{{id}}。
                - headers (str): 请求头，如果有参数需要使用{{}}进行替换，例如 {"contentType":"Application/json"}。
                - params (str): 请求参数，如果有参数需要使用{{}}进行替换，例如 {"uuid": "{{uuid}}" }。
                - data (str): 请求体，如果有参数需要使用{{}}进行替换，例如 {"name": "{{name}}" }。

    Returns:
        str: 响应数据。

    Raises:
        ValueError: 当请求参数无效或请求失败时抛出
    """
    try:
        dynamics_dict = json_repair.loads(dynamics)
        api_kwargs = update_api_config(dynamics_dict, config)
        return _request("DELETE", **api_kwargs)
    except Exception as e:
        logger.error(f"HTTP DELETE请求失败: {e}")
        raise


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    reraise=True
)
def _request(method: str, url: str, headers: Dict, params: str, data: Optional[Dict]) -> str:
    """
    发送HTTP请求，支持重试机制

    Args:
        method: 请求方法
        url: 请求URL
        headers: 请求头
        params: URL参数（字符串格式）
        data: 请求体数据

    Returns:
        str: 响应内容

    Raises:
        ValueError: 请求失败时抛出异常
    """
    # 参数校验
    if not url or not isinstance(url, str):
        raise ValueError("URL不能为空且必须是字符串")

    if not method or method.upper() not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
        raise ValueError(f"不支持的HTTP方法: {method}")

    # 解析params字符串
    params_dict = {}
    if params:
        try:
            params_dict = json_repair.loads(
                params) if isinstance(params, str) else params
            if not isinstance(params_dict, dict):
                params_dict = {}
        except Exception:
            logger.warning(f"无法解析params参数: {params}")
            params_dict = {}

    # 脱敏日志记录
    masked_headers = _mask_sensitive_data(headers)
    masked_data = _mask_sensitive_data(data) if data else None

    logger.info(
        f"发起HTTP请求",
        extra={
            "method": method.upper(),
            "url": url,
            "headers": masked_headers,
            "params": params_dict,
            "has_data": bool(data)
        }
    )

    try:
        # 配置请求参数
        request_kwargs = {
            'headers': headers,
            'params': params_dict,
            'timeout': DEFAULT_TIMEOUT,
            'verify': True  # 启用SSL验证
        }

        # 根据方法选择合适的请求方式
        if method.upper() in ['POST', 'PUT', 'PATCH'] and data:
            request_kwargs['json'] = data

        # 发送请求
        response = requests.request(method.upper(), url, **request_kwargs)

        # 检查响应状态
        if response.status_code >= 400:
            logger.error(
                f"HTTP请求返回错误状态",
                extra={
                    "status": response.status_code,
                    "url": url,
                    "method": method.upper(),
                    "error_text": response.text[:500]  # 限制错误信息长度
                }
            )
            raise ValueError(f"HTTP请求失败，状态码: {response.status_code}")

        # 获取响应内容
        content = response.text

        logger.info(
            f"HTTP请求成功",
            extra={
                "status": response.status_code,
                "url": url,
                "method": method.upper(),
                "content_length": len(content)
            }
        )

        return content

    except requests.exceptions.Timeout:
        logger.error(f"HTTP请求超时: {url}")
        raise ValueError(f"请求超时: {url}")

    except requests.exceptions.ConnectionError as e:
        logger.error(
            f"HTTP连接错误",
            extra={
                "url": url,
                "method": method.upper(),
                "error": str(e)
            }
        )
        raise ValueError(f"连接失败: {e}")

    except requests.exceptions.RequestException as e:
        logger.error(
            f"HTTP请求异常",
            extra={
                "url": url,
                "method": method.upper(),
                "error": str(e)
            }
        )
        raise ValueError(f"HTTP请求失败: {e}")

    except Exception as e:
        logger.error(
            f"HTTP请求未知错误",
            extra={
                "url": url,
                "method": method.upper(),
                "error": str(e)
            }
        )
        raise ValueError(f"请求处理失败: {e}")
