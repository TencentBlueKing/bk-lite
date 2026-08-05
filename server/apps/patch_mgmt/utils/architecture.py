"""补丁管理 CPU 架构规范化。

模块内部只使用 BK-Lite 平台规范值 ``x86_64`` / ``arm64``；APT、RPM、
WSUS 等外部系统的命名差异只在对应 Adapter 调用 ``repository_architecture``
时暴露。
"""

from collections.abc import Iterable

from apps.node_mgmt.constants.node import NodeConstants
from apps.patch_mgmt.constants import OSType, PatchSourceType

X86_64 = NodeConstants.X86_64_ARCH
ARM64 = NodeConstants.ARM64_ARCH

ARCHITECTURE_CHOICES = (
    (X86_64, "x86_64"),
    (ARM64, "ARM64"),
)

_ALIASES = {
    **NodeConstants.CPU_ARCH_ALIASES,
    "x64": X86_64,
}

_INDEPENDENT_ARCHITECTURES = {"all", "any", "noarch"}

_SUPPORTED_BY_OS = {
    OSType.LINUX: (X86_64, ARM64),
    OSType.WINDOWS: (X86_64,),
}

_REPOSITORY_ARCHITECTURES = {
    PatchSourceType.APT_REPO: {
        X86_64: "amd64",
        ARM64: "arm64",
    },
    PatchSourceType.YUM_REPO: {
        X86_64: "x86_64",
        ARM64: "aarch64",
    },
    PatchSourceType.DNF_REPO: {
        X86_64: "x86_64",
        ARM64: "aarch64",
    },
    PatchSourceType.WSUS: {
        X86_64: "x64",
        ARM64: "ARM64",
    },
}


class UnsupportedArchitecture(ValueError):
    """输入架构不在 BK-Lite 支持矩阵中。"""


def normalize_architecture(value, *, default: str = "") -> str:
    """把平台别名归一为 ``x86_64`` / ``arm64``。"""
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    normalized = _ALIASES.get(raw)
    if not normalized:
        raise UnsupportedArchitecture(f"不支持的 CPU 架构: {value}")
    return normalized


def normalize_architectures(values: Iterable, *, fallback: str = "") -> list[str]:
    """归一化架构列表，并把 ``all`` / ``noarch`` 收敛到补丁源目标架构。"""
    normalized_fallback = normalize_architecture(fallback) if fallback else ""
    normalized_values = []
    for value in values or []:
        raw = str(value or "").strip().lower()
        if not raw:
            continue
        if raw in _INDEPENDENT_ARCHITECTURES:
            if not normalized_fallback:
                continue
            normalized = normalized_fallback
        else:
            normalized = normalize_architecture(raw)
        if normalized not in normalized_values:
            normalized_values.append(normalized)
    return normalized_values


def repository_architecture(value, source_type: str) -> str:
    """返回指定补丁源协议使用的架构名。"""
    canonical = normalize_architecture(value)
    mapping = _REPOSITORY_ARCHITECTURES.get(source_type)
    if not mapping:
        raise UnsupportedArchitecture(f"补丁源类型不支持架构映射: {source_type}")
    return mapping[canonical]


def repository_package_applies(
    package_architecture,
    *,
    source_type: str,
    target_architecture,
) -> bool:
    """判断仓库包架构是否属于补丁源的目标范围。

    仓库的 ``all`` / ``noarch`` 包随当前源入库；其他架构必须与
    Adapter 协议名精确匹配，避免把 i686 等不支持架构误标为 x86_64。
    """
    raw = str(package_architecture or "").strip().lower()
    if raw in _INDEPENDENT_ARCHITECTURES:
        return True
    if not raw:
        return False
    expected = repository_architecture(target_architecture, source_type).lower()
    return raw == expected


def supported_architectures(os_type: str) -> tuple[str, ...]:
    """返回 BK-Lite 对指定操作系统承诺支持的架构。"""
    return _SUPPORTED_BY_OS.get(os_type, ())


def validate_os_architecture(os_type: str, value, *, allow_blank: bool = True) -> str:
    """归一化并校验操作系统与架构组合。"""
    if not str(value or "").strip() and allow_blank:
        return ""
    normalized = normalize_architecture(value)
    if normalized not in supported_architectures(os_type):
        raise UnsupportedArchitecture(f"{os_type} 不支持 CPU 架构: {value}")
    return normalized
