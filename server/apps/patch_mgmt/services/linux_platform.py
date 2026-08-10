"""Linux 原生包生态的事实探测、解析与校验。"""

from __future__ import annotations

from dataclasses import dataclass

from apps.patch_mgmt.constants import PackageManagerType


HOST_FACT_PREFIX = "BKPATCH_HOST|LINUX|"
SUPPORTED_PACKAGE_MANAGERS = {
    PackageManagerType.APT,
    PackageManagerType.DNF,
    PackageManagerType.YUM,
}


@dataclass(frozen=True)
class LinuxHostFacts:
    """影响补丁适用性及执行命令选择的 Linux 主机事实。"""

    distro_id: str = ""
    distro_like: tuple[str, ...] = ()
    version_id: str = ""
    architecture: str = ""
    package_manager: str = ""


def package_manager_family(value: str) -> str:
    """把补丁源/包管理器兼容值归一为 apt 或 rpm 家族。"""
    manager = PackageManagerType.normalize(str(value or "").strip().lower())
    if manager == PackageManagerType.APT:
        return "apt"
    if manager in {PackageManagerType.DNF, PackageManagerType.YUM}:
        return "rpm"
    return ""


def linux_host_facts_command(*, marker: str = "") -> str:
    """生成 POSIX sh 可执行的只读事实探测命令。

    判断依据是原生包数据库，不是系统里恰好存在的命令。这样 Ubuntu 即使额外
    安装了 dnf 也仍识别为 APT；RPM 主机则在 dnf/yum 之间选择实际可用者。
    """
    marker_command = f"printf '%s\\n' '{marker}'; " if marker else ""
    return (
        "os_id=''; os_like=''; os_version=''; "
        "if [ -r /etc/os-release ]; then . /etc/os-release; "
        "os_id=${ID:-}; os_like=${ID_LIKE:-}; os_version=${VERSION_ID:-}; fi; "
        "host_arch=$(uname -m 2>/dev/null); "
        "has_dpkg=0; has_rpm=0; "
        "if command -v dpkg-query >/dev/null 2>&1 && [ -s /var/lib/dpkg/status ] "
        "&& dpkg-query -W >/dev/null 2>&1; then has_dpkg=1; fi; "
        "if command -v rpm >/dev/null 2>&1 "
        "&& [ -n \"$(rpm -qa --qf '%{NAME}\\n' 2>/dev/null | sed -n '1p')\" ]; then has_rpm=1; fi; "
        "if [ \"$has_dpkg\" -eq 1 ] && [ \"$has_rpm\" -eq 1 ]; then manager=conflict; "
        "elif [ \"$has_dpkg\" -eq 1 ]; then "
        "if command -v apt-get >/dev/null 2>&1; then manager=apt; else manager=unknown; fi; "
        "elif [ \"$has_rpm\" -eq 1 ]; then "
        "if command -v dnf >/dev/null 2>&1; then manager=dnf; "
        "elif command -v yum >/dev/null 2>&1; then manager=yum; else manager=unknown; fi; "
        "else manager=unknown; fi; "
        + marker_command
        + "printf 'BKPATCH_HOST|LINUX|%s|%s|%s|%s|%s\\n' "
        '"$os_id" "$os_like" "$os_version" "$host_arch" "$manager"'
    )


def parse_linux_host_facts(stdout: str) -> LinuxHostFacts:
    """解析事实协议；旧输出缺少协议时返回空事实，由调用方决定兼容策略。"""
    for raw_line in str(stdout or "").splitlines():
        if not raw_line.startswith(HOST_FACT_PREFIX):
            continue
        parts = raw_line.split("|", 6)
        if len(parts) != 7:
            continue
        _, _, distro_id, distro_like, version_id, architecture, package_manager = parts
        return LinuxHostFacts(
            distro_id=distro_id.strip(),
            distro_like=tuple(distro_like.strip().split()),
            version_id=version_id.strip(),
            architecture=architecture.strip(),
            package_manager=package_manager.strip().lower(),
        )
    return LinuxHostFacts()


def validate_linux_host_facts(facts: LinuxHostFacts) -> str:
    """返回不可安全执行评估/治理的原因；空串表示事实完整。"""
    missing = []
    if not facts.distro_id:
        missing.append("发行版")
    if not facts.version_id:
        missing.append("系统版本")
    if not facts.architecture:
        missing.append("架构")
    if missing:
        return f"主机事实缺少：{', '.join(missing)}"
    if facts.package_manager == "conflict":
        return "同时检测到有效的 dpkg 与 RPM 原生包数据库，无法安全确定包生态"
    if facts.package_manager not in SUPPORTED_PACKAGE_MANAGERS:
        return "未识别到可用的原生包管理器（apt-get、dnf 或 yum）"
    return ""
