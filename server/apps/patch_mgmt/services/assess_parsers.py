"""评估结果解析器

把 assess 任务在目标主机上收集到的原始输出，解析成基线要求级别的满足状态。

支持的输入：
- Linux apt: `apt-get -s upgrade`
- Linux yum/dnf: `yum --security check-update` / `dnf --security check-update`
- Windows: `Get-HotFix | Select-Object -ExpandProperty HotFixID`

MVP 判断逻辑：
- Linux：如果基线要求的包名出现在「可升级包列表」中，则认为不满足；否则认为满足。
  这里假设基线补丁来自同一 repo，未出现即表示当前已安装版本不低于要求版本。
- Windows：如果基线要求的 KB 号出现在已安装 KB 列表中，则认为满足；否则不满足。
  暂时不考虑替代 KB 链（MVP 后续可扩展）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger("app")

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


@dataclass
class RequirementAssessment:
    """单条基线要求的评估结果"""

    requirement_id: int
    satisfied: bool
    evidence: dict = field(default_factory=dict)
    reason: str = ""


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


def assess_linux_requirements(stdout: str, requirements: Iterable) -> dict[int, RequirementAssessment]:
    """对 Linux 基线要求做评估。"""
    parse = _detect_linux_parser(stdout)
    upgradable = parse(stdout)

    result: dict[int, RequirementAssessment] = {}
    for req in requirements:
        req_id = req.id
        try:
            detail = req.patch.linux_detail
            pkg_name = detail.pkg_name
        except Exception:  # noqa: BLE001
            logger.warning("要求 %s 缺少 Linux 补丁详情，无法评估", req_id)
            result[req_id] = RequirementAssessment(
                requirement_id=req_id,
                satisfied=False,
                evidence={"error": "missing linux_detail"},
                reason="补丁缺少 Linux 详情，无法判断",
            )
            continue

        if not pkg_name:
            result[req_id] = RequirementAssessment(
                requirement_id=req_id,
                satisfied=False,
                evidence={},
                reason="补丁未配置包名",
            )
            continue

        missing = pkg_name in upgradable
        result[req_id] = RequirementAssessment(
            requirement_id=req_id,
            satisfied=not missing,
            evidence={
                "pkg_name": pkg_name,
                "upgradable": missing,
                "upgradable_packages": sorted(upgradable),
            },
            reason=f"检测到 {pkg_name} 有待更新" if missing else f"{pkg_name} 已满足版本要求",
        )

    return result


def assess_windows_requirements(stdout: str, requirements: Iterable) -> dict[int, RequirementAssessment]:
    """对 Windows 基线要求做评估。

    解析 combined WUA Search + Get-HotFix 输出：
    - ===WUA=== 段：WUA Search IsInstalled=0 返回的未安装更新（KB号|Severity|Title）
    - ===HOTFIX=== 段：Get-HotFix 返回的已安装 KB 号列表

    判断逻辑：
    - KB 在已安装列表 -> 满足
    - KB 在未安装列表 -> 未满足（缺失，可安装）
    - KB 两个列表都没有 -> 未满足（Windows Update 不存在此 KB）
    """
    # 分段解析
    if '===HOTFIX===' in stdout:
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

    result: dict[int, RequirementAssessment] = {}
    for req in requirements:
        req_id = req.id
        try:
            detail = req.patch.windows_detail
            kb_number = (detail.kb_number or "").upper()
        except Exception:  # noqa: BLE001
            logger.warning("要求 %s 缺少 Windows 补丁详情，无法评估", req_id)
            result[req_id] = RequirementAssessment(
                requirement_id=req_id,
                satisfied=False,
                evidence={"error": "missing windows_detail"},
                reason="补丁缺少 Windows 详情，无法判断",
            )
            continue

        if not kb_number:
            result[req_id] = RequirementAssessment(
                requirement_id=req_id,
                satisfied=False,
                evidence={"installed_kbs": sorted(installed_kbs)},
                reason="补丁未配置 KB 号",
            )
            continue

        if kb_number in installed_kbs:
            # 已安装
            result[req_id] = RequirementAssessment(
                requirement_id=req_id,
                satisfied=True,
                evidence={
                    "required_kb": kb_number,
                    "missing_kbs": sorted(missing_kbs),
                    "installed_kbs": sorted(installed_kbs),
                },
                reason=f"已安装 {kb_number}",
            )
        elif kb_number in missing_kbs:
            # 缺失，可安装
            wua_info = wua_results.get(kb_number, {})
            severity = wua_info.get('severity', '')
            title = wua_info.get('title', '')
            result[req_id] = RequirementAssessment(
                requirement_id=req_id,
                satisfied=False,
                evidence={
                    "required_kb": kb_number,
                    "missing_kbs": sorted(missing_kbs),
                    "installed_kbs": sorted(installed_kbs),
                    "severity": severity,
                },
                reason=f"未安装 {kb_number}",
            )
            if severity:
                _backfill_patch_severity(req.patch, severity)
        else:
            # 两个列表都没有，KB 不存在
            result[req_id] = RequirementAssessment(
                requirement_id=req_id,
                satisfied=False,
                evidence={
                    "required_kb": kb_number,
                    "missing_kbs": sorted(missing_kbs),
                    "installed_kbs": sorted(installed_kbs),
                },
                reason=f"{kb_number} 未在 Windows Update 中找到，可能 KB 号有误",
            )

    return result


def assess_requirements(os_type: str, stdout: str, requirements: Iterable) -> dict[int, RequirementAssessment]:
    """入口：根据 OS 类型分发到对应解析器。"""
    if os_type == "windows":
        return assess_windows_requirements(stdout, requirements)
    return assess_linux_requirements(stdout, requirements)
