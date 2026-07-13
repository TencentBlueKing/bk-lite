"""作业管理模块常量定义"""


class TargetSource:
    """目标来源"""

    SYNC = "sync"  # 从 Node 同步，使用 execute_local / download_to_local（兼容旧值）
    MANUAL = "manual"  # 手动新增，使用 execute_ssh / download_to_remote
    NODE_MGMT = "node_mgmt"  # 节点管理，使用 execute_local / download_to_local

    CHOICES = (
        (SYNC, "同步"),
        (MANUAL, "手动"),
        (NODE_MGMT, "节点管理"),
    )


class OSType:
    """操作系统类型"""

    LINUX = "linux"
    WINDOWS = "windows"

    CHOICES = (
        (LINUX, "Linux"),
        (WINDOWS, "Windows"),
    )


class ScriptType:
    """脚本类型"""

    SHELL = "shell"
    PYTHON = "python"
    POWERSHELL = "powershell"
    BAT = "bat"

    CHOICES = (
        (SHELL, "Shell"),
        (PYTHON, "Python"),
        (POWERSHELL, "PowerShell"),
        (BAT, "Batch"),
    )

    # 映射到 Executor.execute_local 的 shell 参数
    SHELL_MAPPING = {
        SHELL: "bash",
        PYTHON: "python",
        POWERSHELL: "powershell",
        BAT: "cmd",
    }


class JobType:
    """作业类型"""

    SCRIPT = "script"
    FILE_DISTRIBUTION = "file_distribution"
    PLAYBOOK = "playbook"

    CHOICES = (
        (SCRIPT, "脚本执行"),
        (FILE_DISTRIBUTION, "文件分发"),
        (PLAYBOOK, "Playbook"),
    )


class CallbackType:
    """任务完成回调通道（调用方触发作业时按需选择，可单选或全选）

    - web:  HTTP 回调，结果 POST 到 callback_url（原 web 层方式）
    - nats: NATS 回调，结果 publish 到 callback_subject（参考 ansible 的 callback_config.subject）
    - both: 两个通道都投递
    """

    WEB = "web"
    NATS = "nats"
    BOTH = "both"

    CHOICES = (
        (WEB, "HTTP回调"),
        (NATS, "NATS回调"),
        (BOTH, "HTTP+NATS"),
    )

    # 各通道是否启用的判定辅助
    @classmethod
    def use_web(cls, value: str) -> bool:
        return value in (cls.WEB, cls.BOTH)

    @classmethod
    def use_nats(cls, value: str) -> bool:
        return value in (cls.NATS, cls.BOTH)


class ExecutionStatus:
    """执行状态"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"

    CHOICES = (
        (PENDING, "等待中"),
        (RUNNING, "执行中"),
        (SUCCESS, "成功"),
        (FAILED, "失败"),
        (TIMEOUT, "超时"),
        (CANCELLING, "取消中"),
        (CANCELLED, "已取消"),
    )

    # 终态（CANCELLING 是非终态的过渡态：已请求取消、等待真实结果回写后收敛为 CANCELLED）
    TERMINAL_STATES = (SUCCESS, FAILED, TIMEOUT, CANCELLED)


class ScheduleType:
    """定时任务类型"""

    ONCE = "once"
    CRON = "cron"

    CHOICES = (
        (ONCE, "单次执行"),
        (CRON, "周期执行"),
    )


class DangerousLevel:
    """危险等级/处理策略"""

    CONFIRM = "confirm"  # 二次确认
    FORBIDDEN = "forbidden"  # 禁止分发

    CHOICES = (
        (CONFIRM, "二次确认"),
        (FORBIDDEN, "禁止分发"),
    )


class MatchType:
    """匹配方式"""

    EXACT = "exact"  # 精确匹配（路径前缀）
    REGEX = "regex"  # 正则匹配

    CHOICES = (
        (EXACT, "精确匹配"),
        (REGEX, "正则匹配"),
    )


class ExecutorDriver:
    """执行驱动类型"""

    ANSIBLE = "ansible"
    SIDECAR = "sidecar"

    CHOICES = (
        (ANSIBLE, "Ansible"),
        (SIDECAR, "Sidecar"),
    )


class CredentialSource:
    """凭据来源"""

    MANUAL = "manual"  # 手动录入
    CREDENTIAL = "credential"  # 凭据管理

    CHOICES = (
        (MANUAL, "手动录入"),
        (CREDENTIAL, "凭据管理"),
    )


class SSHCredentialType:
    """SSH凭据类型"""

    PASSWORD = "password"  # 密码
    KEY = "key"  # 密钥

    CHOICES = (
        (PASSWORD, "密码"),
        (KEY, "密钥"),
    )


class OverwriteStrategy:
    """覆盖策略"""

    OVERWRITE = "overwrite"  # 覆盖已存在文件
    SKIP = "skip"  # 跳过已存在文件

    CHOICES = (
        (OVERWRITE, "覆盖已存在文件"),
        (SKIP, "跳过已存在文件"),
    )


class ConcurrencyPolicy:
    """并发策略"""

    SKIP = "skip"  # 跳过（上次未完成则跳过本次）
    RUN = "run"  # 运行（无论上次是否完成）
    QUEUE = "queue"  # 排队（等待上次完成后执行）

    CHOICES = (
        (SKIP, "跳过（上次未完成则跳过本次）"),
        (RUN, "运行（无论上次是否完成）"),
        (QUEUE, "排队（等待上次完成后执行）"),
    )


class TriggerSource:
    """触发来源"""

    MANUAL = "manual"  # 手动执行
    SCHEDULED = "scheduled"  # 定时任务
    API = "api"  # API 调用

    CHOICES = (
        (MANUAL, "手动执行"),
        (SCHEDULED, "定时任务"),
        (API, "API调用"),
    )


class WinRMScheme:
    """WinRM 连接协议"""

    HTTP = "http"
    HTTPS = "https"

    CHOICES = (
        (HTTP, "HTTP"),
        (HTTPS, "HTTPS"),
    )


class WinRMTransport:
    """WinRM 认证传输方式"""

    BASIC = "basic"
    NTLM = "ntlm"
    KERBEROS = "kerberos"
    CREDSSP = "credssp"

    CHOICES = (
        (BASIC, "Basic"),
        (NTLM, "NTLM"),
        (KERBEROS, "Kerberos"),
        (CREDSSP, "CredSSP"),
    )
