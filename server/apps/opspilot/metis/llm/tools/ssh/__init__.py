"""SSH工具模块

这个模块提供了完整的SSH远程操作工具集，用于Agent通过SSH方式对远程设备进行管理和操作。
工具按功能分类到不同的子模块中：

- connection: SSH连接管理工具（连接测试、服务器信息获取）
- execute: 命令执行工具（执行命令、脚本、获取输出）
- transfer: SFTP文件传输工具（上传、下载、列目录、删除）
- batch: 批量操作工具（批量执行命令、批量上传、主机可用性检查）
- utils: 通用辅助函数

**主要特性：**
- 支持密码和SSH密钥认证
- 支持单机和批量操作
- 完整的文件传输功能（SFTP）
- 详细的错误处理和结果反馈
- 并发执行提高批量操作效率

**使用场景：**
- 远程服务器运维管理
- 批量配置部署
- 日志收集和分析
- 应用部署和更新
- 系统监控和巡检
"""

# 工具集构造参数元数据
from apps.opspilot.metis.llm.tools.ssh.utils import (
    prepare_ssh_config,
    resolve_key_path,
    format_command_output,
    validate_host_params,
    format_file_size,
    parse_ssh_uri,
)
from apps.opspilot.metis.llm.tools.ssh.batch import (
    batch_execute_commands,
    batch_upload_files,
    check_hosts_availability,
)
from apps.opspilot.metis.llm.tools.ssh.transfer import (
    upload_file,
    download_file,
    list_remote_directory,
    delete_remote_file,
)
from apps.opspilot.metis.llm.tools.ssh.execute import (
    ssh_execute_command,
    ssh_execute_script,
    ssh_get_command_output,
)
from apps.opspilot.metis.llm.tools.ssh.connection import (
    test_ssh_connection,
    get_ssh_server_info,
)
CONSTRUCTOR_PARAMS = [
    {
        "name": "ssh_timeout",
        "type": "integer",
        "required": False,
        "description": "SSH连接超时时间（秒），默认20秒"
    },
    {
        "name": "ssh_port",
        "type": "integer",
        "required": False,
        "description": "SSH默认端口，默认22"
    },
    {
        "name": "ssh_key_path",
        "type": "string",
        "required": False,
        "description": "SSH私钥文件路径，支持~符号，默认自动查找 ~/.ssh/id_rsa 等"
    }
]

# 导入所有工具函数


__all__ = [
    # 连接管理工具
    "test_ssh_connection",
    "get_ssh_server_info",

    # 命令执行工具
    "ssh_execute_command",
    "ssh_execute_script",
    "ssh_get_command_output",

    # 文件传输工具
    "upload_file",
    "download_file",
    "list_remote_directory",
    "delete_remote_file",

    # 批量操作工具
    "batch_execute_commands",
    "batch_upload_files",
    "check_hosts_availability",

    # 辅助函数
    "prepare_ssh_config",
    "resolve_key_path",
    "format_command_output",
    "validate_host_params",
    "format_file_size",
    "parse_ssh_uri",
]
