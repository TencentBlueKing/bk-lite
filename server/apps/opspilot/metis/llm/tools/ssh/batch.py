"""批量SSH操作工具"""
import concurrent.futures
from typing import Optional, Dict, Any, List
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.ssh.execute import ssh_execute_command
from apps.opspilot.metis.llm.tools.ssh.transfer import upload_file


@tool()
def batch_execute_commands(
    hosts: List[str],
    username: str,
    command: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    timeout: int = 20,
    max_workers: int = 10,
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    在多台服务器上批量执行相同的命令

    **何时使用此工具：**
    - 在多台服务器上执行相同的运维操作
    - 批量检查集群状态
    - 同时收集多台服务器的信息
    - 批量配置变更

    **工具能力：**
    - 并发执行，提高效率
    - 自动汇总所有服务器的结果
    - 区分成功和失败的主机
    - 支持自定义并发数

    **典型使用场景：**
    1. 集群巡检：
       - hosts=["web1", "web2", "web3"]
       - command="df -h"
    2. 服务状态检查：
       - command="systemctl status nginx"
    3. 批量重启服务：
       - command="systemctl restart app"
    4. 日志收集：
       - command="tail -n 100 /var/log/app.log"

    Args:
        hosts (list): SSH服务器地址列表（必填）
        username (str): SSH用户名（必填）
        command (str): 要执行的命令（必填）
        password (str, optional): SSH密码（所有主机使用相同密码）
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        timeout (int): 命令执行超时时间（秒），默认20
        max_workers (int): 最大并发数，默认10
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 批量执行结果
            - total (int): 总主机数
            - success_count (int): 成功数量
            - failed_count (int): 失败数量
            - results (dict): 每台主机的详细结果
                key: 主机地址
                value: 命令执行结果
            - summary (dict): 汇总信息
                - successful_hosts (list): 成功的主机列表
                - failed_hosts (list): 失败的主机列表

    **配合其他工具使用：**
    - 执行前可先用 test_ssh_connection 测试连接
    - 复杂任务可用 ssh_execute_script

    **注意事项：**
    - 所有主机必须使用相同的认证凭据
    - 并发数过大可能影响网络和本地性能
    - 建议先在单台主机测试命令
    - 失败的主机不影响其他主机的执行
    """
    if not hosts:
        raise ValueError("主机列表不能为空")

    results = {}
    successful_hosts = []
    failed_hosts = []

    def execute_on_host(host):
        try:
            result = ssh_execute_command(
                host=host,
                username=username,
                command=command,
                password=password,
                private_key_path=private_key_path,
                port=port,
                timeout=timeout,
                config=config
            )
            return host, result
        except Exception as e:
            return host, {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'exit_code': -1,
                'error': str(e)
            }

    # 并发执行
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(execute_on_host, host) for host in hosts]

        for future in concurrent.futures.as_completed(futures):
            host, result = future.result()
            results[host] = result

            if result.get('success', False):
                successful_hosts.append(host)
            else:
                failed_hosts.append(host)

    return {
        'total': len(hosts),
        'success_count': len(successful_hosts),
        'failed_count': len(failed_hosts),
        'results': results,
        'summary': {
            'successful_hosts': successful_hosts,
            'failed_hosts': failed_hosts,
        }
    }


@tool()
def batch_upload_files(
    hosts: List[str],
    username: str,
    local_path: str,
    remote_path: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    max_workers: int = 10,
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    批量上传文件到多台服务器

    **何时使用此工具：**
    - 批量分发配置文件
    - 同时部署脚本到多台服务器
    - 集群配置同步

    **工具能力：**
    - 并发上传，提高效率
    - 自动汇总上传结果
    - 区分成功和失败的主机

    **典型使用场景：**
    1. 配置分发：
       - local_path="/path/to/nginx.conf"
       - remote_path="/etc/nginx/nginx.conf"
    2. 脚本部署：
       - local_path="./deploy.sh"
       - remote_path="/opt/scripts/deploy.sh"

    Args:
        hosts (list): SSH服务器地址列表（必填）
        username (str): SSH用户名（必填）
        local_path (str): 本地文件路径（必填）
        remote_path (str): 远程文件路径（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        max_workers (int): 最大并发数，默认10
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 批量上传结果
            - total (int): 总主机数
            - success_count (int): 成功数量
            - failed_count (int): 失败数量
            - results (dict): 每台主机的详细结果
            - summary (dict): 汇总信息
    """
    if not hosts:
        raise ValueError("主机列表不能为空")

    results = {}
    successful_hosts = []
    failed_hosts = []

    def upload_to_host(host):
        try:
            result = upload_file(
                host=host,
                username=username,
                local_path=local_path,
                remote_path=remote_path,
                password=password,
                private_key_path=private_key_path,
                port=port,
                config=config
            )
            return host, result
        except Exception as e:
            return host, {
                'success': False,
                'error': str(e)
            }

    # 并发上传
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(upload_to_host, host) for host in hosts]

        for future in concurrent.futures.as_completed(futures):
            host, result = future.result()
            results[host] = result

            if result.get('success', False):
                successful_hosts.append(host)
            else:
                failed_hosts.append(host)

    return {
        'total': len(hosts),
        'success_count': len(successful_hosts),
        'failed_count': len(failed_hosts),
        'results': results,
        'summary': {
            'successful_hosts': successful_hosts,
            'failed_hosts': failed_hosts,
        }
    }


@tool()
def check_hosts_availability(
    hosts: List[str],
    username: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    timeout: int = 10,
    max_workers: int = 20,
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    批量检查SSH主机连接状态

    **何时使用此工具：**
    - 批量操作前验证主机可达性
    - 检查集群主机状态
    - 快速定位连接问题

    **工具能力：**
    - 快速并发检查
    - 返回可用和不可用主机列表
    - 提供详细的连接错误信息

    Args:
        hosts (list): SSH服务器地址列表（必填）
        username (str): SSH用户名（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        timeout (int): 连接超时时间（秒），默认10
        max_workers (int): 最大并发数，默认20
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 主机可用性检查结果
            - total (int): 总主机数
            - available_count (int): 可用主机数
            - unavailable_count (int): 不可用主机数
            - available_hosts (list): 可用主机列表
            - unavailable_hosts (list): 不可用主机列表
            - details (dict): 每台主机的详细检查结果
    """
    from apps.opspilot.metis.llm.tools.ssh.connection import test_ssh_connection

    if not hosts:
        raise ValueError("主机列表不能为空")

    available_hosts = []
    unavailable_hosts = []
    details = {}

    def check_host(host):
        try:
            result = test_ssh_connection(
                host=host,
                username=username,
                password=password,
                private_key_path=private_key_path,
                port=port,
                timeout=timeout,
                config=config
            )
            return host, result
        except Exception as e:
            return host, {
                'success': False,
                'error': str(e)
            }

    # 并发检查
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(check_host, host) for host in hosts]

        for future in concurrent.futures.as_completed(futures):
            host, result = future.result()
            details[host] = result

            if result.get('success', False):
                available_hosts.append(host)
            else:
                unavailable_hosts.append(host)

    return {
        'total': len(hosts),
        'available_count': len(available_hosts),
        'unavailable_count': len(unavailable_hosts),
        'available_hosts': available_hosts,
        'unavailable_hosts': unavailable_hosts,
        'details': details,
    }
