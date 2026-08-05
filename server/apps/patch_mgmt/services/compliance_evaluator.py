"""基于结构化主机事实的公开补丁合规评估服务。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from apps.patch_mgmt.constants import OSType, RequirementAssessmentStatus


@dataclass(frozen=True)
class RequirementSpec:
    """与持久化模型解耦的单条基线要求。"""

    requirement_id: int
    os_type: str
    identifier: str
    required_version: str = ""
    replacement_identifiers: tuple[str, ...] = ()
    configuration_error: str = ""


@dataclass(frozen=True)
class LinuxPackageFact:
    """目标机使用原生包管理器采集并比较后的包事实。"""

    installed: bool | None
    installed_version: str = ""
    comparison: int | None = None
    error: str = ""


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
    windows: WindowsUpdateFacts = field(default_factory=WindowsUpdateFacts)
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


def _evaluate_linux(
    requirement: RequirementSpec,
    facts: HostAssessmentFacts,
) -> RequirementAssessment:
    package_name = requirement.identifier.strip()
    fact = facts.linux_packages.get(package_name)
    if fact is None:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.UNKNOWN,
            f"未采集到 {package_name} 的包事实",
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
            fact.error or f"无法判断 {package_name} 是否已安装",
            **evidence,
        )
    if fact.installed is False:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.MISSING,
            f"未安装 {package_name}",
            **evidence,
        )
    if fact.comparison is None:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.UNKNOWN,
            f"无法比较 {package_name} 的已安装版本和最低版本",
            **evidence,
        )
    if fact.comparison >= 0:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.SATISFIED,
            f"{package_name} 已安装版本不低于最低版本",
            **evidence,
        )
    return _result(
        requirement.requirement_id,
        RequirementAssessmentStatus.MISSING,
        f"{package_name} 已安装版本低于最低版本",
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
    #（例如 Defender 平台更新）。只要当前仍明确提供目标 KB，就不能
    # 因为历史修订已安装而判为合规。
    if required_kb in missing:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.MISSING,
            f"{required_kb} 适用但未安装",
            **evidence,
        )
    installed_matches = sorted(candidates & installed)
    if installed_matches:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.SATISFIED,
            f"已安装 {installed_matches[0]}",
            satisfied_by=installed_matches[0],
            **evidence,
        )
    if required_kb in not_applicable:
        return _result(
            requirement.requirement_id,
            RequirementAssessmentStatus.NOT_APPLICABLE,
            f"{required_kb} 不适用于当前主机",
            **evidence,
        )
    return _result(
        requirement.requirement_id,
        RequirementAssessmentStatus.UNKNOWN,
        f"无法确认 {required_kb} 的安装、适用或替代状态",
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
                "missing linux_detail": "缺少 Linux 补丁详情",
                "missing package name": "补丁未配置包名",
                "missing windows_detail": "缺少 Windows 补丁详情",
                "missing KB number": "补丁未配置 KB 号",
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
                f"不支持的操作系统类型: {requirement.os_type}",
            )
        result[requirement.requirement_id] = assessment
    return result
