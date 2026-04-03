import os


class InstallerConstants:
    REQUEST_TIMEOUT = 30

    # 控制器安装相关超时配置（秒）
    # NATS 操作超时 - 用于 download、unzip、send、run 等步骤
    # 可通过环境变量覆盖，适应大文件传输或慢网络场景
    NATS_OPERATION_TIMEOUT = int(os.getenv("NATS_OPERATION_TIMEOUT", "600"))

    # 文件传输超时 - 用于 SCP 文件传输到远程主机
    FILE_TRANSFER_TIMEOUT = int(os.getenv("FILE_TRANSFER_TIMEOUT", "1800"))

    # 命令执行超时 - 用于远程执行安装/卸载命令
    COMMAND_EXECUTE_TIMEOUT = int(os.getenv("COMMAND_EXECUTE_TIMEOUT", "900"))

    # 控制器安装任务总超时 - 需要覆盖下载、解压、远程目录准备、文件传输、安装命令
    # 默认按串行步骤预算累加，并预留少量缓冲，避免任务级超时早于单步超时
    CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS = int(
        os.getenv(
            "CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS",
            str(NATS_OPERATION_TIMEOUT * 2 + COMMAND_EXECUTE_TIMEOUT * 2 + FILE_TRANSFER_TIMEOUT + 60),
        )
    )

    INSTALL_TOKEN_EXPIRE_TIME = 60 * 30

    INSTALL_TOKEN_MAX_USAGE = 5

    DOWNLOAD_TOKEN_EXPIRE_TIME = 60 * 10

    DOWNLOAD_TOKEN_MAX_USAGE = 3

    INSTALL_TOKEN_CACHE_PREFIX = "node_install_token"

    DOWNLOAD_TOKEN_CACHE_PREFIX = "package_download_token"

    WINDOWS_INSTALLER_S3_PATH = "installer/windows/bklite-monitor-installer.exe"

    WINDOWS_INSTALLER_FILENAME = "bklite-monitor-installer.exe"
