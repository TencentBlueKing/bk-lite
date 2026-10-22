"""安装前磁盘预算。

比较「这次会新写入的字节 + 固定余量」和目标机剩余空间。
不读取 WUA 的磁盘接口；WUA 只提供更新体积。
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from apps.patch_mgmt.config import PATCH_MGMT_LINUX_DISK_RESERVE_BYTES, PATCH_MGMT_WINDOWS_DISK_RESERVE_BYTES
from apps.patch_mgmt.utils.i18n import patch_message

WINDOWS_MSI_CONTAINER_MIN_EXPANSION_LIMIT_BYTES = 16 * 1024 * 1024
WINDOWS_MSI_CONTAINER_MAX_EXPANSION_LIMIT_BYTES = 1024 * 1024 * 1024
WINDOWS_MSI_CONTAINER_MAX_EXPANSION_RATIO = 8

_SIZE_RE = re.compile(
    r"(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>KiB|MiB|GiB|TiB|KB|MB|GB|TB|K|M|G|T|B)\b",
    re.IGNORECASE,
)
_SIZE_FACTORS = {
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "kib": 1024,
    "m": 1024**2,
    "mb": 1024**2,
    "mib": 1024**2,
    "g": 1024**3,
    "gb": 1024**3,
    "gib": 1024**3,
    "t": 1024**4,
    "tb": 1024**4,
    "tib": 1024**4,
}


def windows_disk_reserve_bytes() -> int:
    return max(int(PATCH_MGMT_WINDOWS_DISK_RESERVE_BYTES), 0)


def linux_disk_reserve_bytes() -> int:
    return max(int(PATCH_MGMT_LINUX_DISK_RESERVE_BYTES), 0)


def cab_expansion_limit_bytes(package_size: int) -> int:
    size = max(int(package_size or 0), 1)
    return min(
        max(
            size * WINDOWS_MSI_CONTAINER_MAX_EXPANSION_RATIO,
            WINDOWS_MSI_CONTAINER_MIN_EXPANSION_LIMIT_BYTES,
        ),
        WINDOWS_MSI_CONTAINER_MAX_EXPANSION_LIMIT_BYTES,
    )


def manual_stage_requirement_bytes(packages: list[tuple[int, str]]) -> int:
    """送文件前：包大小加上 CAB 展开上限，再加一块 Windows 余量。"""
    total = 0
    for package_size, extension in packages:
        total += max(int(package_size or 0), 0)
        if str(extension or "").lower() == ".cab":
            total += cab_expansion_limit_bytes(package_size)
    return total + windows_disk_reserve_bytes()


def manual_install_requirement_bytes(packages: list[tuple[int, str]]) -> int:
    """文件已经在盘上。MSU 只留余量，CAB 还要留出展开上限。"""
    total = 0
    for package_size, extension in packages:
        if str(extension or "").lower() == ".cab":
            total += cab_expansion_limit_bytes(package_size)
    return total + windows_disk_reserve_bytes()


def wua_download_requirement_bytes(updates: list[tuple[int, int]]) -> int:
    """每个更新取下载大小和建议空间的较大值，再加一块 Windows 余量。"""
    total = 0
    for download_bytes, recommended_megabytes in updates:
        recommended = max(int(recommended_megabytes or 0), 0) * 1024 * 1024
        total += max(max(int(download_bytes or 0), 0), recommended)
    return total + windows_disk_reserve_bytes()


@dataclass(frozen=True)
class MountFreeSpace:
    mount: str
    free_bytes: int


@dataclass(frozen=True)
class LinuxDiskProbe:
    root: MountFreeSpace | None = None
    cache: MountFreeSpace | None = None
    error: str = ""

    @property
    def same_filesystem(self) -> bool:
        return bool(self.root and self.cache and self.root.mount == self.cache.mount)


def format_bytes(value: int) -> str:
    size = max(int(value or 0), 0)
    gib = 1024**3
    if size >= gib:
        return f"{size / gib:.1f} GiB"
    return f"{size / (1024**2):.1f} MiB"


def windows_free_space_command() -> str:
    return (
        "$ProgressPreference='SilentlyContinue';"
        "try{"
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "$disk=Get-CimInstance Win32_LogicalDisk -Filter (\"DeviceID='{0}'\" -f $os.SystemDrive);"
        "if(-not $disk){throw 'missing'};"
        "'BKPATCH_DISK|WINDOWS|{0}' -f [int64]$disk.FreeSpace"
        "}catch{'BKPATCH_DISK|ERROR|probe_failed'}"
    )


def parse_windows_free_bytes(stdout: str) -> int | None:
    for line in str(stdout or "").splitlines():
        if line.startswith("BKPATCH_DISK|ERROR|"):
            return None
        if not line.startswith("BKPATCH_DISK|WINDOWS|"):
            continue
        free = line.split("|", 2)[2].strip()
        if free.isdigit():
            return int(free)
        return None
    return None


def linux_cache_path(package_manager: str) -> str:
    if package_manager == "apt":
        return "/var/cache/apt"
    if package_manager == "yum":
        return "/var/cache/yum"
    return "/var/cache/dnf"


def linux_disk_probe_command(cache_path: str) -> str:
    cache = shlex.quote(cache_path or "/var/cache")
    return (
        "probe() { "
        "label=$1; path=$2; "
        'if [ ! -e "$path" ]; then path=/; fi; '
        "set -- $(df -P -B1 \"$path\" 2>/dev/null | awk 'NR==2 { print $4, $6 }'); "
        'if [ -z "$1" ] || [ -z "$2" ]; then '
        "printf 'BKPATCH_DISK|ERROR|probe_failed\\n'; return; fi; "
        'printf \'BKPATCH_DISK|%s|%s|%s\\n\' "$label" "$2" "$1"; '
        "}; "
        f"probe root /; probe cache {cache}"
    )


def parse_linux_disk_probe(stdout: str) -> LinuxDiskProbe:
    root = None
    cache = None
    for line in str(stdout or "").splitlines():
        if line.startswith("BKPATCH_DISK|ERROR|"):
            return LinuxDiskProbe(error="probe_failed")
        parts = line.split("|")
        if len(parts) != 4 or parts[0] != "BKPATCH_DISK":
            continue
        _, label, mount, free = parts
        if not free.isdigit() or not mount:
            return LinuxDiskProbe(error="probe_failed")
        point = MountFreeSpace(mount=mount, free_bytes=int(free))
        if label == "root":
            root = point
        elif label == "cache":
            cache = point
    if root is None or cache is None:
        return LinuxDiskProbe(error="probe_failed")
    return LinuxDiskProbe(root=root, cache=cache)


def _first_size_bytes(line: str) -> int | None:
    match = _SIZE_RE.search(line.replace(",", ""))
    if match is None:
        return None
    number = match.group("number").replace(",", "")
    unit = match.group("unit").lower()
    factor = _SIZE_FACTORS.get(unit)
    if factor is None:
        return None
    try:
        return int(float(number) * factor)
    except ValueError:
        return None


_APT_URI_RE = re.compile(r"^'[^']+'\s+\S+\s+(\d+)\s+")


def apt_simulation_is_empty(stdout: str) -> bool:
    return re.search(r"0 upgraded,\s*0 newly installed", stdout or "", re.IGNORECASE) is not None


def parse_apt_download_bytes(stdout: str) -> int | None:
    text = str(stdout or "")
    if "Unable to locate package" in text or "\nE:" in f"\n{text}":
        return None
    total = 0
    for line in text.splitlines():
        match = _APT_URI_RE.match(line.strip())
        if match:
            total += int(match.group(1))
    return total


def parse_apt_installed_bytes(stdout: str) -> int | None:
    total = 0
    seen = False
    current_package = ""
    counted: set[str] = set()
    for line in str(stdout or "").splitlines():
        if line.startswith("Package:"):
            current_package = line.split(":", 1)[1].strip()
            continue
        if not line.startswith("Installed-Size:") or not current_package or current_package in counted:
            continue
        size_text = line.split(":", 1)[1].strip()
        if not size_text.isdigit():
            return None
        total += int(size_text) * 1024
        counted.add(current_package)
        seen = True
    if not seen:
        return None
    return total


def parse_install_sizes(stdout: str) -> tuple[int, int] | None:
    """返回 (仍需下载字节, 安装增量字节)。无法同时识别两者时返回 None。"""
    download = None
    growth = None
    for raw_line in str(stdout or "").splitlines():
        line = raw_line.strip().lower()
        if "need to get" in line or "total download size" in line or line.startswith("download size"):
            size = _first_size_bytes(raw_line)
            if size is not None:
                download = size
        if "disk space will be freed" in line:
            growth = 0
        elif "additional disk space will be used" in line or "installed size" in line:
            size = _first_size_bytes(raw_line)
            if size is not None:
                growth = size
    if download is None or growth is None:
        return None
    return download, growth


def linux_disk_shortfall(
    probe: LinuxDiskProbe,
    download_bytes: int,
    growth_bytes: int,
    *,
    reserve_bytes: int | None = None,
) -> tuple[str, str]:
    if probe.error or probe.root is None or probe.cache is None:
        return (
            "disk_probe_failed",
            patch_message(None, "error.disk_linux_unreadable", "Unable to read the target disk free space"),
        )
    reserve = linux_disk_reserve_bytes() if reserve_bytes is None else max(int(reserve_bytes), 0)
    download = max(int(download_bytes or 0), 0)
    growth = max(int(growth_bytes or 0), 0)
    if probe.same_filesystem:
        required = download + growth + reserve
        if probe.root.free_bytes < required:
            return (
                "disk_insufficient",
                patch_message(
                    None,
                    "error.disk_linux_root_short",
                    "Not enough disk space before installation: the root filesystem has {free} free and needs at least {required}",
                    free=format_bytes(probe.root.free_bytes),
                    required=format_bytes(required),
                ),
            )
        return "", ""
    cache_required = download + reserve
    root_required = growth + reserve
    shortages = []
    if probe.cache.free_bytes < cache_required:
        shortages.append(
            patch_message(
                None,
                "error.disk_linux_cache_short",
                "the download cache has {free} free and needs at least {required}",
                free=format_bytes(probe.cache.free_bytes),
                required=format_bytes(cache_required),
            )
        )
    if probe.root.free_bytes < root_required:
        shortages.append(
            patch_message(
                None,
                "error.disk_linux_root_part_short",
                "the root filesystem has {free} free and needs at least {required}",
                free=format_bytes(probe.root.free_bytes),
                required=format_bytes(root_required),
            )
        )
    if not shortages:
        return "", ""
    return (
        "disk_insufficient",
        patch_message(
            None,
            "error.disk_linux_short",
            "Not enough disk space before installation: {detail}",
            detail="; ".join(shortages),
        ),
    )


def windows_disk_shortfall(free_bytes: int | None, required_bytes: int, *, action: str) -> tuple[str, str]:
    if free_bytes is None:
        return (
            "disk_probe_failed",
            patch_message(None, "error.disk_windows_unreadable", "Unable to read the Windows system drive free space"),
        )
    required = max(int(required_bytes or 0), 0)
    if free_bytes >= required:
        return "", ""
    free = format_bytes(free_bytes)
    needed = format_bytes(required)
    if action == "stage":
        return (
            "disk_insufficient",
            patch_message(
                None,
                "error.disk_windows_stage_short",
                "Not enough disk space before installation: the system drive has {free} free while staging the package and needs at least {required}",
                free=free,
                required=needed,
            ),
        )
    return (
        "disk_insufficient",
        patch_message(
            None,
            "error.disk_windows_install_short",
            "Not enough disk space before installation: the system drive has {free} free while installing the package and needs at least {required}",
            free=free,
            required=needed,
        ),
    )
