"""Fetch工具的通用辅助函数"""
import re
from typing import Optional, Dict, Any
from urllib.parse import urlparse, urljoin


def prepare_fetch_config(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    准备Fetch请求配置

    Args:
        cfg: RunnableConfig配置对象，可包含以下配置：
            - default_timeout: 默认请求超时时间（秒）
            - default_limit: 默认内容长度限制
            - user_agent: 默认User-Agent
            - verify_ssl: 是否验证SSL证书

    Returns:
        dict: Fetch配置字典
    """
    config = {
        'timeout': 30,  # 默认超时30秒
        'default_limit': 5000,  # 默认内容限制
        'user_agent': 'Mozilla/5.0 (compatible; BK-Lite-Agent/1.0)',
        'verify_ssl': True,
    }

    if cfg:
        configurable = cfg.get('configurable', {})
        if 'default_timeout' in configurable:
            config['timeout'] = configurable['default_timeout']
        if 'default_limit' in configurable:
            config['default_limit'] = configurable['default_limit']
        if 'user_agent' in configurable:
            config['user_agent'] = configurable['user_agent']
        if 'verify_ssl' in configurable:
            config['verify_ssl'] = configurable['verify_ssl']

    return config


def validate_url(url: str) -> str:
    """
    验证并规范化URL

    Args:
        url: URL字符串

    Returns:
        str: 规范化后的URL

    Raises:
        ValueError: URL无效时抛出
    """
    if not url or not url.strip():
        raise ValueError("URL不能为空")

    url = url.strip()

    # 如果没有协议，默认添加https://
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # 验证URL格式
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValueError(f"URL格式无效: {url}")
        return url
    except Exception as e:
        raise ValueError(f"URL格式无效: {url}, 错误: {str(e)}")


def prepare_headers(
    custom_headers: Optional[Dict[str, str]] = None,
    user_agent: Optional[str] = None
) -> Dict[str, str]:
    """
    准备HTTP请求头

    Args:
        custom_headers: 自定义请求头
        user_agent: User-Agent字符串

    Returns:
        dict: 合并后的请求头
    """
    headers = {}

    # 默认User-Agent
    if user_agent:
        headers['User-Agent'] = user_agent

    # 合并自定义请求头
    if custom_headers:
        headers.update(custom_headers)

    return headers


def format_response_info(
    status_code: int,
    headers: Dict[str, str],
    content_length: int
) -> Dict[str, Any]:
    """
    格式化响应信息

    Args:
        status_code: HTTP状态码
        headers: 响应头
        content_length: 内容长度

    Returns:
        dict: 格式化的响应信息
    """
    return {
        'status_code': status_code,
        'content_type': headers.get('Content-Type', 'unknown'),
        'content_length': content_length,
        'encoding': headers.get('Content-Encoding'),
    }


def truncate_content(
    content: str,
    max_length: Optional[int] = None,
    start_index: int = 0
) -> Dict[str, Any]:
    """
    截取内容到指定长度

    Args:
        content: 内容字符串
        max_length: 最大长度，None表示不限制
        start_index: 起始索引

    Returns:
        dict: 包含截取内容和元信息
            - content: 截取后的内容
            - total_length: 总长度
            - truncated: 是否被截断
            - start_index: 起始位置
            - end_index: 结束位置
    """
    total_length = len(content)

    # 验证起始索引
    if start_index < 0:
        start_index = 0
    if start_index >= total_length:
        return {
            'content': '',
            'total_length': total_length,
            'truncated': True,
            'start_index': start_index,
            'end_index': start_index,
            'remaining': 0,
        }

    # 如果没有长度限制，返回从start_index开始的所有内容
    if max_length is None or max_length <= 0:
        return {
            'content': content[start_index:],
            'total_length': total_length,
            'truncated': False,
            'start_index': start_index,
            'end_index': total_length,
            'remaining': 0,
        }

    # 计算结束位置
    end_index = min(start_index + max_length, total_length)
    truncated_content = content[start_index:end_index]

    return {
        'content': truncated_content,
        'total_length': total_length,
        'truncated': end_index < total_length,
        'start_index': start_index,
        'end_index': end_index,
        'remaining': max(0, total_length - end_index),
    }


def clean_html_tags(html: str) -> str:
    """
    移除HTML标签，仅保留文本内容

    Args:
        html: HTML字符串

    Returns:
        str: 清理后的纯文本
    """
    # 移除script和style标签及其内容
    html = re.sub(r'<script[^>]*>.*?</script>', '',
                  html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html,
                  flags=re.DOTALL | re.IGNORECASE)

    # 移除HTML注释
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # 移除所有HTML标签
    html = re.sub(r'<[^>]+>', '', html)

    # 转换HTML实体
    html = html.replace('&nbsp;', ' ')
    html = html.replace('&lt;', '<')
    html = html.replace('&gt;', '>')
    html = html.replace('&amp;', '&')
    html = html.replace('&quot;', '"')
    html = html.replace('&#39;', "'")

    # 清理多余空白
    html = re.sub(r'\n\s*\n', '\n\n', html)
    html = re.sub(r' +', ' ', html)

    return html.strip()


def is_valid_json_content_type(content_type: str) -> bool:
    """
    检查Content-Type是否为JSON

    Args:
        content_type: Content-Type字符串

    Returns:
        bool: 是否为JSON类型
    """
    if not content_type:
        return False

    content_type = content_type.lower()
    return any(t in content_type for t in ['application/json', 'text/json', '+json'])


def format_error_response(error: Exception, url: str) -> Dict[str, Any]:
    """
    格式化错误响应

    Args:
        error: 异常对象
        url: 请求的URL

    Returns:
        dict: 错误信息字典
    """
    error_type = type(error).__name__
    error_msg = str(error)

    return {
        'success': False,
        'error': error_msg,
        'error_type': error_type,
        'url': url,
    }


def parse_content_type_encoding(content_type: str) -> Optional[str]:
    """
    从Content-Type中解析字符编码

    Args:
        content_type: Content-Type字符串

    Returns:
        str: 字符编码，如果未找到返回None
    """
    if not content_type:
        return None

    # 查找charset参数
    match = re.search(r'charset=([^\s;]+)', content_type, re.IGNORECASE)
    if match:
        return match.group(1).strip('"\'')

    return None
