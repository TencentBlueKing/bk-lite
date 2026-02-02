"""SSH工具的通用辅助函数"""
import os
from pathlib import Path
from typing import Optional, Dict, Any


def prepare_ssh_config(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    准备SSH连接配置

    Args:
        cfg: RunnableConfig配置对象，可包含以下配置：
            - ssh_timeout: SSH连接超时时间（秒）
            - ssh_port: SSH默认端口
            - ssh_key_path: 默认私钥路径

    Returns:
        dict: SSH配置字典
    """
    config = {
        'timeout': 20,  # 默认超时20秒
        'port': 22,     # 默认SSH端口
        'key_path': None,
        'look_for_keys': True,  # 自动查找SSH密钥
    }

    if cfg:
        configurable = cfg.get('configurable', {})
        if 'ssh_timeout' in configurable:
            config['timeout'] = configurable['ssh_timeout']
        if 'ssh_port' in configurable:
            config['port'] = configurable['ssh_port']
        if 'ssh_key_path' in configurable:
            config['key_path'] = configurable['ssh_key_path']

    return config


def resolve_key_path(key_path: Optional[str] = None) -> Optional[str]:
    """
    解析SSH私钥路径，支持~符号和相对路径

    Args:
        key_path: 私钥路径

    Returns:
        str: 解析后的绝对路径，如果文件不存在返回None
    """
    if not key_path:
        # 尝试默认路径
        default_paths = [
            '~/.ssh/id_rsa',
            '~/.ssh/id_ed25519',
            '~/.ssh/id_ecdsa',
        ]
        for path in default_paths:
            expanded = os.path.expanduser(path)
            if os.path.exists(expanded):
                return expanded
        return None

    # 展开用户目录符号
    expanded = os.path.expanduser(key_path)

    # 转换为绝对路径
    abs_path = os.path.abspath(expanded)

    # 验证文件存在
    if os.path.exists(abs_path):
        return abs_path

    return None


def format_command_output(stdout: str, stderr: str, exit_code: int) -> Dict[str, Any]:
    """
    格式化SSH命令执行结果

    Args:
        stdout: 标准输出
        stderr: 标准错误
        exit_code: 退出码

    Returns:
        dict: 格式化的结果字典
    """
    return {
        'stdout': stdout.strip() if stdout else '',
        'stderr': stderr.strip() if stderr else '',
        'exit_code': exit_code,
        'success': exit_code == 0,
    }


def validate_host_params(host: str, username: str) -> None:
    """
    验证SSH主机参数

    Args:
        host: 主机地址
        username: 用户名

    Raises:
        ValueError: 参数无效时抛出
    """
    if not host or not host.strip():
        raise ValueError("主机地址不能为空")

    if not username or not username.strip():
        raise ValueError("用户名不能为空")

    # 验证主机地址格式（简单检查）
    host = host.strip()
    if host.startswith('-'):
        raise ValueError("主机地址格式无效")


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小为人类可读格式

    Args:
        size_bytes: 字节数

    Returns:
        str: 格式化的大小字符串
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def parse_ssh_uri(uri: str) -> Dict[str, Any]:
    """
    解析SSH URI格式：ssh://user@host:port/path
    或简化格式：user@host:path

    Args:
        uri: SSH URI字符串

    Returns:
        dict: 包含host, username, port, path的字典
    """
    result = {
        'host': None,
        'username': None,
        'port': 22,
        'path': None,
    }

    # 移除ssh://前缀
    if uri.startswith('ssh://'):
        uri = uri[6:]

    # 解析用户名@主机部分
    if '@' in uri:
        username_host, _, path = uri.partition('/')
        username, _, host_port = username_host.partition('@')
        result['username'] = username

        # 解析主机:端口
        if ':' in host_port:
            host, port = host_port.rsplit(':', 1)
            try:
                result['port'] = int(port)
                result['host'] = host
            except ValueError:
                result['host'] = host_port
        else:
            result['host'] = host_port

        if path:
            result['path'] = '/' + path
    else:
        result['host'] = uri

    return result
