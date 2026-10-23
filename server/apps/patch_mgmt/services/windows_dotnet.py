"""手工 Windows 补丁包的 .NET Framework 版本标记与 Release 对照。"""

from __future__ import annotations

import re

from apps.patch_mgmt.constants import RequirementAssessmentStatus
from apps.patch_mgmt.utils.i18n import patch_message

DOTNET_481 = "4.8.1"
DOTNET_48 = "4.8"
DOTNET_472 = "4.7.2"
DOTNET_VERSIONS = (DOTNET_481, DOTNET_472, DOTNET_48)

_TOKEN_RE = re.compile(r"(?i)(?<![a-z0-9])ndp(481|472|48)(?![0-9])")
_DECLARED_RE = re.compile(r"^4\.(?:8\.1|8|7\.2)$")
_RELEASE_LINE_RE = re.compile(r"^BKPATCH_DOTNET\|(\d*)$")

# Microsoft Learn: how to determine which .NET Framework versions are installed.
_RELEASE_481 = 533320
_RELEASE_48 = 528040
_RELEASE_472 = 461808


def dotnet_version_from_text(value: str) -> str:
    """从文件名或包内名称读取 ndp481、ndp472、ndp48。长标记优先。"""
    match = _TOKEN_RE.search(str(value or ""))
    if match is None:
        return ""
    return {
        "481": DOTNET_481,
        "472": DOTNET_472,
        "48": DOTNET_48,
    }[match.group(1)]


def normalize_declared_dotnet_version(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _DECLARED_RE.fullmatch(text) is None:
        raise ValueError(text)
    return text


def classify_dotnet_release(release: int | None) -> str:
    """把 Full\\Release 归到 4.8.1、4.8 或 4.7.2。更低的 Release 返回空字符串。"""
    if release is None:
        return ""
    if release >= _RELEASE_481:
        return DOTNET_481
    if release >= _RELEASE_48:
        return DOTNET_48
    if release >= _RELEASE_472:
        return DOTNET_472
    return ""


def resolve_dotnet_version(
    *,
    file_name: str,
    entry_names: tuple[str, ...],
    declared: str,
) -> str:
    """文件名、已签名包内名称和上传时标明的版本必须一致，否则拒绝。"""
    from_file = dotnet_version_from_text(file_name)
    from_entries = ""
    for name in entry_names:
        found = dotnet_version_from_text(name)
        if not found:
            continue
        if from_entries and from_entries != found:
            raise ValueError("multiple")
        from_entries = found
    if from_file and from_entries and from_file != from_entries:
        raise ValueError("conflict")
    detected = from_file or from_entries
    try:
        declared_version = normalize_declared_dotnet_version(declared)
    except ValueError as exc:
        raise ValueError("declared") from exc
    if declared_version and detected and declared_version != detected:
        raise ValueError("declared-conflict")
    return detected or declared_version


def parse_windows_dotnet_release(stdout: str) -> int | None:
    release: int | None = None
    seen = False
    for raw_line in str(stdout or "").splitlines():
        match = _RELEASE_LINE_RE.match(raw_line.strip())
        if match is None:
            continue
        seen = True
        number = match.group(1)
        release = int(number) if number else None
    if not seen:
        return None
    return release


def windows_dotnet_release_command() -> str:
    return (
        "$ProgressPreference='SilentlyContinue';"
        "$rel=(Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\NET Framework Setup\\NDP\\v4\\Full' "
        "-Name Release -ErrorAction SilentlyContinue).Release;"
        "if($null -eq $rel){'BKPATCH_DOTNET|'}else{'BKPATCH_DOTNET|{0}' -f [int64]$rel}"
    )


def windows_dotnet_decision(
    package_version: str,
    release: int | None,
    kb: str,
) -> tuple[str, str]:
    """返回 (状态, 原因)。状态为空表示这个包没有 .NET 版本限制，或版本一致。"""
    if not package_version:
        return "", ""
    if release is None:
        return (
            RequirementAssessmentStatus.UNKNOWN,
            patch_message(
                None,
                "assessment.dotnet_release_unknown",
                "The .NET Framework Release was not collected, so applicability of {kb} cannot be decided",
                kb=kb,
            ),
        )
    host_version = classify_dotnet_release(release)
    if host_version == package_version:
        return "", ""
    if host_version:
        return (
            RequirementAssessmentStatus.NOT_APPLICABLE,
            patch_message(
                None,
                "assessment.dotnet_not_applicable",
                "Package is .NET Framework {package}, but the host Release {release} is {host}",
                package=package_version,
                release=release,
                host=host_version,
            ),
        )
    return (
        RequirementAssessmentStatus.NOT_APPLICABLE,
        patch_message(
            None,
            "assessment.dotnet_not_applicable_other",
            "Package is .NET Framework {package}, but the host Release {release} is not 4.7.2, 4.8, or 4.8.1",
            package=package_version,
            release=release,
        ),
    )
