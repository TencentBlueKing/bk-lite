"""SSH连接管理工具"""
import paramiko
from typing import Optional, Dict, Any
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.ssh.utils import (
    prepare_ssh_config,
    resolve_key_path,
    validate_host_params,
)


def create_ssh_client(
    host: str,
    username: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    timeout: int = 20,
    look_for_keys: bool = True,
) -> paramiko.SSHClient:
    """
    创建并返回已连接的SSH客户端

    Args:
        host: SSH服务器地址
        username: SSH用户名
        password: SSH密码（可选）
        private_key_path: SSH私钥路径（可选）
        port: SSH端口，默认22
        timeout: 连接超时时间（秒），默认20
        look_for_keys: 是否自动查找SSH密钥，默认True

    Returns:
        paramiko.SSHClient: 已连接的SSH客户端

    Raises:
        ValueError: 参数无效
        paramiko.AuthenticationException: 认证失败
        paramiko.SSHException: SSH连接失败
    """
    validate_host_params(host, username)

    # 创建SSH客户端
    client = paramiko.SSHClient()

    # 自动添加主机密钥（生产环境应该使用更安全的策略）
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # 准备连接参数
    connect_params = {
        'hostname': host.strip(),
        'username': username.strip(),
        'port': port,
        'timeout': timeout,
        'look_for_keys': look_for_keys,
    }

    # 认证方式优先级：私钥 > 密码 > 自动查找密钥
    if private_key_path:
        key_path = resolve_key_path(private_key_path)
        if not key_path:
            raise ValueError(f"SSH私钥文件不存在: {private_key_path}")

        try:
            # 尝试加载私钥
            private_key = paramiko.RSAKey.from_private_key_file(key_path)
            connect_params['pkey'] = private_key
            connect_params['look_for_keys'] = False
        except paramiko.PasswordRequiredException:
            raise ValueError(f"私钥文件需要密码: {key_path}")
        except Exception as e:
            raise ValueError(f"加载私钥失败: {str(e)}")
    elif password:
        connect_params['password'] = password
        connect_params['look_for_keys'] = False

    # 建立连接
    try:
        client.connect(**connect_params)
        return client
    except paramiko.AuthenticationException as e:
        raise paramiko.AuthenticationException(
            f"SSH认证失败 - 主机: {host}, 用户: {username}. "
            f"请检查密码或密钥是否正确。详细信息: {str(e)}"
        )
    except paramiko.SSHException as e:
        raise paramiko.SSHException(
            f"SSH连接失败 - 主机: {host}:{port}. "
            f"请检查主机地址、端口和网络连接。详细信息: {str(e)}"
        )
    except Exception as e:
        raise Exception(
            f"建立SSH连接时发生未知错误 - 主机: {host}:{port}. "
            f"详细信息: {str(e)}"
        )


@tool()
def test_ssh_connection(
    host: str,
    username: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    timeout: int = 10,
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    测试SSH连接是否可用

    **何时使用此工具：**
    - 在执行SSH操作前验证连接
    - 检查SSH服务器是否可达
    - 验证认证凭据是否正确
    - 排查SSH连接问题

    **工具能力：**
    - 支持密码认证
    - 支持SSH密钥认证
    - 支持自定义端口
    - 返回详细的连接状态和服务器信息

    **典型使用场景：**
    1. 验证新主机连接：确保主机可达且凭据正确
    2. 批量操作前检查：避免批量操作时部分主机失败
    3. 故障诊断：确定是网络问题还是认证问题

    Args:
        host (str): SSH服务器地址（必填）
        username (str): SSH用户名（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径（PEM格式）
        port (int): SSH端口，默认22
        timeout (int): 连接超时时间（秒），默认10
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 连接测试结果
            - success (bool): 连接是否成功
            - message (str): 结果消息
            - server_info (dict): 服务器信息（成功时返回）
                - hostname: 主机名
                - banner: SSH服务器标识
            - error (str): 错误信息（失败时返回）

    **注意事项：**
    - 此工具不执行任何命令，仅测试连接
    - 密码和私钥至少提供一个
    - 私钥路径支持~符号
    """
    ssh_config = prepare_ssh_config(config)

    # 配置优先级：参数 > config
    if port == 22 and ssh_config.get('port'):
        port = ssh_config['port']
    if timeout == 10 and ssh_config.get('timeout'):
        timeout = ssh_config['timeout']

    client = None
    try:
        # 尝试建立连接
        client = create_ssh_client(
            host=host,
            username=username,
            password=password,
            private_key_path=private_key_path,
            port=port,
            timeout=timeout,
        )

        # 获取服务器信息
        transport = client.get_transport()
        server_info = {
            'hostname': host,
            'banner': transport.remote_version if transport else 'Unknown',
        }

        return {
            'success': True,
            'message': f'成功连接到 {username}@{host}:{port}',
            'server_info': server_info,
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'连接失败: {username}@{host}:{port}',
            'error': str(e),
        }
    finally:
        if client:
            client.close()


@tool()
def get_ssh_server_info(
    host: str,
    username: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    获取SSH服务器详细信息

    **何时使用此工具：**
    - 查看远程主机的系统信息
    - 收集服务器环境数据
    - 检查系统版本和配置

    **工具能力：**
    - 获取操作系统信息
    - 获取主机名和内核版本
    - 获取SSH服务器版本
    - 获取系统架构信息

    Args:
        host (str): SSH服务器地址（必填）
        username (str): SSH用户名（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 服务器信息
            - hostname: 主机名
            - os_info: 操作系统信息
            - kernel: 内核版本
            - architecture: 系统架构
            - ssh_banner: SSH服务器标识
    """
    ssh_config = prepare_ssh_config(config)
    timeout = ssh_config.get('timeout', 20)

    client = None
    try:
        client = create_ssh_client(
            host=host,
            username=username,
            password=password,
            private_key_path=private_key_path,
            port=port,
            timeout=timeout,
        )

        # 获取系统信息
        commands = {
            'hostname': 'hostname',
            'os_info': 'cat /etc/os-release 2>/dev/null || uname -s',
            'kernel': 'uname -r',
            'architecture': 'uname -m',
        }

        info = {}
        for key, cmd in commands.items():
            stdin, stdout, stderr = client.exec_command(cmd)
            output = stdout.read().decode('utf-8').strip()
            info[key] = output

        # 获取SSH服务器banner
        transport = client.get_transport()
        info['ssh_banner'] = transport.remote_version if transport else 'Unknown'

        return info

    except Exception as e:
        raise Exception(f"获取服务器信息失败: {str(e)}")
    finally:
        if client:
            client.close()
