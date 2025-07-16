from typing import Dict

import json_repair
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
import logging

logger = logging.getLogger(__name__)

import requests


def update_api_config(dynamics: Dict, config: RunnableConfig) -> Dict:
    """
    更新API配置,用params进行参数替换
    """
    url = config['configurable']['url']
    headers = config['configurable'].get("headers") or '{}'
    api_params = config['configurable'].get("params") or '{}'
    data = config['configurable'].get("data") or '{}'
    # 替换url中的参数
    for key, value in dynamics.items():
        url = url.replace(f'{{{{{key}}}}}', str(value))
        headers = headers.replace(f'{{{{{key}}}}}', str(value))
        api_params = api_params.replace(f'{{{{{key}}}}}', str(value))
        data = data.replace(f'{{{{{key}}}}}', str(value))
    try:
        headers = json_repair.loads(headers)
        data = json_repair.loads(data)
    except:
        raise ValueError("headers or data is not a valid JSON string")
    return {
        'url': url,
        'headers': headers,
        'params': api_params,
        'data': data
    }


@tool()
def http_get(dynamics: str, config: RunnableConfig):
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
    """
    dynamics = json_repair.loads(dynamics)
    api_kwargs = update_api_config(dynamics, config)
    api_kwargs.update(data=None)
    return _request("GET", **api_kwargs, )


@tool()
def http_post(dynamics: str, config: RunnableConfig):
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
    """
    dynamics = json_repair.loads(dynamics)
    api_kwargs = update_api_config(dynamics, config)
    return _request("POST", **api_kwargs)


@tool()
def http_put(dynamics: str, config: RunnableConfig):
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
    """
    dynamics = json_repair.loads(dynamics)
    api_kwargs = update_api_config(dynamics, config)
    return _request("PUT", **api_kwargs)


@tool()
def http_delete(dynamics: str, config: RunnableConfig):
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
    """
    dynamics = json_repair.loads(dynamics)
    api_kwargs = update_api_config(dynamics, config)
    return _request("DELETE", **api_kwargs)


def _request(method: str, url: str, headers: Dict, params: Dict, data: Dict):
    """
    发送HTTP请求
    :param method: 请求方法
    :param url: 请求URL
    :param headers: 请求头
    :param params: URL参数
    :param data: 请求体数据
    :return:
    """
    try:
        response = requests.request(
            method, url, headers=headers, params=params, json=data, verify=False)
        logger.info(
            f"请求URL: {url}, 请求方法: {method}, 请求头: {headers}, 请求参数: {params}, 请求体: {data}")
        return response.content.decode('utf-8')
    except requests.exceptions.RequestException as e:
        raise ValueError(f"请求失败: {e}")
