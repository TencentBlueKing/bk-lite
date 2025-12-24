"""SFTP文件传输工具"""
import os
import stat
from typing import Optional, Dict, Any, List
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.ssh.connection import create_ssh_client
from apps.opspilot.metis.llm.tools.ssh.utils import (
    prepare_ssh_config,
    format_file_size,
)


@tool()
def upload_file(
    host: str,
    username: str,
    local_path: str,
    remote_path: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    create_directories: bool = True,
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    通过SFTP上传文件到远程服务器

    **何时使用此工具：**
    - 上传配置文件到远程服务器
    - 部署应用文件
    - 传输脚本或数据文件
    - 分发配置模板

    **工具能力：**
    - 上传单个文件
    - 自动创建远程目录
    - 支持大文件传输
    - 返回传输统计信息

    **典型使用场景：**
    1. 配置部署：上传nginx.conf、docker-compose.yml等
    2. 脚本分发：上传运维脚本
    3. 应用部署：上传应用包

    Args:
        host (str): SSH服务器地址（必填）
        username (str): SSH用户名（必填）
        local_path (str): 本地文件路径（必填）
        remote_path (str): 远程文件路径（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        create_directories (bool): 是否自动创建远程目录，默认True
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 上传结果
            - success (bool): 是否成功
            - local_path (str): 本地文件路径
            - remote_path (str): 远程文件路径
            - file_size (str): 文件大小（人类可读格式）
            - bytes_transferred (int): 传输字节数

    **配合其他工具使用：**
    - 上传后使用 ssh_execute_command 验证文件
    - 批量上传使用 upload_directory

    **注意事项：**
    - 确保本地文件存在
    - 确保远程路径有写权限
    - 大文件传输可能较慢
    """
    ssh_config = prepare_ssh_config(config)

    # 验证本地文件存在
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"本地文件不存在: {local_path}")

    if not os.path.isfile(local_path):
        raise ValueError(f"路径不是文件: {local_path}")

    client = None
    sftp = None

    try:
        client = create_ssh_client(
            host=host,
            username=username,
            password=password,
            private_key_path=private_key_path,
            port=port,
            timeout=ssh_config.get('timeout', 20),
        )

        # 打开SFTP会话
        sftp = client.open_sftp()

        # 如果需要，创建远程目录
        if create_directories:
            remote_dir = os.path.dirname(remote_path)
            if remote_dir:
                _create_remote_directory(sftp, remote_dir)

        # 获取文件大小
        file_size = os.path.getsize(local_path)

        # 上传文件
        sftp.put(local_path, remote_path)

        return {
            'success': True,
            'local_path': local_path,
            'remote_path': remote_path,
            'file_size': format_file_size(file_size),
            'bytes_transferred': file_size,
        }

    except Exception as e:
        raise Exception(f"文件上传失败: {str(e)}")
    finally:
        if sftp:
            sftp.close()
        if client:
            client.close()


@tool()
def download_file(
    host: str,
    username: str,
    remote_path: str,
    local_path: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    create_directories: bool = True,
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    从远程服务器下载文件

    **何时使用此工具：**
    - 下载日志文件进行分析
    - 获取配置文件备份
    - 下载应用数据
    - 收集诊断信息

    **工具能力：**
    - 下载单个文件
    - 自动创建本地目录
    - 支持大文件下载

    Args:
        host (str): SSH服务器地址（必填）
        username (str): SSH用户名（必填）
        remote_path (str): 远程文件路径（必填）
        local_path (str): 本地保存路径（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        create_directories (bool): 是否自动创建本地目录，默认True
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 下载结果
            - success (bool): 是否成功
            - remote_path (str): 远程文件路径
            - local_path (str): 本地文件路径
            - file_size (str): 文件大小
            - bytes_transferred (int): 传输字节数
    """
    ssh_config = prepare_ssh_config(config)

    # 如果需要，创建本地目录
    if create_directories:
        local_dir = os.path.dirname(local_path)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir)

    client = None
    sftp = None

    try:
        client = create_ssh_client(
            host=host,
            username=username,
            password=password,
            private_key_path=private_key_path,
            port=port,
            timeout=ssh_config.get('timeout', 20),
        )

        # 打开SFTP会话
        sftp = client.open_sftp()

        # 下载文件
        sftp.get(remote_path, local_path)

        # 获取文件大小
        file_size = os.path.getsize(local_path)

        return {
            'success': True,
            'remote_path': remote_path,
            'local_path': local_path,
            'file_size': format_file_size(file_size),
            'bytes_transferred': file_size,
        }

    except Exception as e:
        raise Exception(f"文件下载失败: {str(e)}")
    finally:
        if sftp:
            sftp.close()
        if client:
            client.close()


@tool()
def list_remote_directory(
    host: str,
    username: str,
    remote_path: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    show_hidden: bool = False,
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    列出远程目录内容

    **何时使用此工具：**
    - 浏览远程目录结构
    - 查找特定文件
    - 检查文件是否存在
    - 确认部署内容

    **工具能力：**
    - 列出目录中的文件和子目录
    - 显示文件大小、权限、修改时间
    - 区分文件和目录

    Args:
        host (str): SSH服务器地址（必填）
        username (str): SSH用户名（必填）
        remote_path (str): 远程目录路径（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        show_hidden (bool): 是否显示隐藏文件，默认False
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 目录内容
            - path (str): 目录路径
            - files (list): 文件列表
            - directories (list): 子目录列表
            - total_items (int): 总项目数
    """
    ssh_config = prepare_ssh_config(config)

    client = None
    sftp = None

    try:
        client = create_ssh_client(
            host=host,
            username=username,
            password=password,
            private_key_path=private_key_path,
            port=port,
            timeout=ssh_config.get('timeout', 20),
        )

        # 打开SFTP会话
        sftp = client.open_sftp()

        # 列出目录内容
        items = sftp.listdir_attr(remote_path)

        files = []
        directories = []

        for item in items:
            # 跳过隐藏文件
            if not show_hidden and item.filename.startswith('.'):
                continue

            item_info = {
                'name': item.filename,
                'size': format_file_size(item.st_size) if item.st_size else '0 B',
                'size_bytes': item.st_size,
                'permissions': stat.filemode(item.st_mode),
                'modified': item.st_mtime,
            }

            # 区分文件和目录
            if stat.S_ISDIR(item.st_mode):
                directories.append(item_info)
            else:
                files.append(item_info)

        return {
            'path': remote_path,
            'files': files,
            'directories': directories,
            'total_items': len(files) + len(directories),
        }

    except Exception as e:
        raise Exception(f"列出目录失败: {str(e)}")
    finally:
        if sftp:
            sftp.close()
        if client:
            client.close()


@tool()
def delete_remote_file(
    host: str,
    username: str,
    remote_path: str,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    删除远程服务器上的文件

    **何时使用此工具：**
    - 清理临时文件
    - 删除过期数据
    - 清理部署产物

    **警告：**
    - 此操作不可逆
    - 请谨慎使用

    Args:
        host (str): SSH服务器地址（必填）
        username (str): SSH用户名（必填）
        remote_path (str): 要删除的远程文件路径（必填）
        password (str, optional): SSH密码
        private_key_path (str, optional): SSH私钥路径
        port (int): SSH端口，默认22
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        dict: 删除结果
            - success (bool): 是否成功
            - remote_path (str): 被删除的文件路径
    """
    ssh_config = prepare_ssh_config(config)

    client = None
    sftp = None

    try:
        client = create_ssh_client(
            host=host,
            username=username,
            password=password,
            private_key_path=private_key_path,
            port=port,
            timeout=ssh_config.get('timeout', 20),
        )

        # 打开SFTP会话
        sftp = client.open_sftp()

        # 删除文件
        sftp.remove(remote_path)

        return {
            'success': True,
            'remote_path': remote_path,
            'message': f'成功删除文件: {remote_path}'
        }

    except Exception as e:
        raise Exception(f"删除文件失败: {str(e)}")
    finally:
        if sftp:
            sftp.close()
        if client:
            client.close()


def _create_remote_directory(sftp, remote_dir: str):
    """递归创建远程目录"""
    if not remote_dir or remote_dir == '/':
        return

    try:
        sftp.stat(remote_dir)
        # 目录已存在
        return
    except IOError:
        # 目录不存在，需要创建
        pass

    # 递归创建父目录
    parent_dir = os.path.dirname(remote_dir)
    if parent_dir:
        _create_remote_directory(sftp, parent_dir)

    # 创建当前目录
    try:
        sftp.mkdir(remote_dir)
    except IOError:
        # 可能已经存在（并发创建）
        pass
