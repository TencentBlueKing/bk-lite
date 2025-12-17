from apps.node_mgmt.constants.node import NodeConstants


class ControllerConstants:
    """控制器相关常量"""

    CONTROLLER = [
        {
            "os": "linux",
            "name": "Controller",
            "description": "The Controller is primarily used to manage various types of collectors, composed of Sidecarand NAS Executor, enabling automated deployment, resource coordination, and task execution on servers.",
            "version_command": "cat /opt/fusion-collectors/VERSION",
        },
        {
            "os": "windows",
            "name": "Controller",
            "description": "The Controller is primarily used to manage various types of collectors, composed of Sidecarand NAS Executor, enabling automated deployment, resource coordination, and task execution on servers.",
            "version_command": "type C:\\Program Files\\fusion-collectors\\VERSION",
        },
    ]

    # 控制器状态
    NORMAL = "normal"
    ABNORMAL = "abnormal"
    NOT_INSTALLED = "not_installed"

    SIDECAR_STATUS_ENUM = {
        NORMAL: "正常",
        ABNORMAL: "异常",
        NOT_INSTALLED: "未安装",
    }

    # 控制器默认更新时间（秒）
    DEFAULT_UPDATE_INTERVAL = 30

    # Etag缓存时间（秒）
    E_CACHE_TIMEOUT = 60 * 5  # 5分钟

    # 控制器下发目录
    CONTROLLER_INSTALL_DIR = {
        NodeConstants.LINUX_OS: {"storage_dir": "/tmp", "install_dir": "/tmp"},
        NodeConstants.WINDOWS_OS: {"storage_dir": "/tmp", "install_dir": "C:\\gse"},
    }

    # 设置权限并运行命令
    RUN_COMMAND = {
        NodeConstants.LINUX_OS: (
            "sudo rm -rf /opt/fusion-collectors && "
            "sudo mv /tmp/fusion-collectors /opt/fusion-collectors && "
            "sudo chmod -R +x /opt/fusion-collectors/* && "
            "cd /opt/fusion-collectors && "
            "sudo bash ./install.sh {server_url}/api/v1/node_mgmt/open_api/node "
            "{server_token} {cloud} {group} {node_name} {node_id}"
        ),
        NodeConstants.WINDOWS_OS: (
            "powershell -command "
            "\"Set-ExecutionPolicy Unrestricted -Force; & "
            "'{}\\install.ps1' -ServerUrl {} -ServerToken {} -Cloud {} -Group {} -NodeName {} -NodeId {}\""
        ),
    }

    # 手动安装命令
    MANUAL_INSTALL_COMMAND = {
        NodeConstants.LINUX_OS: (
            "sudo rm -rf /tmp/fusion-collectors /tmp/fusion-collectors.zip && "
            "cd /tmp && "
            "curl -L -o fusion-collectors.zip '{server_url}/api/v1/node_mgmt/open_api/download/fusion_collector/{package_id}' && "
            "unzip -o fusion-collectors.zip && "
            "sudo rm -rf /opt/fusion-collectors && "
            "sudo mv fusion-collectors /opt/fusion-collectors && "
            "sudo chmod -R +x /opt/fusion-collectors/* && "
            "cd /opt/fusion-collectors && "
            "sudo bash ./install.sh {server_url}/api/v1/node_mgmt/open_api/node "
            "{server_token} {cloud} {group} {node_name} {node_id}"
        ),
        NodeConstants.WINDOWS_OS: (
            "powershell -ExecutionPolicy Unrestricted -Command \""
            "$packageUrl = '{server_url}/api/v1/node_mgmt/open_api/download/fusion_collector/{package_id}'; "
            "$downloadPath = 'C:\\temp\\fusion-collectors.zip'; "
            "$extractPath = 'C:\\gse'; "
            "New-Item -ItemType Directory -Force -Path C:\\temp | Out-Null; "
            "if (Test-Path $downloadPath) {{ Remove-Item -Path $downloadPath -Force }}; "
            "Write-Host 'Downloading package...'; "
            "Invoke-WebRequest -Uri $packageUrl -OutFile $downloadPath; "
            "if (Test-Path $extractPath\\fusion-collectors) {{ Remove-Item -Path $extractPath\\fusion-collectors -Recurse -Force }}; "
            "Write-Host 'Extracting package...'; "
            "Add-Type -AssemblyName System.IO.Compression.FileSystem; "
            "[System.IO.Compression.ZipFile]::ExtractToDirectory($downloadPath, $extractPath); "
            "Write-Host 'Running installation script...'; "
            "& '$extractPath\\fusion-collectors\\install.ps1' "
            "-ServerUrl '{server_url}/api/v1/node_mgmt/open_api/node' "
            "-ServerToken '{server_token}' "
            "-Cloud '{cloud}' "
            "-Group '{group}' "
            "-NodeName '{node_name}' "
            "-NodeId '{node_id}'\""
        ),
    }

    # 卸载命令
    UNINSTALL_COMMAND = {
        NodeConstants.LINUX_OS: "cd /opt/fusion-collectors && ./uninstall.sh",
        NodeConstants.WINDOWS_OS: "powershell -command \"Remove-Item -Path {} -Recurse\"",
    }

    # 控制器目录删除命令
    CONTROLLER_DIR_DELETE_COMMAND = {
        NodeConstants.LINUX_OS: "rm -rf /opt/fusion-collectors",
        NodeConstants.WINDOWS_OS: "powershell -command \"Remove-Item -Path {} -Recurse\"",
    }

    # 标签字段
    GROUP_TAG = "group"
    CLOUD_TAG = "zone"
    INSTALL_METHOD_TAG = "install_method"
    NODE_TYPE_TAG = "node_type"  # 节点类型标签（用于标识容器节点、K8s节点等）

    # 安装方式
    MANUAL = "manual"
    AUTO = "auto"

    INSTALL_METHOD_ENUM = {
        MANUAL: "手动安装",
        AUTO: "自动安装",
    }

    # 节点类型
    NODE_TYPE_CONTAINER = "container"  # 容器节点
    NODE_TYPE_HOST = "host"  # 主机节点

    NODE_TYPE_ENUM = {
        NODE_TYPE_CONTAINER: "容器节点",
        NODE_TYPE_HOST: "主机节点",
    }

    WAITING = "waiting"
    INSTALLED = "installed"
    # 手动安装控制器状态
    MANUAL_INSTALL_STATUS_ENUM = {
        WAITING: "等待安装",
        INSTALLED: "安装成功",
    }