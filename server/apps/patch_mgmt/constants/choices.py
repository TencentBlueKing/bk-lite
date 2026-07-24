"""补丁管理模块常量定义"""


class PatchSourceType:
    """补丁源类型"""

    WSUS = "wsus"  # Windows Server Update Services
    YUM_REPO = "yum_repo"  # yum 软件源
    DNF_REPO = "dnf_repo"  # dnf 软件源
    APT_REPO = "apt_repo"  # apt 软件源

    CHOICES = (
        (WSUS, "WSUS"),
        (YUM_REPO, "yum repo"),
        (DNF_REPO, "dnf repo"),
        (APT_REPO, "apt repo"),
    )

    WINDOWS_TYPES = (WSUS,)
    LINUX_TYPES = (YUM_REPO, DNF_REPO, APT_REPO)


class OSType:
    """操作系统类型"""

    WINDOWS = "windows"
    LINUX = "linux"

    CHOICES = (
        (WINDOWS, "Windows"),
        (LINUX, "Linux"),
    )


class PatchTargetSource:
    """补丁管理目标来源"""

    MANUAL = "manual"
    NODE_MGMT = "node_mgmt"

    CHOICES = (
        (MANUAL, "手动录入"),
        (NODE_MGMT, "节点管理"),
    )


class PatchType:
    """补丁类型"""

    SECURITY = "security"  # 安全补丁
    GENERIC = "generic"  # 通用补丁

    CHOICES = (
        (SECURITY, "安全补丁"),
        (GENERIC, "通用补丁"),
    )


class PatchSeverity:
    """补丁严重级别"""

    CRITICAL = "critical"  # 严重
    IMPORTANT = "important"  # 重要
    MODERATE = "moderate"  # 中等
    LOW = "low"  # 低
    UNSPECIFIED = "unspecified"  # 未指定

    CHOICES = (
        (CRITICAL, "严重"),
        (IMPORTANT, "重要"),
        (MODERATE, "中等"),
        (LOW, "低"),
        (UNSPECIFIED, "未指定"),
    )


class PackageStatus:
    """补丁包状态（Patch 主记录层面）"""

    PENDING = "pending"  # 仅元数据，未下载
    DOWNLOADING = "downloading"  # 手工补丁包处理中
    READY = "ready"  # 已就绪（包已下载）
    DOWNLOAD_FAILED = "download_failed"  # 下载失败

    CHOICES = (
        (PENDING, "待下载"),
        (DOWNLOADING, "处理中"),
        (READY, "已就绪"),
        (DOWNLOAD_FAILED, "下载失败"),
    )


class PackageManagerType:
    """包管理器类型"""

    APT = "apt"
    YUM = "yum"
    DNF = "dnf"

    CHOICES = (
        (APT, "apt"),
        (YUM, "yum"),
        (DNF, "dnf"),
    )


class ConnectivityStatus:
    """连通性状态"""

    UNKNOWN = "unknown"
    CONNECTED = "connected"
    FAILED = "failed"

    CHOICES = (
        (UNKNOWN, "未检测"),
        (CONNECTED, "连通"),
        (FAILED, "失败"),
    )


class SSHCredentialType:
    """SSH 凭据类型"""

    PASSWORD = "password"
    KEY = "key"

    CHOICES = (
        (PASSWORD, "密码"),
        (KEY, "密钥"),
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


class RebootPolicy:
    """重启策略（对应规格：不重启 / 安装后立即重启 / 指定时间重启）"""

    NO_REBOOT = "no_reboot"    # 不重启
    IMMEDIATE = "immediate"    # 安装后立即重启
    SCHEDULED = "scheduled"    # 指定时间重启

    CHOICES = (
        (NO_REBOOT, "不重启"),
        (IMMEDIATE, "安装后立即重启"),
        (SCHEDULED, "指定时间重启"),
    )


class ComplianceStatus:
    """主机合规状态"""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PENDING = "pending"
    EVALUATING = "evaluating"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"

    CHOICES = (
        (COMPLIANT, "合规"),
        (NON_COMPLIANT, "不合规"),
        (PENDING, "待评估"),
        (EVALUATING, "评估中"),
        (FAILED, "评估失败"),
        (UNCONFIGURED, "未配置"),
    )


class RiskCompliance:
    """风险项合规状态"""

    MISSING = "missing"
    SATISFIED = "satisfied"
    INVALIDATED = "invalidated"

    CHOICES = (
        (MISSING, "缺失"),
        (SATISFIED, "已满足"),
        (INVALIDATED, "已失效"),
    )


class RemediationStatus:
    """风险项治理状态"""

    UNPLANNED = "unplanned"
    SCHEDULED = "scheduled"
    REMEDIATING = "remediating"
    PENDING_REBOOT = "pending_reboot"
    FAILED = "failed"
    FIXED = "fixed"

    CHOICES = (
        (UNPLANNED, "待修复"),
        (SCHEDULED, "已计划"),
        (REMEDIATING, "修复中"),
        (PENDING_REBOOT, "待重启"),
        (FAILED, "修复失败"),
        (FIXED, "已修复"),
    )


class GovernanceTaskType:
    """治理任务类型"""

    ASSESS = "assess"
    INSTALL = "install"
    REBOOT = "reboot"
    VERIFY = "verify"

    CHOICES = (
        (ASSESS, "评估"),
        (INSTALL, "安装"),
        (REBOOT, "重启"),
        (VERIFY, "验证"),
    )


class GovernanceTaskStatus:
    """治理任务状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_SUCCESS = "partial_success"
    PARTIAL_CANCELLED = "partial_cancelled"
    FAILED = "failed"
    CANCELLED = "cancelled"

    CHOICES = (
        (PENDING, "等待"),
        (RUNNING, "执行中"),
        (COMPLETED, "完成"),
        (PARTIAL_SUCCESS, "部分成功"),
        (PARTIAL_CANCELLED, "部分取消"),
        (FAILED, "失败"),
        (CANCELLED, "已取消"),
    )

    TERMINAL_STATES = (COMPLETED, PARTIAL_SUCCESS, PARTIAL_CANCELLED, FAILED, CANCELLED)
    ACTIVE_STATES = (PENDING, RUNNING)
