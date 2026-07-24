"""风险计算服务

从 HostBaselineBinding + BaselineRequirement 动态计算风险项，
支持三视角聚合（主机/补丁/基线）。MVP 阶段无扫描结果，
合规状态统一按缺失评估；治理状态由 GovernanceTask 推断。
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from apps.patch_mgmt.constants import (
    ComplianceStatus,
    GovernanceTaskStatus,
    GovernanceTaskType,
    RemediationStatus,
    RiskCompliance,
)
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    HostComplianceSnapshot,
    Patch,
    PatchTarget,
)

logger = logging.getLogger("app")


@dataclass
class RiskItem:
    """风险项"""

    host_id: int
    host_name: str
    host_ip: str
    patch_id: int
    patch_title: str
    patch_severity: str
    baseline_id: int
    baseline_name: str
    compliance: str
    remediation: str
    in_other_task: bool = False
    condition: str = ""
    os_type: str = ""
    kb_number: str = ""
    pkg_name: str = ""
    pkg_version: str = ""
    version: str = ""
    arch: str = ""
    deps: str = ""
    install_impact: dict = field(default_factory=dict)
    evaluated_at: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "host_id": self.host_id,
            "host_name": self.host_name,
            "host_ip": self.host_ip,
            "patch_id": self.patch_id,
            "patch_title": self.patch_title,
            "patch_severity": self.patch_severity,
            "baseline_id": self.baseline_id,
            "baseline_name": self.baseline_name,
            "compliance": self.compliance,
            "remediation": self.remediation,
            "in_other_task": self.in_other_task,
            "condition": self.condition,
            "os_type": self.os_type,
            "kb_number": self.kb_number,
            "pkg_name": self.pkg_name,
            "pkg_version": self.pkg_version,
            "version": self.version,
            "arch": self.arch,
            "deps": self.deps,
            "install_impact": self.install_impact,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
        }


def _get_patch_detail_fields(patch) -> dict:
    """从 patch 的 detail 中提取展示字段"""
    fields = {
        "patch_title": patch.title,
        "patch_severity": patch.severity,
        "os_type": patch.os_type,
        "kb_number": "",
        "pkg_name": "",
        "pkg_version": "",
        "version": "",
        "arch": "",
    }
    if patch.os_type == "windows":
        try:
            d = patch.windows_detail
            fields["kb_number"] = d.kb_number or ""
            fields["version"] = ", ".join(d.product_list or [])
            fields["arch"] = ", ".join(d.architectures or [])
        except Exception:
            pass
    else:
        try:
            d = patch.linux_detail
            fields["pkg_name"] = d.pkg_name or ""
            fields["pkg_version"] = d.pkg_version or ""
            fields["version"] = d.distro_name or ""
            fields["arch"] = ", ".join(d.architectures or [])
        except Exception:
            pass
    return fields


def _compute_compliance(has_binding: bool) -> str:
    if not has_binding:
        return "unconfigured"
    return RiskCompliance.MISSING


def _is_satisfied_by_task(target_id: int, patch_id: int) -> bool:
    """已通过其他任务/补丁满足：检查最近的 install/verify 任务是否完成。

    MVP 没有扫描结果表，按治理任务推断 SATISFIED：存在一个 target+patch 已 completed 的任务
    即视为已满足（避免永远 100% 不合规）。
    """
    tasks = GovernanceTask.objects.filter(
        task_type__in=("install", "verify"),
        status=GovernanceTaskStatus.COMPLETED,
        target_list__contains=[target_id],
        patch_list__contains=[patch_id],
    ).order_by("-created_at")
    return any(_task_contains_pair(task, target_id, patch_id) for task in tasks)


def _task_contains_pair(task: GovernanceTask, target_id: int, patch_id: int) -> bool:
    """按创建时风险快照判断主机补丁关系。

    target_list/patch_list 只是批量索引，两者笛卡尔积并不代表用户
    选中了每一种主机补丁组合。旧任务没有快照时才回退到列表判断。
    """
    snapshot = task.risk_snapshot or []
    if snapshot:
        return any(
            item.get("host_id") == target_id and item.get("patch_id") == patch_id
            for item in snapshot
        )
    return target_id in (task.target_list or []) and patch_id in (task.patch_list or [])


def _latest_task_for_pair(queryset, target_id: int, patch_id: int):
    return next(
        (task for task in queryset.order_by("-created_at") if _task_contains_pair(task, target_id, patch_id)),
        None,
    )


def _is_reboot_completed(target_id: int) -> bool:
    """检查该主机是否已有完成的 reboot 任务。"""
    return GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.REBOOT,
        status=GovernanceTaskStatus.COMPLETED,
        target_list__contains=[target_id],
    ).exists()


def _compute_remediation(target_id: int, patch_id: int, compliance: str, evaluated_at=None) -> str:
    # 活动状态按安装 > 重启 > 验证优先展示，避免重启过程中仍显示“待重启”。
    install_task = _latest_task_for_pair(GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.INSTALL,
        status__in=(GovernanceTaskStatus.PENDING, GovernanceTaskStatus.RUNNING),
        target_list__contains=[target_id],
        patch_list__contains=[patch_id],
    ), target_id, patch_id)
    if install_task:
        host_stage = GovernanceTaskHost.objects.filter(
            task=install_task, target_id=target_id
        ).values_list('stage', flat=True).first()
        return RemediationStatus.SCHEDULED if host_stage == 'waiting' else 'installing'

    rebooting = GovernanceTaskHost.objects.filter(
        target_id=target_id,
        task__task_type=GovernanceTaskType.REBOOT,
        task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
    ).exists()
    if rebooting:
        return 'rebooting'

    # 安装后无需重启会直接创建验证任务；验证完成前仍属于治理中。
    verifying = _latest_task_for_pair(GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.VERIFY,
        status__in=(GovernanceTaskStatus.PENDING, GovernanceTaskStatus.RUNNING),
        target_list__contains=[target_id],
        patch_list__contains=[patch_id],
    ), target_id, patch_id)
    if verifying:
        return 'verifying'

    # 已完成的安装任务按 host stage 推断下一步
    install_task = _latest_task_for_pair(GovernanceTask.objects.filter(
        task_type=GovernanceTaskType.INSTALL,
        status=GovernanceTaskStatus.COMPLETED,
        target_list__contains=[target_id],
        patch_list__contains=[patch_id],
    ), target_id, patch_id)
    if install_task:
        install_host = GovernanceTaskHost.objects.filter(
            task=install_task, target_id=target_id,
        ).first()
        if install_host:
            if install_host.stage == 'pending_reboot':
                # 只有安装晚于最新评估时才等待重启；后续验证/评估
                # 已经更新快照时，应以较新快照为准。
                if evaluated_at is None or install_task.created_at > evaluated_at:
                    return RemediationStatus.PENDING_REBOOT
                if compliance == RiskCompliance.SATISFIED:
                    return RemediationStatus.FIXED
                return RemediationStatus.FAILED
            elif install_host.stage == 'failed':
                # 安装失败
                return RemediationStatus.FAILED
            elif install_host.stage == 'completed':
                # 安装+验证已完成，快照仍未满足 -> 安装可能未生效
                return (
                    RemediationStatus.FIXED
                    if compliance == RiskCompliance.SATISFIED
                    else RemediationStatus.FAILED
                )
    if compliance == RiskCompliance.SATISFIED:
        return RemediationStatus.FIXED
    return RemediationStatus.UNPLANNED


def compute_risk_items() -> list[RiskItem]:
    """计算所有风险项

    遍历所有主机基线绑定，对每个绑定的主机×要求组合，
    查最新扫描结果和安装结果，计算合规和治理状态。
    """
    bindings = list(HostBaselineBinding.objects.select_related("target", "baseline").all())
    if not bindings:
        return []

    # 预加载基线要求
    baseline_ids = [b.baseline_id for b in bindings]
    requirements = (
        BaselineRequirement.objects.filter(baseline_id__in=baseline_ids)
        .select_related("patch__windows_detail", "patch__linux_detail")
        .all()
    )
    req_by_baseline: dict[int, list[BaselineRequirement]] = defaultdict(list)
    for req in requirements:
        req_by_baseline[req.baseline_id].append(req)

    # 预加载最新合规快照
    binding_ids = [b.id for b in bindings]
    snapshots = {
        (s.binding_id, s.requirement_id): s
        for s in HostComplianceSnapshot.objects.filter(binding_id__in=binding_ids)
    }

    # 预加载依赖/替代补丁标题，用于展示连带升级信息
    related_patch_ids: set[int] = set()
    for req in requirements:
        related_patch_ids.update(req.patch.dependency_ids or [])
        related_patch_ids.update(req.patch.replacement_ids or [])
    related_titles = {
        p["id"]: p["title"]
        for p in Patch.objects.filter(pk__in=related_patch_ids).values("id", "title")
    }

    risk_items: list[RiskItem] = []
    for binding in bindings:
        target = binding.target
        baseline = binding.baseline
        reqs = req_by_baseline.get(baseline.id, [])

        # 只有当前有效评估结果才能生成风险；旧快照仅作为历史证据保留。
        if binding.compliance_status in (
            ComplianceStatus.PENDING,
            ComplianceStatus.EVALUATING,
            ComplianceStatus.UNCONFIGURED,
            ComplianceStatus.FAILED,
        ):
            continue

        for req in reqs:
            patch = req.patch
            snapshot = snapshots.get((binding.id, req.id))

            if snapshot:
                # 有评估快照时优先按快照判断
                compliance = RiskCompliance.SATISFIED if snapshot.satisfied else RiskCompliance.MISSING
            else:
                compliance = _compute_compliance(has_binding=True)

            remediation = _compute_remediation(
                target.id,
                patch.id,
                compliance,
                snapshot.evaluated_at if snapshot else None,
            )

            # 跳过已满足+已修复的，不展示
            if compliance == RiskCompliance.SATISFIED and remediation == RemediationStatus.FIXED:
                continue

            detail_fields = _get_patch_detail_fields(patch)
            condition = req.condition
            if not condition:
                if patch.os_type == "windows" and detail_fields["kb_number"]:
                    condition = f"装 {detail_fields['kb_number']} 或有效替代 KB"
                elif patch.os_type == "linux" and detail_fields["pkg_name"]:
                    condition = f"包版本 ≥ {detail_fields['pkg_version']}"

            dep_ids = list(dict.fromkeys((patch.dependency_ids or []) + (patch.replacement_ids or [])))
            dep_titles = [related_titles.get(pid, "") for pid in dep_ids]
            deps = "、".join([t for t in dep_titles if t]) or ""

            # 从快照 evidence 中提取安装影响信息
            install_impact = {}
            if snapshot and isinstance(snapshot.evidence, dict):
                install_impact = snapshot.evidence.get('install_impact', {})

            risk_items.append(
                RiskItem(
                    host_id=target.id,
                    host_name=target.name,
                    host_ip=target.ip,
                    patch_id=patch.id,
                    baseline_id=baseline.id,
                    baseline_name=baseline.name,
                    compliance=compliance,
                    remediation=remediation,
                    condition=condition,
                    deps=deps,
                    install_impact=install_impact,
                    evaluated_at=snapshot.evaluated_at if snapshot else None,
                    **detail_fields,
                )
            )

    return risk_items


def aggregate_by_host(risk_items: list[RiskItem]) -> list[dict]:
    """按主机视角聚合"""
    by_host: dict[int, list[RiskItem]] = defaultdict(list)
    for item in risk_items:
        by_host[item.host_id].append(item)

    result = []
    for host_id, items in by_host.items():
        first = items[0]
        dist = _compute_dist(items)
        result.append({
            "key": f"h-{host_id}",
            "host": first.host_name,
            "host_ip": first.host_ip,
            "os_type": first.os_type,
            "baseline": first.baseline_name,
            "baseline_id": first.baseline_id,
            "missing": sum(1 for i in items if i.compliance == RiskCompliance.MISSING),
            "evaluated_at": _latest_evaluated_at(items),
            "dist": dist,
            "items": [i.to_dict() for i in items],
        })
    return result


def aggregate_by_patch(risk_items: list[RiskItem]) -> list[dict]:
    """按补丁视角聚合"""
    by_patch: dict[int, list[RiskItem]] = defaultdict(list)
    for item in risk_items:
        by_patch[item.patch_id].append(item)

    result = []
    for patch_id, items in by_patch.items():
        first = items[0]
        dist = _compute_dist(items)
        patch_label = first.kb_number or first.pkg_name or first.patch_title
        result.append({
            "key": f"p-{patch_id}",
            "patch": patch_label,
            "sub": first.patch_title,
            "sev": first.patch_severity,
            "hosts": len(items),
            "evaluated_at": _latest_evaluated_at(items),
            "dist": dist,
            "items": [i.to_dict() for i in items],
        })
    return result


def _build_apply_label(items: list[RiskItem]) -> str:
    """根据风险项推断基线适用范围，如 'Windows · Windows Server 2019 · x64'。"""
    if not items:
        return ""
    first = items[0]
    os_label = "Windows" if first.os_type == "windows" else "Linux" if first.os_type == "linux" else (first.os_type or "")
    parts = [os_label]

    versions = sorted({i.version for i in items if i.version})
    if versions:
        parts.append(", ".join(versions)[:64])

    archs = sorted({i.arch for i in items if i.arch})
    if archs:
        parts.append(", ".join(archs)[:32])

    return " · ".join(parts)


def aggregate_by_baseline(risk_items: list[RiskItem]) -> list[dict]:
    """按基线视角聚合"""
    by_baseline: dict[int, list[RiskItem]] = defaultdict(list)
    for item in risk_items:
        by_baseline[item.baseline_id].append(item)

    result = []
    for baseline_id, items in by_baseline.items():
        first = items[0]
        dist = _compute_dist(items)
        result.append({
            "key": f"b-{baseline_id}",
            "baseline": first.baseline_name,
            "baseline_id": baseline_id,
            "apply": _build_apply_label(items),
            "evaluated_at": _latest_evaluated_at(items),
            "dist": dist,
            "items": [i.to_dict() for i in items],
        })
    return result


def _latest_evaluated_at(items: list[RiskItem]) -> str | None:
    values = [item.evaluated_at for item in items if item.evaluated_at]
    return max(values).isoformat() if values else None


def _compute_dist(items: list[RiskItem]) -> list[dict]:
    """计算治理状态分布"""
    status_labels = {
        RemediationStatus.UNPLANNED: "待修复",
        RemediationStatus.SCHEDULED: "已计划",
        RemediationStatus.REMEDIATING: "修复中",
        "installing": "安装中",
        "rebooting": "重启中",
        "verifying": "验证中",
        RemediationStatus.PENDING_REBOOT: "待重启",
        RemediationStatus.FAILED: "修复失败",
        RemediationStatus.FIXED: "已修复",
    }
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        if item.compliance == RiskCompliance.INVALIDATED:
            counts["已失效"] += 1
        else:
            counts[status_labels.get(item.remediation, "待修复")] += 1

    color_map = {
        "待修复": "warning",
        "已计划": "processing",
        "修复中": "purple",
        "安装中": "processing",
        "重启中": "processing",
        "验证中": "processing",
        "待重启": "default",
        "修复失败": "error",
        "已修复": "success",
        "已失效": "default",
    }
    return [{"label": f"{label} {count}", "color": color_map.get(label, "default")} for label, count in counts.items()]


def _has_active_assessment(target_id: int) -> bool:
    """是否存在正在运行的 assess/verify 任务会重新计算该目标合规状态。"""
    return GovernanceTask.objects.filter(
        host_results__target_id=target_id,
        task_type__in=(GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY),
        status__in=GovernanceTaskStatus.ACTIVE_STATES,
    ).exists()


def compute_host_compliance_status(target: PatchTarget) -> str:
    """计算单台主机的合规状态

    优先读 HostBaselineBinding 持久化字段（由评估任务写回）；
    无 binding 时返回 UNCONFIGURED；
    已绑定且存在进行中的 assess/verify 任务时返回 EVALUATING；
    已绑定但尚未完成过评估时返回 PENDING；
    评估完成后按 persistence 状态或 missing_count 推断。
    """
    binding = getattr(target, "baseline_binding", None)
    if not binding:
        return ComplianceStatus.UNCONFIGURED

    # 有正在进行的评估/验证任务时，显示评估中
    if _has_active_assessment(target.id):
        return ComplianceStatus.EVALUATING

    # 已绑定但还未执行过评估：显示待评估
    if binding.compliance_status == ComplianceStatus.PENDING and not binding.last_evaluated_at:
        return ComplianceStatus.PENDING

    if binding.compliance_status and binding.compliance_status != ComplianceStatus.PENDING:
        return binding.compliance_status

    # 兼容旧数据：binding 状态仍为 PENDING 但已有评估时间时，按成功任务/缺失数推断
    if _binding_has_recent_success(binding):
        return ComplianceStatus.COMPLIANT
    if binding.missing_count and binding.missing_count > 0:
        return ComplianceStatus.NON_COMPLIANT
    return ComplianceStatus.COMPLIANT


def _binding_has_recent_success(binding) -> bool:
    """该 binding 全部要求都已有成功完成的治理任务（最近一次评估结果）"""
    reqs = binding.baseline.requirements.all()
    if not reqs:
        return True
    for req in reqs:
        if not _is_satisfied_by_task(binding.target_id, req.patch_id):
            return False
    return True


def filter_risk_items(items: list[RiskItem], query_params) -> list[RiskItem]:
    """按查询参数过滤风险项

    支持：
    - compliance: 风险项合规状态（missing/satisfied/invalidated）
    - remediation: 治理状态（unplanned/scheduled/remediating/pending_reboot/failed/fixed）
    - severity: 严重级别（critical/important/moderate/low/unspecified）
    - os_type: windows/linux
    - host_id: 单主机
    - baseline_id: 单基线
    - patch_id: 单补丁
    - host_name: 模糊匹配主机名/IP
    - patch_name: 模糊匹配补丁标题/KB/包名
    - baseline_name: 模糊匹配基线名称
    - search: 全局模糊匹配 host_name/host_ip/patch_title/kb/pkg/baseline
    """
    compliance = (query_params.get("compliance") or "").strip()
    remediation = (query_params.get("remediation") or "").strip()
    severity = (query_params.get("severity") or "").strip()
    os_type = (query_params.get("os_type") or "").strip()
    host_id = query_params.get("host_id")
    baseline_id = query_params.get("baseline_id")
    patch_id = query_params.get("patch_id")
    host_name = (query_params.get("host_name") or "").strip().lower()
    patch_name = (query_params.get("patch_name") or "").strip().lower()
    baseline_name = (query_params.get("baseline_name") or "").strip().lower()
    search = (query_params.get("search") or "").strip().lower()

    def _match(item: RiskItem) -> bool:
        if compliance and item.compliance != compliance:
            return False
        if remediation and item.remediation != remediation:
            return False
        if severity and (item.patch_severity or "") != severity:
            return False
        if os_type and item.os_type != os_type:
            return False
        if host_id and str(item.host_id) != str(host_id):
            return False
        if baseline_id and str(item.baseline_id) != str(baseline_id):
            return False
        if patch_id and str(item.patch_id) != str(patch_id):
            return False
        if host_name:
            if host_name not in (item.host_name or "").lower():
                return False
        if patch_name:
            hay = " ".join([
                item.patch_title or "",
                item.kb_number or "",
                item.pkg_name or "",
            ]).lower()
            if patch_name not in hay:
                return False
        if baseline_name:
            if baseline_name not in (item.baseline_name or "").lower():
                return False
        if search:
            hay = " ".join([
                item.host_name or "",
                item.host_ip or "",
                item.patch_title or "",
                item.kb_number or "",
                item.pkg_name or "",
                item.baseline_name or "",
            ]).lower()
            if search not in hay:
                return False
        return True

    return [i for i in items if _match(i)]
