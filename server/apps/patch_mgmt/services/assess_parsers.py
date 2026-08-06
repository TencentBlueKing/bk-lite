"""评估结果解析器

把 assess 任务在目标主机上收集到的原始输出，解析成基线要求级别的满足状态。

支持的输入：
- Linux 主机/包结构化事实，兼容旧 apt、yum、dnf 输出；
- Windows 主机事实、WUA 当前已安装/待安装更新，以及 `Get-HotFix` 兼容补充。

解析后统一交由合规评估器生成 `satisfied`、`missing`、`not_applicable`、
`unknown` 四态结果；只有明确适用且低于最低版本或未安装时才进入待治理。
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable

from apps.core.logger import logger
from apps.patch_mgmt.constants import OSType, RequirementAssessmentStatus
from apps.patch_mgmt.services.compliance_evaluator import (
    HostAssessmentFacts,
    LinuxHostFacts,
    LinuxPackageFact,
    RequirementAssessment,
    RequirementSpec,
    WindowsHostFacts,
    WindowsUpdateFacts,
    evaluate_requirements,
)


# WUA MsrcSeverity -> PatchSeverity 映射
_WUA_SEVERITY_MAP = {
    "Critical": "critical",
    "Important": "important",
    "Moderate": "moderate",
    "Low": "low",
}


def _backfill_patch_severity(patch, severity_text: str) -> None:
    """WUA 评估返回的 MsrcSeverity 回填到 Patch 记录。"""
    if not severity_text:
        return
    mapped = _WUA_SEVERITY_MAP.get(severity_text.strip())
    if not mapped:
        return
    if patch.severity == mapped or patch.severity not in ("", "unspecified"):
        return
    patch.severity = mapped
    patch.save(update_fields=["severity", "updated_at"])
    logger.info("WUA 回填 severity: patch_id=%s -> %s", patch.id, mapped)


def _strip_arch(name: str) -> str:
    """去掉包名末尾的架构后缀，如 `gzip.x86_64` -> `gzip`。"""
    if "." in name:
        return name.rsplit(".", 1)[0]
    return name


def parse_apt_upgradable(stdout: str) -> set[str]:
    """解析 apt-get -s upgrade 输出，返回可升级包名集合。"""
    packages: set[str] = set()
    lines = stdout.splitlines()
    in_list = False

    marker = "The following packages will be upgraded:"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(marker):
            in_list = True
            continue

        if in_list:
            # apt 的包列表可能跨多行，直到遇到空行或以数字开头的汇总行
            if not stripped or re.match(r"^\d+\s+upgraded", stripped):
                in_list = False
                continue
            # 去掉行首的 "Inst "（某些格式会带）
            if stripped.startswith("Inst "):
                stripped = stripped[5:].strip()
            # 包名是空格分隔的第一个 token
            pkg = stripped.split()[0]
            if pkg:
                packages.add(pkg)

        # 独立成行的 Inst 行也包含包名：
        # Inst gzip [1.10-10ubuntu4] (...)
        if stripped.startswith("Inst "):
            parts = stripped.split()
            if len(parts) >= 2:
                packages.add(parts[1])

    return packages


def _looks_like_version(token: str) -> bool:
    """粗略判断 token 是否像版本号（包含数字和 . 或 -）。"""
    return bool(re.search(r"\d", token)) and ("." in token or "-" in token)


def parse_yum_dnf_upgradable(stdout: str) -> set[str]:
    """解析 yum/dnf check-update 输出，返回可升级包名集合。"""
    packages: set[str] = set()
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("=") or line.startswith("Last metadata"):
            continue

        parts = line.split()
        if len(parts) < 3:
            continue

        name_with_arch = parts[0]
        version_token = parts[1]
        # 第一列必须是 name.arch，版本列必须像版本号
        if "." not in name_with_arch or not _looks_like_version(version_token):
            continue

        packages.add(_strip_arch(name_with_arch))

    return packages


def parse_windows_hotfixes(stdout: str) -> set[str]:
    """解析 Get-HotFix HotFixID 输出，返回大写 KB 号集合。

    保留用于向后兼容，新评估走 WUA Search 输出。
    """
    kbs: set[str] = set()
    for line in stdout.splitlines():
        for match in re.findall(r"KB\d+", line, flags=re.IGNORECASE):
            kbs.add(match.upper())
    return kbs


def parse_wua_search(stdout: str) -> dict[str, dict]:
    """解析 WUA Search 输出，返回 {KB号: {severity, title}} 字典。

    WUA 输出格式（每行）: KB号|Severity|Title
    例如: KB5040430|Important|2024-07 Cumulative Update for Windows Server 2019
    """
    results: dict[str, dict] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or '|' not in line:
            continue
        parts = line.split('|', 2)
        if len(parts) < 3:
            continue
        kb = parts[0].strip().upper()
        if not kb:
            continue
        # 确保 KB 号格式正确
        if not re.match(r'^KB\d+$', kb, re.IGNORECASE):
            # 尝试从中提取 KB 号
            match = re.search(r'KB\d+', kb, re.IGNORECASE)
            if match:
                kb = match.group(0).upper()
            else:
                continue
        results[kb] = {
            'severity': parts[1].strip(),
            'title': parts[2].strip(),
        }
    return results


def _detect_linux_parser(stdout: str):
    """根据输出特征选择 Linux 解析器。"""
    if "The following packages will be upgraded" in stdout or "Inst " in stdout:
        return parse_apt_upgradable
    return parse_yum_dnf_upgradable


def _linux_specs(requirements: list) -> list[RequirementSpec]:
    specs = []
    for requirement in requirements:
        try:
            detail = requirement.patch.linux_detail
            package_name = (getattr(detail, "pkg_name", "") or "").strip()
            required_version = (getattr(detail, "pkg_version", "") or "").strip()
            distro_name = (getattr(detail, "distro_name", "") or "").strip()
            os_version_range = (getattr(detail, "os_version_range", "") or "").strip()
            architectures = tuple(getattr(detail, "architectures", None) or ())
            package_manager = (getattr(detail, "repo_type", "") or "").strip()
            configuration_error = "" if package_name else "missing package name"
        except Exception:  # noqa: BLE001
            package_name = ""
            required_version = ""
            distro_name = ""
            os_version_range = ""
            architectures = ()
            package_manager = ""
            configuration_error = "missing linux_detail"
        specs.append(
            RequirementSpec(
                requirement.id,
                OSType.LINUX,
                package_name,
                required_version=required_version,
                distro_name=distro_name,
                os_version_range=os_version_range,
                architectures=architectures,
                package_manager=package_manager,
                configuration_error=configuration_error,
            )
        )
    return specs


def _parse_linux_facts(stdout: str) -> HostAssessmentFacts:
    packages: dict[str, LinuxPackageFact] = {}
    linux_host = LinuxHostFacts()
    parsed_lines = 0
    for raw_line in stdout.splitlines():
        if raw_line.startswith("BKPATCH_HOST|LINUX|"):
            parts = raw_line.split("|", 6)
            if len(parts) == 7:
                _, _, distro_id, distro_like, version_id, architecture, package_manager = parts
                linux_host = LinuxHostFacts(
                    distro_id=distro_id.strip(),
                    distro_like=tuple(distro_like.strip().split()),
                    version_id=version_id.strip(),
                    architecture=architecture.strip(),
                    package_manager=package_manager.strip(),
                )
            continue
        if not raw_line.startswith("BKPATCH_LINUX|"):
            continue
        parts = raw_line.split("|", 6)
        if len(parts) != 7:
            continue
        _, _requirement_id, package_name, state, installed_version, comparison, error = parts
        package_name = package_name.strip()
        if not package_name:
            continue
        parsed_lines += 1
        parsed_comparison = None
        if comparison.strip() in {"-1", "0", "1"}:
            parsed_comparison = int(comparison.strip())
        installed = {"installed": True, "absent": False}.get(state.strip())
        packages[package_name] = LinuxPackageFact(
            installed=installed,
            installed_version=installed_version.strip(),
            comparison=parsed_comparison,
            error=error.strip(),
        )
    if parsed_lines == 0:
        return HostAssessmentFacts(collection_error="评估输出缺少结构化 Linux 包事实")
    return HostAssessmentFacts(linux_packages=packages, linux_host=linux_host)


def assess_linux_requirements(stdout: str, requirements: Iterable) -> dict[int, RequirementAssessment]:
    """使用目标机原生版本比较结果评估 Linux 基线要求。"""
    requirements = list(requirements)
    return evaluate_requirements(_linux_specs(requirements), _parse_linux_facts(stdout))


def _replacement_kbs(requirement) -> tuple[str, ...]:
    replacement_ids = list(getattr(requirement.patch, "replacement_ids", None) or [])
    if not replacement_ids:
        return ()
    from apps.patch_mgmt.models import WindowsPatchDetail

    return tuple(
        WindowsPatchDetail.objects.filter(patch_id__in=replacement_ids)
        .exclude(kb_number="")
        .values_list("kb_number", flat=True)
    )


def assess_windows_requirements(stdout: str, requirements: Iterable) -> dict[int, RequirementAssessment]:
    """对 Windows 基线要求做评估。

    解析 combined WUA Search + Get-HotFix 输出：
    - ===WUA=== 段：WUA Search IsInstalled=0 返回的未安装更新（KB号|Severity|Title）
    - ===WUA_INSTALLED=== 段：WUA Search IsInstalled=1 返回的当前已安装更新
    - ===HOTFIX=== 段：Get-HotFix 返回的已安装 KB 号列表

    判断逻辑：
    - KB 在已安装列表 -> 满足
    - KB 在未安装列表 -> 未满足（缺失，可安装）
    - KB 两个列表都没有 -> 未知（不能据此证明不适用或已被替代）
    """
    # 分段解析。Defender 安全情报等 WUA 更新不会出现在
    # Get-HotFix 中，必须使用 IsInstalled=1 才能证明其当前安装状态。
    if '===WUA_INSTALLED===' in stdout:
        wua_part, _, installed_and_hotfix = stdout.partition('===WUA_INSTALLED===')
        installed_part, hotfix_marker, hotfix_part = installed_and_hotfix.partition('===HOTFIX===')
        wua_results = parse_wua_search(wua_part)
        installed_kbs = parse_windows_hotfixes(installed_part)
        if hotfix_marker:
            installed_kbs.update(parse_windows_hotfixes(hotfix_part))
    elif '===HOTFIX===' in stdout:
        wua_part, _, hotfix_part = stdout.partition('===HOTFIX===')
        wua_results = parse_wua_search(wua_part)
        installed_kbs = parse_windows_hotfixes(hotfix_part)
    elif '|' in stdout:
        # 纯 WUA 格式（向后兼容）
        wua_results = parse_wua_search(stdout)
        installed_kbs = set()
    else:
        # 纯 Get-HotFix 格式（向后兼容）
        wua_results = {}
        installed_kbs = parse_windows_hotfixes(stdout)

    missing_kbs = set(wua_results.keys())
    windows_host = WindowsHostFacts()
    for raw_line in stdout.splitlines():
        if not raw_line.startswith("BKPATCH_HOST|WINDOWS|"):
            continue
        parts = raw_line.split("|", 5)
        if len(parts) == 6:
            _, _, product_name, version, build_number, architecture = parts
            windows_host = WindowsHostFacts(
                product_name=product_name.strip(),
                version=version.strip(),
                build_number=build_number.strip(),
                architecture=architecture.strip(),
            )
        break
    requirements = list(requirements)
    specs = []
    for req in requirements:
        try:
            detail = req.patch.windows_detail
            kb_number = (detail.kb_number or "").upper()
            products = tuple(detail.product_list or ())
            architectures = tuple(detail.architectures or ())
            configuration_error = "" if kb_number else "missing KB number"
        except Exception:  # noqa: BLE001
            logger.warning("要求 %s 缺少 Windows 补丁详情，无法评估", req.id)
            kb_number = ""
            products = ()
            architectures = ()
            configuration_error = "missing windows_detail"
        specs.append(
            RequirementSpec(
                req.id,
                OSType.WINDOWS,
                kb_number,
                replacement_identifiers=_replacement_kbs(req),
                products=products,
                architectures=architectures,
                configuration_error=configuration_error,
            )
        )

    facts = HostAssessmentFacts(
        windows=WindowsUpdateFacts(
            installed_kbs=frozenset(installed_kbs),
            applicable_missing_kbs=frozenset(missing_kbs),
        ),
        windows_host=windows_host,
        collection_error="" if stdout.strip() else "Windows 更新评估输出为空",
    )
    result = evaluate_requirements(specs, facts)
    for req in requirements:
        assessment = result.get(req.id)
        if assessment and assessment.status == RequirementAssessmentStatus.MISSING:
            kb_number = assessment.evidence.get("required_kb", "")
            wua_info = wua_results.get(kb_number, {})
            severity = wua_info.get('severity', '')
            if severity:
                result[req.id] = replace(
                    assessment,
                    evidence={**assessment.evidence, "severity": severity},
                )
                _backfill_patch_severity(req.patch, severity)
    return result


def assess_requirements(os_type: str, stdout: str, requirements: Iterable) -> dict[int, RequirementAssessment]:
    """入口：根据 OS 类型分发到对应解析器。"""
    if os_type == "windows":
        return assess_windows_requirements(stdout, requirements)
    return assess_linux_requirements(stdout, requirements)
