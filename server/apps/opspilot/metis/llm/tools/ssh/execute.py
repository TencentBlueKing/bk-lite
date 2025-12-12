"""SSH命令执行工具"""
import time
from typing import Optional, Dict, Any, List
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.ssh.connection import create_ssh_client
from apps.opspilot.metis.llm.tools.ssh.utils import (
    prepare_ssh_config,
    format_command_output,
)


@tool()
def ssh_execute_command(
    host: str,
    username: str,
    command: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    timeout: int = 20,
    working_directory: Optional[str] = None,
    environment: Optional[Dict[str, str]] = None,
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    在远程SSH服务器上执行命令

    **何时使用此工具：**
    - 执行任意Shell命令
    - 查看系统状态（如df、ps、top等）
    - 管理服务（如systemctl、service等）
    - 执行运维脚本
    - 检查应用状态

    **工具能力：**
    - 执行任意Shell命令
    - 捕获标准输出和标准错误
    - 返回命令退出码
    - 支持设置工作目录
    - 支持环境变量注入
    - 自动处理命令超时

    **典型使用场景：**
    1. 系统监控：
       - command="df -h" 查看磁盘使用
       - command="free -m" 查看内存使用
       - command="top -bn1" 查看进程状态
    2. 服务管理：
       - command="systemctl status nginx" 查看服务状态
       - command="docker ps" 查看容器状态
    3. 日志查看：
       - command="tail -n 100 /var/log/app.log"
    4. 脚本执行：
       - command="bash /path/to/script.sh"

    Args:
        host (str): SSH服务器地址（必填）
        username (str): SSH用户名（必填）
        command (str): 要执行的命令（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        timeout (int): 命令执行超时时间（秒），默认20
        working_directory (str, optional): 命令执行的工作目录
        environment (dict, optional): 环境变量字典
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 命令执行结果
            - stdout (str): 标准输出
            - stderr (str): 标准错误
            - exit_code (int): 退出码（0表示成功）
            - success (bool): 是否执行成功
            - command (str): 执行的命令
            - duration (float): 执行时长（秒）

    **配合其他工具使用：**
    - 执行前先使用 test_ssh_connection 验证连接
    - 批量执行使用 batch_execute_commands
    - 需要上传脚本先使用 upload_file

    **注意事项：**
    - 长时间运行的命令可能超时，建议调整timeout参数
    - 交互式命令（如vim）不支持
    - 某些命令需要sudo权限，确保用户有相应权限
    - 输出过长可能影响性能，建议使用管道过滤
    """
    ssh_config = prepare_ssh_config(config)

    # 配置优先级：参数 > config
    if timeout == 20 and ssh_config.get('timeout'):
        timeout = ssh_config['timeout']

    client = None
    start_time = time.time()

    try:
        client = create_ssh_client(
            host=host,
            username=username,
            password=password,
            private_key_path=private_key_path,
            port=port,
            timeout=timeout,
        )

        # 构建完整命令
        full_command = command

        # 如果指定了工作目录，添加cd命令
        if working_directory:
            full_command = f"cd {working_directory} && {command}"

        # 如果指定了环境变量，添加export命令
        if environment:
            env_exports = " ".join(
                [f"export {k}={v};" for k, v in environment.items()])
            full_command = f"{env_exports} {full_command}"

        # 执行命令
        stdin, stdout, stderr = client.exec_command(
            full_command, timeout=timeout)

        # 读取输出
        stdout_data = stdout.read().decode('utf-8')
        stderr_data = stderr.read().decode('utf-8')
        exit_code = stdout.channel.recv_exit_status()

        duration = time.time() - start_time

        result = format_command_output(stdout_data, stderr_data, exit_code)
        result.update({
            'command': command,
            'duration': round(duration, 2),
        })

        return result

    except Exception as e:
        duration = time.time() - start_time
        return {
            'stdout': '',
            'stderr': str(e),
            'exit_code': -1,
            'success': False,
            'command': command,
            'duration': round(duration, 2),
            'error': f"命令执行失败: {str(e)}"
        }
    finally:
        if client:
            client.close()


@tool()
def ssh_execute_script(
    host: str,
    username: str,
    script_content: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    timeout: int = 60,
    interpreter: str = "/bin/bash",
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    在远程服务器上执行脚本内容

    **何时使用此工具：**
    - 执行多行Shell脚本
    - 运行复杂的自动化任务
    - 无需先上传脚本文件

    **工具能力：**
    - 直接执行脚本内容，无需上传文件
    - 支持多种解释器（bash、sh、python等）
    - 捕获完整输出和错误

    **典型使用场景：**
    1. 多步骤运维任务
    2. 系统初始化脚本
    3. 批量配置变更

    Args:
        host (str): SSH服务器地址（必填）
        username (str): SSH用户名（必填）
        script_content (str): 脚本内容（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        timeout (int): 脚本执行超时时间（秒），默认60
        interpreter (str): 脚本解释器，默认/bin/bash
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 脚本执行结果（格式同ssh_execute_command）
    """
    ssh_config = prepare_ssh_config(config)

    client = None
    start_time = time.time()

    try:
        client = create_ssh_client(
            host=host,
            username=username,
            password=password,
            private_key_path=private_key_path,
            port=port,
            timeout=ssh_config.get('timeout', 20),
        )

        # 通过stdin传递脚本内容
        command = interpreter
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

        # 写入脚本内容
        stdin.write(script_content)
        stdin.close()

        # 读取输出
        stdout_data = stdout.read().decode('utf-8')
        stderr_data = stderr.read().decode('utf-8')
        exit_code = stdout.channel.recv_exit_status()

        duration = time.time() - start_time

        result = format_command_output(stdout_data, stderr_data, exit_code)
        result.update({
            'command': f'<script via {interpreter}>',
            'duration': round(duration, 2),
        })

        return result

    except Exception as e:
        duration = time.time() - start_time
        return {
            'stdout': '',
            'stderr': str(e),
            'exit_code': -1,
            'success': False,
            'command': '<script>',
            'duration': round(duration, 2),
            'error': f"脚本执行失败: {str(e)}"
        }
    finally:
        if client:
            client.close()


@tool()
def ssh_get_command_output(
    host: str,
    username: str,
    command: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    config: RunnableConfig = None
) -> str:
    """
    执行命令并只返回标准输出（简化版）

    **何时使用此工具：**
    - 只需要命令的输出结果
    - 不关心错误信息和退出码
    - 快速获取信息

    **工具能力：**
    - 简化的返回格式
    - 只返回stdout字符串

    **典型使用场景：**
    1. 获取配置文件内容：command="cat /etc/config.yaml"
    2. 获取系统信息：command="hostname"
    3. 查询数据：command="mysql -e 'SELECT COUNT(*) FROM users;'"

    Args:
        host (str): SSH服务器地址（必填）
        username (str): SSH用户名（必填）
        command (str): 要执行的命令（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        str: 命令的标准输出（仅字符串）

    **注意事项：**
    - 如果命令失败，会抛出异常
    - 不返回stderr和exit_code
    - 适用于简单查询场景
    """
    result = ssh_execute_command(
        host=host,
        username=username,
        command=command,
        password=password,
        private_key_path=private_key_path,
        port=port,
        config=config
    )

    if not result['success']:
        raise Exception(f"命令执行失败: {result.get('error', result['stderr'])}")

    return result['stdout']
