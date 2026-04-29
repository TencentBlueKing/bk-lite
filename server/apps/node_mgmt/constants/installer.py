import os


def _installer_filename(target_os: str) -> str:
    return "bklite-controller-installer.exe" if target_os == "windows" else "bklite-controller-installer"


def _installer_alias_path(target_os: str, architecture: str = "generic") -> str:
    return f"installer/{target_os}/{architecture}/{_installer_filename(target_os)}"


class InstallerConstants:
    REQUEST_TIMEOUT = 30
    CONTROLLER_INSTALL_MAX_PARALLEL = 3

    EXECUTION_PHASE_KEY = "execution_phase"
    EXECUTION_ATTEMPT_KEY = "execution_attempt"
    EXECUTION_PHASE_BOOTSTRAP_RUNNING = "bootstrap_running"
    EXECUTION_PHASE_CONNECTIVITY_WAITING = "connectivity_waiting"
    EXECUTION_PHASE_FINISHED = "finished"

    STEP_STATUS_WAITING = "waiting"
    STEP_STATUS_RUNNING = "running"
    STEP_STATUS_SUCCESS = "success"
    STEP_STATUS_ERROR = "error"

    OVERALL_STATUS_WAITING = "waiting"
    OVERALL_STATUS_RUNNING = "running"
    OVERALL_STATUS_SUCCESS = "success"
    OVERALL_STATUS_ERROR = "error"
    OVERALL_STATUS_TIMEOUT = "timeout"
    OVERALL_STATUS_CANCELLED = "cancelled"

    INSTALLER_EVENT_STATUS_MAP = {
        "running": STEP_STATUS_RUNNING,
        "success": STEP_STATUS_SUCCESS,
        "failed": STEP_STATUS_ERROR,
        "error": STEP_STATUS_ERROR,
        "skipped": STEP_STATUS_SUCCESS,
    }

    INSTALLER_EVENT_STEP_MAP = {
        "fetch_session": "fetch_session",
        "prepare_directories": "prepare_dirs",
        "download_package": "download",
        "extract_package": "extract",
        "configure_runtime": "write_config",
        "run_package_installer": "install",
        "complete": "install_complete",
    }

    INSTALLER_STEP_SEQUENCE = [
        "fetch_session",
        "prepare_dirs",
        "download",
        "extract",
        "write_config",
        "install",
        "install_complete",
    ]

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

    DEFAULT_INSTALLER_VERSION = os.getenv("INSTALLER_DEFAULT_VERSION", "latest")

    WINDOWS_INSTALLER_FILENAME = _installer_filename("windows")
    LINUX_INSTALLER_FILENAME = _installer_filename("linux")

    WINDOWS_INSTALL_DEFAULT_DIR = r"C:\fusion-collectors"
    LINUX_INSTALL_DEFAULT_DIR = "/opt/fusion-collectors"

    @classmethod
    def build_versioned_installer_path(cls, target_os: str, architecture: str = "generic", version: str | None = None) -> str:
        installer_version = version or cls.DEFAULT_INSTALLER_VERSION
        filename = cls.WINDOWS_INSTALLER_FILENAME if target_os == "windows" else cls.LINUX_INSTALLER_FILENAME
        return f"installer/{target_os}/{architecture}/{installer_version}/{filename}"

    @classmethod
    def build_latest_alias_path(cls, target_os: str, architecture: str = "generic") -> str:
        filename = cls.WINDOWS_INSTALLER_FILENAME if target_os == "windows" else cls.LINUX_INSTALLER_FILENAME
        return f"installer/{target_os}/{architecture}/{filename}"

    WINDOWS_INSTALLER_S3_PATH = _installer_alias_path("windows")
    LINUX_INSTALLER_S3_PATH = _installer_alias_path("linux")
