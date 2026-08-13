"""基线合规详情的双视角读模型。"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.core.paginator import Paginator
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery

from apps.patch_mgmt.constants import (
    ComplianceStatus,
    GovernanceTaskStatus,
    GovernanceTaskType,
)
from apps.patch_mgmt.models import (
    GovernanceTaskHost,
    HostBaselineBinding,
    HostComplianceSnapshot,
)
from apps.patch_mgmt.services.governance_convergence import (
    project_host_state,
)
from apps.patch_mgmt.utils.i18n import patch_message


STATUS_ORDER = (
    "satisfied",
    "missing",
    "not_applicable",
    "unknown",
    "pending",
    "evaluating",
    "failed",
)


def _isoformat(value):
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _paginate(queryset, page: int, page_size: int):
    if page_size == -1:
        items = list(queryset)
        return len(items), items
    paginator = Paginator(queryset, page_size)
    if page > paginator.num_pages and paginator.count:
        return paginator.count, []
    return paginator.count, list(paginator.get_page(page).object_list)


def _projected_host_statuses(bindings) -> dict[int, str]:
    """批量投影活动评估状态，避免列表中逐主机查询。"""
    target_ids = [binding.target_id for binding in bindings]
    if not target_ids:
        return {}
    stages_by_target = defaultdict(list)
    hosts = (
        GovernanceTaskHost.objects.filter(
            target_id__in=target_ids,
            task__task_type__in=(
                GovernanceTaskType.ASSESS,
                GovernanceTaskType.VERIFY,
            ),
            task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
        )
        .select_related("task")
        .order_by("-created_at")
    )
    for host in hosts:
        stages_by_target[host.target_id].append(project_host_state(host).stage)

    projected = {}
    terminal_stages = {"failed", "completed", "cancelled", "pending_confirmation"}
    for target_id, stages in stages_by_target.items():
        if any(stage not in terminal_stages for stage in stages):
            projected[target_id] = ComplianceStatus.EVALUATING
        elif any(stage == "failed" for stage in stages):
            projected[target_id] = ComplianceStatus.FAILED
    return projected


def _projected_host_failures(bindings) -> dict[int, dict]:
    """返回当前页主机的投影失败上下文，包括尚未持久化的超时。"""
    target_ids = [binding.target_id for binding in bindings]
    if not target_ids:
        return {}
    failures = {}
    hosts = (
        GovernanceTaskHost.objects.filter(
            target_id__in=target_ids,
            task__task_type__in=(
                GovernanceTaskType.ASSESS,
                GovernanceTaskType.VERIFY,
            ),
            task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
        )
        .select_related("task")
        .order_by("-created_at", "-id")
    )
    for host in hosts:
        if host.target_id in failures:
            continue
        state = project_host_state(host)
        if state.stage != "failed":
            continue
        failures[host.target_id] = {
            "reason": state.reason or state.timeout_reason or "",
            "error_code": state.error_code or "",
            "failed_stage": state.failed_stage or host.task.task_type,
            "evaluated_at": host.updated_at,
        }
    return failures


def _effective_host_status(
    binding: HostBaselineBinding, projected_statuses: dict[int, str] | None = None
) -> str:
    projected = (projected_statuses or {}).get(binding.target_id)
    if projected in {ComplianceStatus.EVALUATING, ComplianceStatus.FAILED}:
        return projected
    if (
        binding.compliance_status == ComplianceStatus.PENDING
        and binding.last_evaluated_at is None
    ):
        return ComplianceStatus.PENDING
    return binding.compliance_status or ComplianceStatus.PENDING


def _fallback_cell_status(host_status: str) -> str:
    if host_status in {
        ComplianceStatus.PENDING,
        ComplianceStatus.EVALUATING,
        ComplianceStatus.FAILED,
    }:
        return host_status
    return ComplianceStatus.UNKNOWN


def _fallback_cell_context(request, binding, host_status, *, failure=None, evaluation=None):
    """无当前补丁快照时，把主机态投影成单元格的原因与时间。"""
    status = _fallback_cell_status(host_status)
    if status == ComplianceStatus.PENDING:
        reason = patch_message(
            request, "message.assessment_not_run", "Assessment has not been run"
        )
        evaluated_at = None
    elif status == ComplianceStatus.EVALUATING:
        reason = patch_message(
            request, "message.assessment_running", "Assessment task is running"
        )
        evaluated_at = (evaluation or {}).get("evaluated_at")
    elif status == ComplianceStatus.FAILED:
        reason = (failure or {}).get("reason") or patch_message(
            request, "message.assessment_failed", "Assessment failed"
        )
        evaluated_at = (failure or {}).get("evaluated_at") or binding.updated_at
    else:
        reason = patch_message(
            request,
            "message.assessment_snapshot_incomplete",
            "No current valid assessment snapshot; assessment data is incomplete",
        )
        evaluated_at = binding.last_evaluated_at or binding.updated_at
    return {
        "status": status,
        "reason": reason,
        "evaluated_at": evaluated_at,
        "failure": failure if status == ComplianceStatus.FAILED else None,
    }


def _public_failure(failure):
    if not failure:
        return failure
    return {
        "reason": failure.get("reason", ""),
        "error_code": failure.get("error_code", ""),
        "failed_stage": failure.get("failed_stage", ""),
    }


def _projected_host_evaluations(bindings) -> dict[int, dict]:
    """批量返回活动评估的开始时间。"""
    target_ids = [binding.target_id for binding in bindings]
    if not target_ids:
        return {}
    result = {}
    hosts = (
        GovernanceTaskHost.objects.filter(
            target_id__in=target_ids,
            task__task_type__in=(GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY),
            task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
        )
        .select_related("task")
        .order_by("-created_at", "-id")
    )
    terminal = {"failed", "completed", "cancelled", "pending_confirmation"}
    for host in hosts:
        if host.target_id in result or project_host_state(host).stage in terminal:
            continue
        result[host.target_id] = {
            "evaluated_at": host.started_at
            or host.stage_started_at
            or host.task.started_at
            or host.created_at
        }
    return result


def _distribution(counts: Counter) -> list[dict]:
    return [
        {"status": item, "count": counts[item]}
        for item in STATUS_ORDER
        if counts[item] > 0
    ]


def _requirement_identifier(requirement) -> str:
    patch = requirement.patch
    if patch.os_type == "windows":
        detail = getattr(patch, "windows_detail", None)
        return getattr(detail, "kb_number", "") or patch.title
    detail = getattr(patch, "linux_detail", None)
    return getattr(detail, "pkg_name", "") or patch.title


def _requirement_condition(request, requirement) -> str:
    if requirement.condition:
        return requirement.condition
    patch = requirement.patch
    if patch.os_type == "windows":
        return patch_message(
            request,
            "message.windows_requirement",
            "Install {kb} or a valid superseding KB",
            kb=_requirement_identifier(requirement),
        )
    detail = getattr(patch, "linux_detail", None)
    version = getattr(detail, "pkg_version", "")
    return (
        patch_message(
            request,
            "message.linux_requirement",
            "Package version ≥ {version}",
            version=version,
        )
        if version
        else ""
    )


def _requirement_summary(request, requirement) -> dict:
    patch = requirement.patch
    return {
        "requirement_id": requirement.id,
        "patch_id": patch.id,
        "identifier": _requirement_identifier(requirement),
        "title": patch.title,
        "severity": patch.severity,
        "severity_display": patch.get_severity_display(),
        "condition": _requirement_condition(request, requirement),
    }


def _current_snapshots(bindings):
    binding_ids = [binding.id for binding in bindings]
    if not binding_ids:
        return {}
    snapshots = HostComplianceSnapshot.objects.filter(
        binding_id__in=binding_ids,
        evaluated_at=F("binding__last_evaluated_at"),
    )
    return {
        (snapshot.binding_id, snapshot.requirement_id): snapshot
        for snapshot in snapshots
    }


def _host_objects(bindings, snapshots, requirement_count: int) -> list[dict]:
    projected_statuses = _projected_host_statuses(bindings)
    counts_by_binding = defaultdict(Counter)
    for (binding_id, _), snapshot in snapshots.items():
        counts_by_binding[binding_id][snapshot.status] += 1
    items = []
    for binding in bindings:
        host_status = _effective_host_status(binding, projected_statuses)
        counts = counts_by_binding[binding.id].copy()
        missing_snapshot_count = requirement_count - sum(counts.values())
        if missing_snapshot_count > 0:
            counts[_fallback_cell_status(host_status)] += missing_snapshot_count
        items.append(
            {
                "id": binding.target_id,
                "binding_id": binding.id,
                "name": binding.target.name,
                "ip": binding.target.ip,
                "compliance_status": host_status,
                "missing_count": binding.missing_count,
                "last_evaluated_at": _isoformat(binding.last_evaluated_at),
                "distribution": _distribution(counts),
            }
        )
    return items


def _latest_host_assessment_failure(target_id: int) -> dict | None:
    hosts = (
        GovernanceTaskHost.objects.filter(
            target_id=target_id,
            task__task_type__in=(
                GovernanceTaskType.ASSESS,
                GovernanceTaskType.VERIFY,
            ),
        )
        .select_related("task")
        .order_by("-created_at", "-id")
    )[:20]
    for host in hosts:
        state = project_host_state(host)
        if state.stage != "failed":
            continue
        return {
            "reason": state.reason or state.timeout_reason or "",
            "error_code": state.error_code or "",
            "failed_stage": state.failed_stage or host.task.task_type,
            "evaluated_at": host.updated_at,
        }
    return None


def _host_details(request, baseline, binding, query, host_status: str) -> dict:
    queryset = baseline.requirements.select_related(
        "patch__windows_detail", "patch__linux_detail"
    ).order_by("id")
    search = query["search"]
    if search:
        queryset = queryset.filter(
            Q(patch__title__icontains=search)
            | Q(patch__windows_detail__kb_number__icontains=search)
            | Q(patch__linux_detail__pkg_name__icontains=search)
        )

    current_snapshots = (
        HostComplianceSnapshot.objects.filter(
            binding=binding,
            evaluated_at=binding.last_evaluated_at,
        )
        if binding.last_evaluated_at
        else HostComplianceSnapshot.objects.none()
    )
    requested_status = query["status"]
    if requested_status:
        if requested_status in {"satisfied", "missing", "not_applicable", "unknown"}:
            matching_ids = current_snapshots.filter(status=requested_status).values(
                "requirement_id"
            )
            if requested_status == _fallback_cell_status(host_status):
                current_ids = current_snapshots.values("requirement_id")
                queryset = queryset.filter(
                    Q(id__in=matching_ids) | ~Q(id__in=current_ids)
                )
            else:
                queryset = queryset.filter(id__in=matching_ids)
        elif requested_status == _fallback_cell_status(host_status):
            queryset = queryset.exclude(compliance_snapshots__in=current_snapshots)
        else:
            queryset = queryset.none()
        queryset = queryset.distinct()

    count, requirements = _paginate(queryset, query["page"], query["page_size"])
    snapshots = {
        snapshot.requirement_id: snapshot
        for snapshot in current_snapshots.filter(
            requirement_id__in=[item.id for item in requirements]
        )
    }
    fallback_status = _fallback_cell_status(host_status)
    failure = (
        _latest_host_assessment_failure(binding.target_id)
        if fallback_status == ComplianceStatus.FAILED
        else None
    )
    evaluation = _projected_host_evaluations([binding]).get(binding.target_id)
    fallback = _fallback_cell_context(
        request, binding, host_status, failure=failure, evaluation=evaluation
    )
    items = []
    for requirement in requirements:
        snapshot = snapshots.get(requirement.id)
        item = _requirement_summary(request, requirement)
        item.update(
            {
                "status": snapshot.status if snapshot else fallback_status,
                "status_scope": "requirement" if snapshot else "host",
                "satisfied": bool(snapshot.satisfied) if snapshot else False,
                "evidence": snapshot.evidence if snapshot else {},
                "reason": snapshot.reason if snapshot else fallback["reason"],
                "evaluated_at": _isoformat(
                    snapshot.evaluated_at if snapshot else fallback["evaluated_at"]
                ),
            }
        )
        items.append(item)
    return {
        "count": count,
        "page": query["page"],
        "page_size": query["page_size"],
        "items": items,
    }


def _visible_bindings(request, baseline):
    from apps.patch_mgmt.services.target_access import target_access_scope

    visible_target_ids = target_access_scope(request).queryset("View").values("id")
    return baseline.host_bindings.filter(
        target_id__in=visible_target_ids
    ).select_related("target", "target__baseline_binding")


def _persisted_fallback_status(compliance_status: str) -> str:
    return _fallback_cell_status(compliance_status)


def _patch_distribution_counts(requirements, bindings) -> dict[int, Counter]:
    """用数据库聚合统计补丁×主机分布，不把基线全部绑定加载到内存。"""
    requirement_ids = [requirement.id for requirement in requirements]
    if not requirement_ids:
        return {}

    fallback_counts = Counter()
    binding_groups = bindings.values("compliance_status").annotate(count=Count("id"))
    for group in binding_groups:
        fallback_counts[_persisted_fallback_status(group["compliance_status"])] += (
            group["count"]
        )

    result = {
        requirement_id: Counter(fallback_counts)
        for requirement_id in requirement_ids
    }
    snapshot_groups = (
        HostComplianceSnapshot.objects.filter(
            binding__in=bindings,
            requirement_id__in=requirement_ids,
            evaluated_at=F("binding__last_evaluated_at"),
        )
        .values(
            "requirement_id",
            "status",
            "binding__compliance_status",
        )
        .annotate(count=Count("id"))
    )
    for group in snapshot_groups:
        counts = result[group["requirement_id"]]
        fallback_status = _persisted_fallback_status(
            group["binding__compliance_status"]
        )
        counts[fallback_status] -= group["count"]
        counts[group["status"]] += group["count"]
    return result


def _patch_objects(request, requirements, distributions) -> list[dict]:
    items = []
    for requirement in requirements:
        item = _requirement_summary(request, requirement)
        item.update(
            {
                "id": requirement.id,
                "distribution": _distribution(distributions[requirement.id]),
            }
        )
        items.append(item)
    return items


def _patch_details(request, baseline, requirement, query) -> dict:
    bindings = _visible_bindings(request, baseline)
    latest_failure = GovernanceTaskHost.objects.filter(
        target_id=OuterRef("target_id"),
        task__task_type__in=(
            GovernanceTaskType.ASSESS,
            GovernanceTaskType.VERIFY,
        ),
        stage="failed",
    ).order_by("-created_at", "-id")
    bindings = bindings.annotate(
        assessment_failure_reason=Subquery(latest_failure.values("reason")[:1]),
        assessment_failure_error_code=Subquery(
            latest_failure.values("error_code")[:1]
        ),
        assessment_failure_stage=Subquery(
            latest_failure.values("failed_stage")[:1]
        ),
        assessment_failure_at=Subquery(latest_failure.values("updated_at")[:1]),
    )
    search = query["search"]
    if search:
        bindings = bindings.filter(
            Q(target__name__icontains=search) | Q(target__ip__icontains=search)
        )
    bindings = bindings.order_by("target__name", "target_id")

    requested_status = query["status"]
    if requested_status:
        current_snapshots = HostComplianceSnapshot.objects.filter(
            requirement=requirement,
            evaluated_at=F("binding__last_evaluated_at"),
        )
        if requested_status in {"satisfied", "missing", "not_applicable", "unknown"}:
            bindings = bindings.annotate(
                has_current_snapshot=Exists(
                    current_snapshots.filter(binding_id=OuterRef("id"))
                ),
                has_requested_snapshot=Exists(
                    current_snapshots.filter(
                        binding_id=OuterRef("id"), status=requested_status
                    )
                ),
            )
            status_query = Q(has_requested_snapshot=True)
            if requested_status == ComplianceStatus.UNKNOWN:
                status_query |= Q(
                    has_current_snapshot=False,
                    compliance_status__in=(
                        ComplianceStatus.COMPLIANT,
                        ComplianceStatus.NON_COMPLIANT,
                        ComplianceStatus.UNKNOWN,
                        ComplianceStatus.UNCONFIGURED,
                        ComplianceStatus.NOT_APPLICABLE,
                    ),
                )
            bindings = bindings.filter(status_query)
            if requested_status == ComplianceStatus.UNKNOWN:
                active_hosts = GovernanceTaskHost.objects.filter(
                    target_id__in=bindings.values("target_id"),
                    task__task_type__in=(
                        GovernanceTaskType.ASSESS,
                        GovernanceTaskType.VERIFY,
                    ),
                    task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
                )
                bindings = bindings.exclude(
                    target_id__in=active_hosts.exclude(
                        stage__in=(
                            "failed",
                            "completed",
                            "cancelled",
                            "pending_confirmation",
                        )
                    ).values("target_id")
                ).exclude(
                    target_id__in=active_hosts.filter(stage="failed").values(
                        "target_id"
                    )
                )
        elif requested_status in {"pending", "evaluating", "failed"}:
            bindings = bindings.exclude(compliance_snapshots__in=current_snapshots)
            assessment_hosts = GovernanceTaskHost.objects.filter(
                target_id__in=bindings.values("target_id"),
                task__task_type__in=(
                    GovernanceTaskType.ASSESS,
                    GovernanceTaskType.VERIFY,
                ),
                task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
            )
            evaluating_target_ids = assessment_hosts.exclude(
                stage__in=("failed", "completed", "cancelled", "pending_confirmation")
            ).values("target_id")
            failed_target_ids = assessment_hosts.filter(stage="failed").values(
                "target_id"
            )
            if requested_status == "pending":
                bindings = bindings.filter(
                    compliance_status=ComplianceStatus.PENDING,
                    last_evaluated_at__isnull=True,
                ).exclude(
                    target_id__in=evaluating_target_ids
                ).exclude(target_id__in=failed_target_ids)
            elif requested_status == "failed":
                bindings = bindings.filter(
                    Q(compliance_status=ComplianceStatus.FAILED)
                    | Q(target_id__in=failed_target_ids)
                )
            else:
                bindings = bindings.filter(
                    Q(compliance_status=ComplianceStatus.EVALUATING)
                    | Q(target_id__in=evaluating_target_ids)
                )
        else:
            bindings = bindings.none()
        bindings = bindings.distinct()

    count, page_bindings = _paginate(bindings, query["page"], query["page_size"])
    snapshots = _current_snapshots(page_bindings)
    projected_statuses = _projected_host_statuses(page_bindings)
    projected_failures = _projected_host_failures(page_bindings)
    projected_evaluations = _projected_host_evaluations(page_bindings)
    items = []
    for binding in page_bindings:
        host_status = _effective_host_status(binding, projected_statuses)
        snapshot = snapshots.get((binding.id, requirement.id))
        failure = None
        if snapshot is None and host_status == ComplianceStatus.FAILED:
            failure = projected_failures.get(binding.target_id) or {
                "reason": binding.assessment_failure_reason or "",
                "error_code": binding.assessment_failure_error_code or "",
                "failed_stage": binding.assessment_failure_stage or "",
                "evaluated_at": binding.assessment_failure_at,
            }
        fallback = _fallback_cell_context(
            request,
            binding,
            host_status,
            failure=failure,
            evaluation=projected_evaluations.get(binding.target_id),
        )
        items.append(
            {
                "binding_id": binding.id,
                "target_id": binding.target_id,
                "target_name": binding.target.name,
                "target_ip": binding.target.ip,
                "compliance_status": host_status,
                "status": snapshot.status
                if snapshot
                else _fallback_cell_status(host_status),
                "status_scope": "requirement" if snapshot else "host",
                "satisfied": bool(snapshot.satisfied) if snapshot else False,
                "evidence": snapshot.evidence if snapshot else {},
                "reason": snapshot.reason if snapshot else fallback["reason"],
                "failure": _public_failure(failure),
                "evaluated_at": _isoformat(snapshot.evaluated_at)
                if snapshot
                else _isoformat(fallback["evaluated_at"]),
            }
        )
    return {
        "count": count,
        "page": query["page"],
        "page_size": query["page_size"],
        "items": items,
    }


def _baseline_summary(baseline) -> dict:
    return {
        "id": baseline.id,
        "name": baseline.name,
        "os_type": baseline.os_type,
    }


def build_baseline_compliance_objects(request, baseline, query) -> dict:
    """返回当前视角的左侧对象列表，不构建任何右侧明细。"""
    perspective = query["perspective"]
    page = query.get("page", 1)
    page_size = query.get("page_size", -1)

    if perspective == "host":
        objects = _visible_bindings(request, baseline).order_by(
            "target__name", "target_id"
        )
        count, bindings = _paginate(objects, page, page_size)
        items = _host_objects(
            bindings,
            _current_snapshots(bindings),
            baseline.requirements.count(),
        )
    else:
        bindings = _visible_bindings(request, baseline)
        objects = baseline.requirements.select_related(
            "patch__windows_detail", "patch__linux_detail"
        ).order_by("id")
        count, requirements = _paginate(objects, page, page_size)
        items = _patch_objects(
            request,
            requirements,
            _patch_distribution_counts(requirements, bindings),
        )

    return {
        "baseline": _baseline_summary(baseline),
        "perspective": perspective,
        "count": count,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


def _empty_details(query) -> dict:
    return {
        "count": 0,
        "page": query["page"],
        "page_size": query["page_size"],
        "items": [],
    }


def build_baseline_compliance_details(request, baseline, query) -> dict:
    """返回一个选中对象的摘要和分页明细，不构建左侧对象列表。"""
    perspective = query["perspective"]
    selected_id = query["selected_id"]
    selected_data = None
    details = _empty_details(query)

    if perspective == "host":
        binding = _visible_bindings(request, baseline).filter(
            target_id=selected_id
        ).first()
        if binding is not None:
            host_status = _effective_host_status(
                binding, _projected_host_statuses([binding])
            )
            selected_data = _host_objects(
                [binding],
                _current_snapshots([binding]),
                baseline.requirements.count(),
            )[0]
            if host_status == ComplianceStatus.FAILED:
                selected_data["failure"] = _public_failure(
                    _latest_host_assessment_failure(binding.target_id)
                )
            details = _host_details(
                request, baseline, binding, query, host_status
            )
    else:
        requirement = (
            baseline.requirements.select_related(
                "patch__windows_detail", "patch__linux_detail"
            )
            .filter(id=selected_id)
            .first()
        )
        if requirement is not None:
            bindings = _visible_bindings(request, baseline)
            distributions = _patch_distribution_counts([requirement], bindings)
            selected_data = _patch_objects(
                request, [requirement], distributions
            )[0]
            details = _patch_details(request, baseline, requirement, query)

    return {
        "baseline": _baseline_summary(baseline),
        "perspective": perspective,
        "selected": selected_data,
        "details": details,
    }
