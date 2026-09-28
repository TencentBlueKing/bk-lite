"""基于结构化主机事实的公开补丁合规评估服务。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from apps.patch_mgmt.constants import OSType, RequirementAssessmentStatus
from apps.patch_mgmt.services.linux_platform import LinuxHostFacts, package_manager_family, validate_linux_host_facts
from apps.patch_mgmt.utils.i18n import patch_message


def _pm(key: str, default: str, **values) -> str:
    return patch_message(None, key, default, **values)


@dataclass(frozen=True)
class RequirementSpec:
    """与持久化模型解耦的单条基线要求。"""

    requirement_id: int
    os_type: str
    identifier: str
    required_version: str = ""
    replacement_identifiers: tuple[str, ...] = ()
    distro_name: str = ""
    os_version_range: str = ""
    architectures: tuple[str, ...] = ()
    package_manager: str = ""
    products: tuple[str, ...] = ()
    configuration_error: str = ""


@dataclass(frozen=True)
class LinuxPackageFact:
    """目标机使用原生包管理器采集并比较后的包事实。"""

    installed: bool | None
    installed_version: str = ""
    comparison: int | None = None
    error: str = ""


@dataclass(frozen=True)
class WindowsHostFacts:
    """Windows 目标机的适用性事实。"""

    product_name: str = ""
    version: str = ""
    build_number: str = ""
    architecture: str = ""


@dataclass(frozen=True)
class WindowsUpdateFacts:
    """目标机 WUA 采集到的 Windows 更新事实。"""

    installed_kbs: frozenset[str] = frozenset()
    applicable_missing_kbs: frozenset[str] = frozenset()
    not_applicable_kbs: frozenset[str] = frozenset()
    error: str = ""


@dataclass(frozen=True)
class HostAssessmentFacts:
    """一次主机采集的结构化事实集合。"""

    linux_packages: Mapping[str, LinuxPackageFact] = field(default_factory=dict)
    linux_host: LinuxHostFacts = field(default_factory=LinuxHostFacts)
    windows: WindowsUpdateFacts = field(default_factory=WindowsUpdateFacts)
    windows_host: WindowsHostFacts = field(default_factory=WindowsHostFacts)
    collection_error: str = ""


@dataclass(frozen=True)
class RequirementAssessment:
    """单条要求的四态评估结果。"""

    requirement_id: int
    status: str
    evidence: Mapping[str, object] = field(default_factory=dict)
    reason: str = ""

    @property
    def satisfied(self) -> bool:
        """兼容旧调用方；只有明确满足才返回 True。"""
        return self.status == RequirementAssessmentStatus.SATISFIED


def _result(
    requirement_id: int,
    status: str,
    reason: str,
    **evidence: object,
) -> RequirementAssessment:
    return RequirementAssessment(
        requirement_id=requirement_id,
        status=status,
        evidence=evidence,
        reason=reason,
    )


def _normalized_architecture(value: str) -> str:
    raw = str(value or "").strip().lower().replace(" ", "")
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "x86-64": "x86_64",
        "x86_64": "x86_64",
        "64-bit": "x86_64",
        "64bit": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    return aliases.get(raw, raw)


def _normalized_distro(value: str) -> str:
    raw = re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()
    aliases = (
        ("oracle linux", "ol"),
        ("red hat enterprise linux", "rhel"),
        ("rocky linux", "rocky"),
        ("alma linux", "almalinux"),
        ("almalinux", "almalinux"),
        ("centos", "centos"),
        ("ubuntu", "ubuntu"),
        ("debian", "debian"),
        ("rhel", "rhel"),
        ("rocky", "rocky"),
        ("ol", "ol"),
    )
    for prefix, canonical in aliases:
        if raw == prefix or raw.startswith(f"{prefix} "):
            return canonical
    return raw.replace(" ", "")


def _version_matches(actual: str, expected: str) -> bool | None:
    actual = str(actual or "").strip()
    expected = str(expected or "").strip()
    if not actual or not expected:
        return None
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version

        if expected.startswith((">", "<", "=", "!", "~")):
            return Version(actual) in SpecifierSet(expected)
        range_match = re.fullmatch(r"\s*([0-9][0-9.]*)\s*-\s*([0-9][0-9.]*)\s*", expected)
        if range_match:
            return Version(range_match.group(1)) <= Version(actual) <= Version(range_match.group(2))
    except (ImportError, ValueError):
        return None
    return actual == expected or actual.startswith(f"{expected}.")


def _linux_not_applicable_reason(requirement: RequirementSpec, host: LinuxHostFacts) -> str:
    expected_arches = {_normalized_architecture(value) for value in requirement.architectures if str(value or "").strip()}
    host_arch = _normalized_architecture(host.architecture)
    universal_arches = {"all", "any", "noarch"}
    if expected_arches.isdisjoint(universal_arches) and host_arch not in expected_arches:
        return _pm(
            "assessment.arch_not_applicable",
            "Patch architecture is not applicable to this host (required {expected}, host {actual})",
            expected=", ".join(sorted(expected_arches)),
            actual=host_arch,
        )

    expected_distro = _normalized_distro(requirement.distro_name)
    host_distro = _normalized_distro(host.distro_id)
    if expected_distro and host_distro and expected_distro != host_distro:
        return _pm(
            "assessment.distro_not_applicable",
            "Patch distro {expected} is not applicable to host {actual}",
            expected=requirement.distro_name,
            actual=host.distro_id,
        )

    version_matches = _version_matches(host.version_id, requirement.os_version_range)
    if version_matches is False:
        return _pm(
            "assessment.version_not_applicable",
            "Patch OS version {expected} is not applicable to host {actual}",
            expected=requirement.os_version_range,
            actual=host.version_id,
        )

    expected_manager = str(requirement.package_manager or "").strip().lower()
    host_manager = str(host.package_manager or "").strip().lower()
    if package_manager_family(expected_manager) != package_manager_family(host_manager):
        return _pm(
            "assessment.package_manager_not_applicable",
            "Patch package manager {expected} is not applicable to host {actual}",
            expected=expected_manager,
            actual=host_manager,
        )
    return ""


def _linux_requirement_metadata_error(requirement: RequirementSpec) -> str:
    missing = []
    if not requirement.identifier.strip():
        missing.append(_pm("assessment.field_package_name", "package name"))
    if not requirement.required_version.strip():
        missing.append(_pm("assessment.field_package_version", "package version"))
    if not requirement.distro_name.strip():
        missing.append(_pm("assessment.field_distro", "distro"))
    if not requirement.os_version_range.strip():
        missing.append(_pm("assessment.field_os_version_range", "OS version range"))
    if not tuple(value for value in requirement.architectures if str(value or "").strip()):
        missing.append(_pm("assessment.field_architecture", "architecture"))
    if not package_manager_family(requirement.package_manager):
        missing.append(_pm("assessment.field_package_manager", "package manager"))
    if missing:
        return _pm("assessment.metadata_missing", "Patch metadata is missing: {fields}", fields=", ".join(missing))
    if _version_matches("0", requirement.os_version_range) is None:
        return _pm(
            "assessment.version_range_unparseable",
            "Patch OS version range cannot be parsed: {range}",
            range=requirement.os_version_range,
        )
    return ""


def evaluate_linux_applicability(
    requirement: RequirementSpec,
    host: LinuxHostFacts,
) -> tuple[str, str]:
    """只判断 Linux 要求是否适用，不读取安装状态。"""
    host_error = validate_linux_host_facts(host)
    if host_error:
        return RequirementAssessmentStatus.UNKNOWN, host_error
    metadata_error = _linux_requirement_metadata_error(requirement)
    if metadata_error:
        return RequirementAssessmentStatus.UNKNOWN, metadata_error
    reason = _linux_not_applicable_reason(requirement, host)
    if reason:
        return RequirementAssessmentStatus.NOT_APPLICABLE, reason
    return RequirementAssessmentStatus.SATISFIED, _pm("assessment.applicable_to_host", "Patch applies to this host")


def _windows_not_applicable_reason(requirement: RequirementSpec, host: WindowsHostFacts) -> str:
    expected_arches = {_normalized_architecture(value) for value in requirement.architectures if str(value or "").strip()}
    host_arch = _normalized_architecture(host.architecture)
    if expected_arches and host_arch and host_arch not in expected_arches:
        return _pm(
            "assessment.arch_not_applicable",
            "Patch architecture is not applicable to this host (required {expected}, host {actual})",
            expected=", ".join(sorted(expected_arches)),
            actual=host_arch,
        )

    product_name = re.sub(r"\s+", " ", str(host.product_name or "").strip().lower())
    products = [re.sub(r"\s+", " ", str(value or "").strip().lower()) for value in requirement.products]
    products = [value for value in products if value]
    if products and product_name and not any(value in product_name for value in products):
        return _pm(
            "assessment.product_not_applicable",
            "Patch product scope is not applicable to host {product}",
            product=host.product_name,
        )
    return ""


def _evaluate_linux(
    requirement: RequirementSpec,
    facts: HostAssessmentFacts,
) -> RequirementAssessment:
    package_name = requirement.identifier.strip()
    # 兼容升级前已下发但尚未完成的旧评估输出；新评估均会携带主机事实，
    # 因而会进入严格的主机事实与补丁元数据校验。
    legacy_without_host_facts = not any(
        (
            facts.linux_host.distro_id,
            facts.linux_host.version_id,
            facts.linux_host.architecture,
            facts.linux_host.package_manager,
        )
    )
    if not legacy_without_host_facts:
        applicability, applicability_reason = evaluate_linux_applicability(requirement, facts.linux_host)
    else:
        applicability, applicability_reason = RequirementAssessmentStatus.SATISFIED, ""
    if applicability == RequirementAssessmentStatus.UNKNOWN:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.UNKNOWN,
            applicability_reason,
            pkg_name=package_name,
            required_version=requirement.required_version,
        )
    if applicability == RequirementAssessmentStatus.NOT_APPLICABLE:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.NOT_APPLICABLE,
            applicability_reason,
            pkg_name=package_name,
            required_version=requirement.required_version,
            host_distro=facts.linux_host.distro_id,
            host_version=facts.linux_host.version_id,
            host_architecture=facts.linux_host.architecture,
            host_package_manager=facts.linux_host.package_manager,
        )
    fact = facts.linux_packages.get(package_name)
    if fact is None:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.UNKNOWN,
            _pm("assessment.package_fact_missing", "No package facts collected for {package}", package=package_name),
            pkg_name=package_name,
            required_version=requirement.required_version,
        )
    evidence = {
        "pkg_name": package_name,
        "required_version": requirement.required_version,
        "installed": fact.installed,
        "installed_version": fact.installed_version,
        "comparison": fact.comparison,
    }
    if fact.error or fact.installed is None:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.UNKNOWN,
            fact.error
            or _pm(
                "assessment.package_install_unknown",
                "Unable to determine whether {package} is installed",
                package=package_name,
            ),
            **evidence,
        )
    if fact.installed is False:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.MISSING,
            _pm("assessment.package_not_installed", "{package} is not installed", package=package_name),
            **evidence,
        )
    if fact.comparison is None:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.UNKNOWN,
            _pm(
                "assessment.package_version_compare_failed",
                "Unable to compare the installed and minimum versions of {package}",
                package=package_name,
            ),
            **evidence,
        )
    if fact.comparison >= 0:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.SATISFIED,
            _pm(
                "assessment.package_version_ok",
                "Installed version of {package} meets the minimum version",
                package=package_name,
            ),
            **evidence,
        )
    return _result(
        requirement.requirement_id,
        RequirementAssessmentStatus.MISSING,
        _pm(
            "assessment.package_version_below",
            "Installed version of {package} is below the minimum version",
            package=package_name,
        ),
        **evidence,
    )


def _normalize_kbs(values: Iterable[str]) -> frozenset[str]:
    return frozenset(str(value).strip().upper() for value in values if str(value).strip())


def _evaluate_windows(
    requirement: RequirementSpec,
    facts: HostAssessmentFacts,
) -> RequirementAssessment:
    windows = facts.windows
    required_kb = requirement.identifier.strip().upper()
    replacements = _normalize_kbs(requirement.replacement_identifiers)
    installed = _normalize_kbs(windows.installed_kbs)
    missing = _normalize_kbs(windows.applicable_missing_kbs)
    not_applicable = _normalize_kbs(windows.not_applicable_kbs)
    candidates = frozenset({required_kb}) | replacements
    evidence = {
        "required_kb": required_kb,
        "replacement_kbs": sorted(replacements),
        "installed_kbs": sorted(installed),
        "applicable_missing_kbs": sorted(missing),
        "not_applicable_kbs": sorted(not_applicable),
    }
    if windows.error:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.UNKNOWN,
            windows.error,
            **evidence,
        )
    # WUA 可能同时返回同一 KB 的已安装旧修订和待安装新修订
    # （例如 Defender 平台更新）。只要当前仍明确提供目标 KB，就不能
    # 因为历史修订已安装而判为合规。
    if required_kb in missing:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.MISSING,
            _pm("assessment.kb_applicable_not_installed", "{kb} is applicable but not installed", kb=required_kb),
            **evidence,
        )
    installed_matches = sorted(candidates & installed)
    if installed_matches:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.SATISFIED,
            _pm("assessment.kb_installed", "{kb} is installed", kb=installed_matches[0]),
            satisfied_by=installed_matches[0],
            **evidence,
        )
    not_applicable_reason = _windows_not_applicable_reason(requirement, facts.windows_host)
    if not_applicable_reason:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.NOT_APPLICABLE,
            not_applicable_reason,
            host_product=facts.windows_host.product_name,
            host_version=facts.windows_host.version,
            host_build=facts.windows_host.build_number,
            host_architecture=facts.windows_host.architecture,
            **evidence,
        )
    if required_kb in not_applicable:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.NOT_APPLICABLE,
            _pm("assessment.kb_not_applicable", "{kb} is not applicable to this host", kb=required_kb),
            **evidence,
        )
    return _result(
        requirement.requirement_id,
        RequirementAssessmentStatus.UNKNOWN,
        _pm(
            "assessment.kb_status_unknown",
            "Unable to confirm install, applicability, or replacement status for {kb}",
            kb=required_kb,
        ),
        **evidence,
    )


def evaluate_requirements(
    requirements: Iterable[RequirementSpec],
    facts: HostAssessmentFacts,
) -> dict[int, RequirementAssessment]:
    """依据结构化事实评估要求，不访问数据库也不执行远程命令。"""
    requirements = list(requirements)
    result: dict[int, RequirementAssessment] = {}
    for requirement in requirements:
        if requirement.configuration_error:
            reasons = {
                "missing linux_detail": _pm("assessment.missing_linux_detail", "Linux patch details are missing"),
                "missing package name": _pm("assessment.missing_package_name", "The patch has no package name configured"),
                "conflicting linux package families": _pm(
                    "assessment.conflicting_linux_families",
                    "The patch is linked to both APT and RPM families and cannot be assessed safely",
                ),
                "missing windows_detail": _pm("assessment.missing_windows_detail", "Windows patch details are missing"),
                "missing KB number": _pm("assessment.missing_kb_number", "The patch has no KB number configured"),
            }
            assessment = _result(
                requirement.requirement_id,
                RequirementAssessmentStatus.UNKNOWN,
                reasons.get(requirement.configuration_error, requirement.configuration_error),
                error=requirement.configuration_error,
            )
        elif facts.collection_error:
            assessment = _result(
                requirement.requirement_id,
                RequirementAssessmentStatus.UNKNOWN,
                facts.collection_error,
                collection_error=facts.collection_error,
            )
        elif requirement.os_type == OSType.LINUX:
            assessment = _evaluate_linux(requirement, facts)
        elif requirement.os_type == OSType.WINDOWS:
            assessment = _evaluate_windows(requirement, facts)
        else:
            assessment = _result(
                requirement.requirement_id,
                RequirementAssessmentStatus.UNKNOWN,
                _pm(
                    "assessment.unsupported_os_type",
                    "Unsupported operating system type: {os_type}",
                    os_type=requirement.os_type,
                ),
            )
        result[requirement.requirement_id] = assessment
    return result
