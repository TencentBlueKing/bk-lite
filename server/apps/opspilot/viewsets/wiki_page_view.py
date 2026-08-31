import json
from collections import defaultdict
from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot import tasks as _opspilot_tasks
from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, Material, PageEvidence, WikiDirectory, WikiKnowledgeBase
from apps.opspilot.serializers.wiki_serializers import BuildRecordSerializer, KnowledgePageSerializer, PageVersionSerializer
from apps.opspilot.services.wiki.active_generation_query_service import ActiveGenerationReadError, page_queryset
from apps.opspilot.services.wiki.build_generation_service import BuildGenerationError
from apps.opspilot.services.wiki.cascade_service import MAINTENANCE_STAGE_KEYS, cascade
from apps.opspilot.services.wiki.directory_service import DirectoryServiceError, archive_pages, move_pages, restore_archived_pages, restore_pages_auto
from apps.opspilot.services.wiki.embedding_service import index_version, reindex_page_chunks
from apps.opspilot.services.wiki.index_rebuild_service import rebuild_page_indexes
from apps.opspilot.services.wiki.index_status_service import failed_index_stages_for_pages
from apps.opspilot.services.wiki.maintenance_errors import humanize_maintenance_error
from apps.opspilot.services.wiki.material_build_queue_service import (
    QUEUE_ITEM_TRIGGER,
    RUNNER_TRIGGER,
    MaterialBuildQueueError,
    enqueue_material_builds,
    kb_has_user_build_in_progress,
    reconcile_orphaned_material_builds,
    release_idle_runner_lease,
    repair_queue_runner_status_from_counts,
    unstick_material_for_cancelled_build,
)
from apps.opspilot.services.wiki.page_service import PageServiceError, create_manual_page, diff_versions, edit_page, restore_version, save_answer_page
from apps.opspilot.viewsets.wiki_team_scope import WikiTeamScopeMixin
from apps.system_mgmt.utils.operation_log_utils import log_operation


def _page_list_metadata(page_items, knowledge_base):
    page_ids = {page.pk for page in page_items}
    source_names = defaultdict(list)
    if page_ids:
        for page_id, material_name in (
            PageEvidence.objects.filter(page_id__in=page_ids).values_list("page_id", "material__name").order_by("page_id", "material__name")
        ):
            name = str(material_name or "").strip()
            if name and name not in source_names[page_id]:
                source_names[page_id].append(name)

    source_summary_lookup = {}
    for page_id, names in source_names.items():
        preview = "、".join(names[:2])
        suffix = "…" if len(names) > 2 else ""
        source_summary_lookup[page_id] = f"{len(names)} 个资料：{preview}{suffix}"

    conflict_types = {
        "conflict": "知识冲突",
        "material_update": "资料更新冲突",
        "duplicate": "重复知识",
        "cannot_merge": "无法自动合并",
    }
    conflict_lookup = defaultdict(lambda: {"count": 0, "labels": []})
    if page_ids:
        checks = CheckItem.objects.filter(
            knowledge_base=knowledge_base,
            status="open",
            check_type__in=tuple(conflict_types),
        ).values("check_type", "related")
        for check in checks:
            related = check.get("related") or {}
            related_pages = related.get("pages") or []
            label = conflict_types.get(check["check_type"], check["check_type"])
            for raw_page_id in related_pages:
                try:
                    page_id = int(raw_page_id)
                except (TypeError, ValueError):
                    continue
                if page_id not in page_ids:
                    continue
                item = conflict_lookup[page_id]
                item["count"] += 1
                if label not in item["labels"]:
                    item["labels"].append(label)
    normalized_conflicts = {
        page_id: {
            "count": item["count"],
            "summary": "、".join(item["labels"]),
        }
        for page_id, item in conflict_lookup.items()
    }
    return {
        "source_summary_lookup": source_summary_lookup,
        "conflict_lookup": normalized_conflicts,
    }


def _active_generation_conflict(error):
    return JsonResponse(
        {
            "result": False,
            "message": str(error),
            "code": error.code,
            "details": error.details,
        },
        status=409,
    )


def _directory_service_error(error):
    return JsonResponse(
        {
            "result": False,
            "message": str(error),
            "code": error.code,
            "retryable": error.retryable,
            "details": error.details,
        },
        status=error.status_code,
    )


def _build_generation_error(error):
    return JsonResponse(
        {
            "result": False,
            "message": str(error),
            "code": error.code,
            "retryable": error.retryable,
            "details": error.details,
        },
        status=409 if error.retryable else 422,
    )


@transaction.atomic
def _archive_pages_by_write_route(
    knowledge_base,
    *,
    page_ids,
    base_generation_id=None,
    structure_version=None,
    operator="",
):
    """Archive pages by publishing a governance generation."""

    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    locked_kb = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
    return archive_pages(
        locked_kb,
        page_ids=page_ids,
        base_generation_id=base_generation_id,
        structure_version=structure_version,
        operator=operator,
    )


@transaction.atomic
def _restore_archived_pages_by_write_route(
    knowledge_base,
    *,
    page_ids,
    base_generation_id=None,
    structure_version=None,
    operator="",
):
    """Restore archived pages by publishing a governance generation."""

    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    locked_kb = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
    return restore_archived_pages(
        locked_kb,
        page_ids=page_ids,
        base_generation_id=base_generation_id,
        structure_version=structure_version,
        operator=operator,
    )


def _decode_evidence_locator(locator):
    locator = (locator or "").strip()
    if not locator:
        return {}, ""
    try:
        value = json.loads(locator)
    except json.JSONDecodeError:
        return {}, locator
    return (value if isinstance(value, dict) else {}), ""


def _evidence_source_payload(evidence):
    locator, locator_raw = _decode_evidence_locator(evidence.locator)
    material = evidence.material
    version = evidence.material_version
    payload = {
        "id": evidence.id,
        "material": {
            "id": material.id,
            "name": material.name,
            "material_type": material.material_type,
            "status": material.status,
        },
        "material_version": None,
        "locator": locator,
        "locator_raw": locator_raw,
        "snippet": locator.get("snippet", ""),
    }
    if version:
        payload["material_version"] = {
            "id": version.id,
            "content_hash": version.content_hash,
            "content_locator": version.content_locator,
            "created_at": version.created_at,
        }
    return payload


_MAINTENANCE_STAGE_COUNT_KEYS = {
    "relations": ("relations",),
    "page_embedding": ("indexed_pages", "cleared_pages"),
    "chunk_embedding": ("indexed_chunks", "cleared_pages"),
    "check_sweep": ("auto_resolved",),
    "deleted_page_prune": ("pruned_checks", "pruned_build_records"),
}
_MAINTENANCE_RETRY_CLAIM_KEY = "_maintenance_retry_claim"
_MAINTENANCE_RETRY_CLAIM_TTL = timedelta(minutes=15)
_PARTITIONED_MAINTENANCE_KEYS = ("archive", "generated", "invalidated", "shared")


class MaintenanceRetryConflict(Exception):
    """The record already has a live retry claim or this worker lost its claim."""


def _maintenance_retry_claim_is_active(claim):
    if not isinstance(claim, dict) or not claim.get("token"):
        return False
    claimed_at = parse_datetime(str(claim.get("claimed_at") or ""))
    if claimed_at is None:
        return False
    if timezone.is_naive(claimed_at):
        claimed_at = timezone.make_aware(claimed_at, timezone.get_current_timezone())
    return claimed_at > timezone.now() - _MAINTENANCE_RETRY_CLAIM_TTL


@transaction.atomic
def _claim_maintenance_retry(record_id):
    record = BuildRecord.objects.select_for_update().get(pk=record_id)
    inputs = dict(record.inputs or {})
    existing_claim = inputs.get(_MAINTENANCE_RETRY_CLAIM_KEY)
    if _maintenance_retry_claim_is_active(existing_claim):
        raise MaintenanceRetryConflict("该维护记录正在重试，请稍后再试")
    token = uuid4().hex
    inputs[_MAINTENANCE_RETRY_CLAIM_KEY] = {
        "token": token,
        "claimed_at": timezone.now().isoformat(),
    }
    record.inputs = inputs
    record.save(update_fields=["inputs", "updated_at"])
    return record, token


@transaction.atomic
def _release_maintenance_retry_claim(record_id, token):
    record = BuildRecord.objects.select_for_update().filter(pk=record_id).first()
    if record is None:
        return
    inputs = dict(record.inputs or {})
    claim = inputs.get(_MAINTENANCE_RETRY_CLAIM_KEY)
    if not isinstance(claim, dict) or claim.get("token") != token:
        return
    inputs.pop(_MAINTENANCE_RETRY_CLAIM_KEY, None)
    record.inputs = inputs
    record.save(update_fields=["inputs", "updated_at"])


def _maintenance_errors(maintenance):
    errors = []

    def visit(value):
        if isinstance(value, dict):
            error = value.get("error")
            if error:
                errors.append(str(error))
            for key, child in value.items():
                if key != "error":
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(maintenance)
    return list(dict.fromkeys(errors))


def _maintenance_status_from_stages(stages):
    stage_values = [stage for stage in (stages or {}).values() if isinstance(stage, dict)]
    return "partial" if any(stage.get("status") == "failed" for stage in stage_values) else "success"


def _merge_selected_maintenance_retry(previous, retry_result, selected_stages):
    if not selected_stages:
        return retry_result

    merged = dict(previous or {})
    merged["event"] = retry_result.get("event", "maintenance_retry")
    merged["affected_page_ids"] = retry_result.get("affected_page_ids") or merged.get("affected_page_ids") or []
    merged_stages = dict(merged.get("stages") if isinstance(merged.get("stages"), dict) else {})
    retry_stages = retry_result.get("stages") if isinstance(retry_result.get("stages"), dict) else {}
    for stage in selected_stages:
        if stage in retry_stages:
            merged_stages[stage] = retry_stages[stage]
    merged["stages"] = merged_stages
    for stage in selected_stages:
        for count_key in _MAINTENANCE_STAGE_COUNT_KEYS.get(stage, ()):
            if count_key in retry_result:
                merged[count_key] = retry_result[count_key]
    merged["last_retry"] = {
        "stages": selected_stages,
        "status": retry_result.get("status", "success"),
    }
    merged["status"] = _maintenance_status_from_stages(merged_stages)
    return merged


def _parse_maintenance_retry_stages(request):
    raw = request.data.get("stages")
    if raw in (None, ""):
        return None, None
    if not isinstance(raw, list) or not raw:
        return None, JsonResponse({"result": False, "message": "stages 必须为非空数组"}, status=400)

    valid_stages = set(MAINTENANCE_STAGE_KEYS)
    parsed = []
    seen = set()
    for item in raw:
        stage = str(item or "").strip()
        if stage not in valid_stages:
            return None, JsonResponse({"result": False, "message": f"不支持的维护阶段: {stage}"}, status=400)
        if stage in seen:
            continue
        parsed.append(stage)
        seen.add(stage)
    return parsed, None


def _filter_build_records_by_material_name(queryset, *, knowledge_base_id, material_name):
    """按资料名模糊筛选构建记录；匹配 inputs.material_name 或关联 Material.name。"""
    keyword = (material_name or "").strip()
    if not keyword:
        return queryset

    material_ids = list(Material.objects.filter(knowledge_base_id=knowledge_base_id, name__icontains=keyword).values_list("id", flat=True)[:1000])
    term = Q(inputs__material_name__icontains=keyword)
    if material_ids:
        term |= Q(inputs__material_id__in=material_ids)
    return queryset.filter(term)


def _filter_build_records_by_maintenance(records, maintenance_status, maintenance_stage, maintenance_stage_status):
    if not any([maintenance_status, maintenance_stage, maintenance_stage_status]):
        return records

    filtered = []
    for record in records:
        maintenance = record.maintenance if isinstance(record.maintenance, dict) else {}
        if maintenance_status and maintenance.get("status") != maintenance_status:
            continue

        stages = maintenance.get("stages") if isinstance(maintenance.get("stages"), dict) else {}
        if maintenance_stage:
            stage = stages.get(maintenance_stage)
            if not isinstance(stage, dict):
                continue
            if maintenance_stage_status and stage.get("status") != maintenance_stage_status:
                continue
        elif maintenance_stage_status and not any(
            isinstance(stage, dict) and stage.get("status") == maintenance_stage_status for stage in stages.values()
        ):
            continue
        filtered.append(record)
    return filtered


def _create_page_lifecycle_record(
    knowledge_base,
    affected_page_ids,
    event,
    *,
    operator="",
    deleted_titles=None,
    prune_deleted_pages=False,
):
    affected_page_ids = list(dict.fromkeys(affected_page_ids or []))
    deleted_titles = list(dict.fromkeys(deleted_titles or []))
    return BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger=event,
        operator=operator or "",
        inputs={
            "maintenance_event": event,
            "deleted_titles": deleted_titles,
            "prune_deleted_pages": prune_deleted_pages,
        },
        stage="maintenance_pending",
        progress=90,
        affected_pages=affected_page_ids,
        maintenance={
            "status": "pending",
            "event": event,
            "affected_page_ids": affected_page_ids,
            "deleted_titles": deleted_titles,
            "prune_deleted_pages": prune_deleted_pages,
            "stages": {},
        },
        status="running",
        created_by=operator or "",
        updated_by=operator or "",
    )


def _run_page_lifecycle_maintenance(
    record,
    affected_page_ids,
    event,
    *,
    deleted_titles=None,
    prune_deleted_pages=False,
):
    affected_page_ids = list(dict.fromkeys(affected_page_ids or []))
    deleted_titles = list(dict.fromkeys(deleted_titles or []))
    error = ""
    try:
        result = cascade(
            record.knowledge_base,
            affected_page_ids,
            event,
            deleted_titles=deleted_titles,
            prune_deleted_pages=prune_deleted_pages,
        )
        if not isinstance(result, dict):
            raise TypeError("cascade must return a maintenance mapping")
        result = dict(result)
        result.setdefault("status", "success")
        result.setdefault("event", event)
        result.setdefault("affected_page_ids", affected_page_ids)
        result.setdefault("deleted_titles", deleted_titles)
        result.setdefault("prune_deleted_pages", prune_deleted_pages)
        result.setdefault("stages", {})
    except Exception as exc:
        error = humanize_maintenance_error(exc)
        result = {
            "status": "partial",
            "event": event,
            "affected_page_ids": affected_page_ids,
            "deleted_titles": deleted_titles,
            "prune_deleted_pages": prune_deleted_pages,
            "stages": {
                "cascade": {
                    "status": "failed",
                    "error": error,
                }
            },
        }
    record.maintenance = result
    record.status = "failed" if result.get("status") == "failed" else "partial" if result.get("status") == "partial" else "success"
    record.stage = "done"
    record.progress = 100
    record.errors = [error] if error else []
    record.save(
        update_fields=[
            "maintenance",
            "status",
            "stage",
            "progress",
            "errors",
            "updated_at",
        ]
    )
    return record


def _retry_rebuild_maintenance(record, maintenance, affected_page_ids, selected_stages):
    from apps.opspilot.services.wiki.rebuild_service import _combine_rebuild_maintenance

    archive_previous = maintenance.get("archive")
    if not isinstance(archive_previous, dict):
        return None
    archive_page_ids = list(archive_previous.get("affected_page_ids") or [])
    if not archive_page_ids:
        return None

    generated_previous = maintenance.get("generated")
    generated_previous = generated_previous if isinstance(generated_previous, dict) else {}
    generated_page_ids = list(generated_previous.get("affected_page_ids") or [])
    if not generated_page_ids:
        archive_set = set(archive_page_ids)
        generated_page_ids = [page_id for page_id in affected_page_ids if page_id not in archive_set]

    cascade_kwargs = {"stages": selected_stages} if selected_stages else {}
    archive_kwargs = dict(cascade_kwargs)
    deleted_titles = list(archive_previous.get("deleted_titles") or [])
    if deleted_titles:
        archive_kwargs["deleted_titles"] = deleted_titles
    archive_retry = cascade(
        record.knowledge_base,
        archive_page_ids,
        "page_delete",
        **archive_kwargs,
    )
    archive_result = _merge_selected_maintenance_retry(
        archive_previous,
        archive_retry,
        selected_stages,
    )
    generated_result = {}
    if generated_page_ids:
        generated_retry = cascade(
            record.knowledge_base,
            generated_page_ids,
            "maintenance_retry",
            **cascade_kwargs,
        )
        generated_result = _merge_selected_maintenance_retry(
            generated_previous,
            generated_retry,
            selected_stages,
        )
    return (
        _combine_rebuild_maintenance(
            archive_result,
            generated_result,
            archive_page_ids,
            generated_page_ids,
            event="maintenance_retry",
        ),
        list(dict.fromkeys([*archive_page_ids, *generated_page_ids])),
    )


def _retry_material_delete_maintenance(
    record,
    maintenance,
    affected_page_ids,
    selected_stages,
):
    from apps.opspilot.services.wiki.update_service import _combine_material_delete_maintenance

    invalidated_previous = maintenance.get("invalidated")
    shared_previous = maintenance.get("shared")
    if not isinstance(invalidated_previous, dict) and not isinstance(
        shared_previous,
        dict,
    ):
        return None

    inputs = record.inputs if isinstance(record.inputs, dict) else {}
    invalidated_previous = invalidated_previous if isinstance(invalidated_previous, dict) else {}
    shared_previous = shared_previous if isinstance(shared_previous, dict) else {}
    invalidated_page_ids = list(invalidated_previous.get("affected_page_ids") or inputs.get("invalidated_page_ids") or [])
    shared_page_ids = list(shared_previous.get("affected_page_ids") or inputs.get("shared_page_ids") or [])
    if not invalidated_page_ids and not shared_page_ids:
        return None

    cascade_kwargs = {"stages": selected_stages} if selected_stages else {}
    invalidated_result = {}
    if invalidated_page_ids:
        invalidated_retry = cascade(
            record.knowledge_base,
            invalidated_page_ids,
            "material_delete",
            **cascade_kwargs,
        )
        invalidated_result = _merge_selected_maintenance_retry(
            invalidated_previous,
            invalidated_retry,
            selected_stages,
        )
    shared_result = {}
    if shared_page_ids:
        shared_retry = cascade(
            record.knowledge_base,
            shared_page_ids,
            "maintenance_retry",
            **cascade_kwargs,
        )
        shared_result = _merge_selected_maintenance_retry(
            shared_previous,
            shared_retry,
            selected_stages,
        )
    combined_page_ids = list(dict.fromkeys([*invalidated_page_ids, *shared_page_ids]))
    return (
        _combine_material_delete_maintenance(
            invalidated_result,
            shared_result,
            invalidated_page_ids,
            shared_page_ids,
            event="maintenance_retry",
        ),
        combined_page_ids,
    )


def _merge_retry_with_latest(
    latest_maintenance,
    retry_maintenance,
    selected_stages,
    *,
    partitioned,
):
    if not partitioned:
        return _merge_selected_maintenance_retry(
            latest_maintenance,
            retry_maintenance,
            selected_stages,
        )
    if not selected_stages:
        return retry_maintenance

    merged = dict(latest_maintenance or {})
    for key, value in retry_maintenance.items():
        if key not in _PARTITIONED_MAINTENANCE_KEYS:
            merged[key] = value
    for key in _PARTITIONED_MAINTENANCE_KEYS:
        retry_partition = retry_maintenance.get(key)
        if not isinstance(retry_partition, dict):
            continue
        latest_partition = merged.get(key)
        latest_partition = latest_partition if isinstance(latest_partition, dict) else {}
        merged[key] = _merge_selected_maintenance_retry(
            latest_partition,
            retry_partition,
            selected_stages,
        )
    return merged


def _retry_build_record_maintenance(
    record,
    selected_stages=None,
    *,
    claim_token=None,
):
    maintenance = record.maintenance if isinstance(record.maintenance, dict) else {}
    affected_page_ids = list(maintenance.get("affected_page_ids") or record.affected_pages or [])
    if not affected_page_ids:
        return None

    previous_event = maintenance.get("event") or record.trigger
    partitioned_retry = _retry_material_delete_maintenance(
        record,
        maintenance,
        affected_page_ids,
        selected_stages,
    )
    if partitioned_retry is None:
        partitioned_retry = _retry_rebuild_maintenance(
            record,
            maintenance,
            affected_page_ids,
            selected_stages,
        )

    partitioned = partitioned_retry is not None
    if not partitioned:
        cascade_kwargs = {"stages": selected_stages} if selected_stages else {}
        retry_inputs = record.inputs if isinstance(record.inputs, dict) else {}
        deleted_titles = list(maintenance.get("deleted_titles") or retry_inputs.get("deleted_titles") or [])
        if deleted_titles:
            cascade_kwargs["deleted_titles"] = deleted_titles
        prune_deleted_pages = bool(maintenance.get("prune_deleted_pages") or retry_inputs.get("prune_deleted_pages"))
        if prune_deleted_pages:
            cascade_kwargs["prune_deleted_pages"] = True
        retry_event = "page_delete" if previous_event == "page_delete" else "maintenance_retry"
        retry_maintenance = cascade(
            record.knowledge_base,
            affected_page_ids,
            retry_event,
            **cascade_kwargs,
        )
    else:
        retry_maintenance, affected_page_ids = partitioned_retry

    def apply_result(target, latest_maintenance):
        merged_maintenance = _merge_retry_with_latest(
            latest_maintenance,
            retry_maintenance,
            selected_stages,
            partitioned=partitioned,
        )
        inputs = dict(target.inputs or {})
        if claim_token is not None:
            claim = inputs.get(_MAINTENANCE_RETRY_CLAIM_KEY)
            if not isinstance(claim, dict) or claim.get("token") != claim_token:
                raise MaintenanceRetryConflict("维护重试占用已失效，请重新发起")
            inputs.pop(_MAINTENANCE_RETRY_CLAIM_KEY, None)
        inputs["maintenance_retry_of"] = previous_event
        if selected_stages:
            inputs["maintenance_retry_stages"] = selected_stages
        else:
            inputs.pop("maintenance_retry_stages", None)
        target.inputs = inputs
        target.affected_pages = affected_page_ids
        target.maintenance = merged_maintenance
        target.errors = _maintenance_errors(merged_maintenance)
        target.status = merged_maintenance.get("status") or target.status
        target.stage = "done"
        target.progress = 100
        target.save(
            update_fields=[
                "inputs",
                "affected_pages",
                "maintenance",
                "errors",
                "status",
                "stage",
                "progress",
                "updated_at",
            ]
        )
        return target

    if claim_token is None:
        return apply_result(record, maintenance)

    with transaction.atomic():
        latest = BuildRecord.objects.select_for_update().select_related("knowledge_base").get(pk=record.pk)
        latest_maintenance = latest.maintenance if isinstance(latest.maintenance, dict) else {}
        return apply_result(latest, latest_maintenance)


def _run_claimed_maintenance_retry(record, selected_stages=None):
    claimed_record, token = _claim_maintenance_retry(record.pk)
    try:
        return _retry_build_record_maintenance(
            claimed_record,
            selected_stages,
            claim_token=token,
        )
    finally:
        _release_maintenance_retry_claim(record.pk, token)


class WikiPageViewSet(WikiTeamScopeMixin, AuthViewSet):
    """知识页面:浏览 + 人工创建/编辑/删除 + 版本查看/恢复(spec §8/§9)。"""

    queryset = KnowledgePage.objects.all().order_by("-id")
    serializer_class = KnowledgePageSerializer
    ordering = ("-id",)

    def _directory_scope(self, request):
        raw_directory_id = request.GET.get("directory_id")
        if raw_directory_id in (None, ""):
            return None, None
        try:
            directory_id = int(raw_directory_id)
        except (TypeError, ValueError):
            return None, JsonResponse(
                {"result": False, "message": "directory_id 必须为整数"},
                status=400,
            )

        directory = WikiDirectory.objects.filter(pk=directory_id).values("id", "knowledge_base_id").first()
        if directory is None:
            return None, JsonResponse(
                {"result": False, "message": "目录不存在"},
                status=400,
            )
        self.accessible_knowledge_base_or_none(directory["knowledge_base_id"])

        raw_knowledge_base_id = request.GET.get("knowledge_base")
        if raw_knowledge_base_id not in (None, ""):
            try:
                knowledge_base_id = int(raw_knowledge_base_id)
            except (TypeError, ValueError):
                return None, JsonResponse(
                    {"result": False, "message": "knowledge_base 必须为整数"},
                    status=400,
                )
            if knowledge_base_id != directory["knowledge_base_id"]:
                return None, JsonResponse(
                    {"result": False, "message": "目录不属于指定知识库"},
                    status=400,
                )

        include_descendants = str(request.GET.get("include_descendants", "")).lower() in {
            "1",
            "true",
            "yes",
        }
        if not include_descendants:
            return [directory_id], None

        children = defaultdict(list)
        for child_id, parent_id in WikiDirectory.objects.filter(
            knowledge_base_id=directory["knowledge_base_id"],
            status="active",
        ).values_list("id", "parent_id"):
            children[parent_id].append(child_id)

        directory_ids = {directory_id}
        pending = [directory_id]
        while pending:
            for child_id in children[pending.pop()]:
                if child_id in directory_ids:
                    continue
                directory_ids.add(child_id)
                pending.append(child_id)
        return directory_ids, None

    @HasPermission("wiki_list-View")
    def list(self, request, *args, **kwargs):
        knowledge_base = self.accessible_knowledge_base_or_none(request.GET.get("knowledge_base"))
        if knowledge_base is None:
            return JsonResponse(
                {"result": False, "message": "knowledge_base 必填或知识库不存在"},
                status=400,
            )
        directory_ids, directory_error = self._directory_scope(request)
        if directory_error:
            return directory_error
        page_type = (request.GET.get("page_type") or "").strip()
        title_filter = (request.GET.get("title") or request.GET.get("name") or "").strip()
        status_filter = (request.GET.get("status") or "").strip()
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            page_size = max(int(request.GET.get("page_size", 20)), 1)
        except (TypeError, ValueError):
            page, page_size = 1, 20
        try:
            queryset = page_queryset(
                knowledge_base,
                statuses=(status_filter,) if status_filter else ("active",),
                directory_ids=directory_ids,
                page_type=page_type,
                title=title_filter,
            ).order_by("-id")
            total = queryset.count()
            page_items = list(queryset[(page - 1) * page_size : (page - 1) * page_size + page_size])
            page_metadata = _page_list_metadata(page_items, knowledge_base)
            serializer = self.get_serializer(
                page_items,
                many=True,
                context={
                    **self.get_serializer_context(),
                    "index_failure_lookup": failed_index_stages_for_pages(page_items),
                    **page_metadata,
                },
            )
            data = serializer.data
        except ActiveGenerationReadError as error:
            return _active_generation_conflict(error)
        return JsonResponse({"result": True, "data": {"count": total, "items": data}})

    @HasPermission("wiki_list-View")
    def retrieve(self, request, *args, **kwargs):
        try:
            identity_page = self.get_object()
            page = get_object_or_404(
                page_queryset(
                    identity_page.knowledge_base,
                    statuses=("active",),
                ),
                pk=identity_page.pk,
            )
            page_metadata = _page_list_metadata([page], page.knowledge_base)
            serializer = self.get_serializer(
                page,
                context={
                    **self.get_serializer_context(),
                    "index_failure_lookup": failed_index_stages_for_pages([page]),
                    **page_metadata,
                },
            )
            data = serializer.data
        except ActiveGenerationReadError as error:
            return _active_generation_conflict(error)
        return JsonResponse({"result": True, "data": data})

    def _parse_ids(self, request):
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            return None, JsonResponse({"result": False, "message": "ids 不能为空"}, status=400)

        parsed_ids = []
        seen = set()
        for raw_id in ids:
            try:
                page_id = int(raw_id)
            except (TypeError, ValueError):
                return None, JsonResponse({"result": False, "message": "ids 必须为整数列表"}, status=400)
            if page_id not in seen:
                parsed_ids.append(page_id)
                seen.add(page_id)
        return parsed_ids, None

    def _parse_knowledge_base(self, request):
        raw_id = request.data.get("knowledge_base") or request.data.get("knowledge_base_id")
        try:
            kb_id = int(raw_id)
        except (TypeError, ValueError):
            return None, JsonResponse({"result": False, "message": "knowledge_base 必填"}, status=400)
        kb = self.accessible_knowledge_base_or_none(kb_id)
        if not kb:
            return None, JsonResponse({"result": False, "message": "知识库不存在"}, status=400)
        return kb, None

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=False)
    def move(self, request):
        """批量移动当前 active generation 中的页面，并切换为人工锁定。"""
        knowledge_base, error = self._parse_knowledge_base(request)
        if error:
            return error
        payload = request.data
        try:
            result = move_pages(
                knowledge_base,
                page_ids=payload.get("page_ids", payload.get("ids")),
                target_directory_id=payload.get("target_directory_id"),
                base_generation_id=payload.get("base_generation_id"),
                structure_version=payload.get("structure_version"),
                operator=getattr(request.user, "username", "") or "",
            )
        except DirectoryServiceError as service_error:
            return _directory_service_error(service_error)

        log_operation(
            request,
            "update",
            "opspilot",
            f"移动知识页面目录({result['changed']}项)",
        )
        return JsonResponse({"result": True, "data": result})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=False)
    def restore_auto(self, request):
        """批量解除人工锁定，并按当前结构确定性恢复自动归类。"""
        knowledge_base, error = self._parse_knowledge_base(request)
        if error:
            return error
        payload = request.data
        try:
            result = restore_pages_auto(
                knowledge_base,
                page_ids=payload.get("page_ids", payload.get("ids")),
                base_generation_id=payload.get("base_generation_id"),
                structure_version=payload.get("structure_version"),
                operator=getattr(request.user, "username", "") or "",
            )
        except DirectoryServiceError as service_error:
            return _directory_service_error(service_error)

        log_operation(
            request,
            "update",
            "opspilot",
            f"恢复知识页面自动归类({result['changed']}项)",
        )
        return JsonResponse({"result": True, "data": result})

    @HasPermission("wiki_list-Edit")
    def create(self, request, *args, **kwargs):
        data = request.data
        kb, error = self._parse_knowledge_base(request)
        if error:
            return error
        try:
            page = create_manual_page(
                knowledge_base=kb,
                page_type=data.get("page_type", "concept"),
                title=data["title"],
                body=data.get("body", ""),
                tags=data.get("tags") or [],
                created_by=getattr(request.user, "username", ""),
                directory_id=data.get("directory_id"),
            )
        except PageServiceError as service_error:
            return _directory_service_error(service_error)
        cascade(kb, [page.id], "page_create")
        log_operation(request, "create", "opspilot", f"新增知识页面: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data}, status=201)

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=False)
    def save_answer(self, request):
        """将 QA/Bot 对话回答保存为知识页面,并保留来源对话元数据。"""
        kb, error = self._parse_knowledge_base(request)
        if error:
            return error
        data = request.data
        required_fields = [
            ("page_type", "page_type 必填"),
            ("title", "title 必填"),
            ("body", "body 必填"),
            ("source_conversation_id", "source_conversation_id 必填"),
        ]
        for field, message in required_fields:
            if not str(data.get(field) or "").strip():
                return JsonResponse({"result": False, "message": message}, status=400)

        try:
            page = save_answer_page(
                knowledge_base=kb,
                page_type=data["page_type"],
                title=data["title"],
                body=data.get("body", ""),
                tags=data.get("tags") or [],
                source_conversation_id=data["source_conversation_id"],
                source_message_id=data.get("source_message_id", ""),
                source_channel=data.get("source_channel", "qa"),
                created_by=getattr(request.user, "username", ""),
            )
        except PageServiceError as service_error:
            return _directory_service_error(service_error)
        cascade(kb, [page.id], "qa_answer_save")
        log_operation(request, "create", "opspilot", f"保存问答为知识页面: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data}, status=201)

    @HasPermission("wiki_list-Edit")
    def update(self, request, *args, **kwargs):
        page = self.get_object()
        if page.status == "archived":
            return JsonResponse({"result": False, "message": "已归档知识页面不可编辑,请先恢复"}, status=400)
        old_title = page.title
        try:
            edit_page(
                page,
                body=request.data.get("body"),
                title=request.data.get("title"),
                tags=request.data.get("tags"),
                page_type=request.data.get("page_type"),
                updated_by=getattr(request.user, "username", ""),
            )
        except PageServiceError as service_error:
            return _directory_service_error(service_error)
        page.refresh_from_db()
        deleted_titles = [old_title] if old_title != page.title else None
        cascade(page.knowledge_base, [page.id], "page_update", deleted_titles=deleted_titles)
        log_operation(request, "update", "opspilot", f"编辑知识页面: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data})

    @HasPermission("wiki_list-Edit")
    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @HasPermission("wiki_list-Edit")
    def destroy(self, request, *args, **kwargs):
        page = self.get_object()
        try:
            result = _archive_pages_by_write_route(
                page.knowledge_base,
                page_ids=[page.pk],
                base_generation_id=request.query_params.get("base_generation_id"),
                structure_version=request.query_params.get("structure_version"),
                operator=(getattr(request.user, "username", "") or ""),
            )
        except DirectoryServiceError as service_error:
            return _directory_service_error(service_error)
        log_operation(
            request,
            "delete",
            "opspilot",
            f"归档知识页面: {page.title}",
        )
        return JsonResponse({"result": True, "data": result})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=False)
    def batch_delete(self, request):
        """通过轻量 governance generation 批量逻辑归档页面。"""
        ids, error = self._parse_ids(request)
        if error:
            return error
        self.ensure_team_accessible_ids(
            KnowledgePage.objects.all(),
            ids,
        )
        knowledge_base, error = self._parse_knowledge_base(request)
        if error:
            return error
        try:
            result = _archive_pages_by_write_route(
                knowledge_base,
                page_ids=ids,
                base_generation_id=request.data.get("base_generation_id"),
                structure_version=request.data.get("structure_version"),
                operator=(getattr(request.user, "username", "") or ""),
            )
        except DirectoryServiceError as service_error:
            return _directory_service_error(service_error)
        log_operation(
            request,
            "delete",
            "opspilot",
            f"批量归档知识页面({result['changed']}项)",
        )
        response_data = {
            **result,
            "deleted": result["changed"],
        }
        return JsonResponse({"result": True, "data": response_data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def reindex(self, request, pk=None):
        """重建单个知识页面的页面级和 chunk 级索引,并落构建记录供诊断/重试追踪。"""
        page = self.get_object()
        kb = page.knowledge_base
        if page.status != "active":
            return JsonResponse({"result": False, "message": "只有启用中的知识页面可以重建索引"}, status=400)
        if not kb.embed_provider_id:
            return JsonResponse({"result": False, "message": "知识库未配置向量模型,无法重建索引"}, status=400)
        if not page.current_version_id:
            return JsonResponse({"result": False, "message": "知识页面无当前版本,无法重建索引"}, status=400)

        operator = getattr(request.user, "username", "")
        build = rebuild_page_indexes(
            kb,
            [page],
            trigger="page_reindex",
            event="page_reindex",
            operator=operator,
            inputs={"page_id": page.id, "page_title": page.title},
            index_fn=index_version,
            chunk_index_fn=reindex_page_chunks,
        )
        log_operation(request, "execute", "opspilot", f"重建知识页面索引: {page.title}")
        return JsonResponse({"result": True, "data": BuildRecordSerializer(build).data})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def sources(self, request, pk=None):
        """查看知识页面的资料来源和片段定位。"""
        page = self.get_object()
        evidences = PageEvidence.objects.filter(page=page).select_related("material", "material_version").order_by("id")
        sources = [_evidence_source_payload(evidence) for evidence in evidences]
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "page_id": page.id,
                    "page_title": page.title,
                    "sources": sources,
                },
            }
        )

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def versions(self, request, pk=None):
        """列出该页面的全部版本(用于 diff/恢复)。"""
        page = self.get_object()
        qs = page.page_versions.order_by("-no")
        return JsonResponse({"result": True, "data": PageVersionSerializer(qs, many=True).data})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def diff(self, request, pk=None):
        """对比两个版本正文,返回统一 diff 行(?from=<版本id>&to=<版本id>)。"""
        page = self.get_object()
        try:
            from_id = int(request.GET.get("from"))
            to_id = int(request.GET.get("to"))
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "from/to 版本 id 必填"}, status=400)
        try:
            lines = diff_versions(page, from_id, to_id)
        except ValueError:
            return JsonResponse({"result": False, "message": "版本不存在"}, status=404)
        return JsonResponse({"result": True, "data": {"diff": lines}})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def restore(self, request, pk=None):
        """恢复到指定历史版本(创建新版本,不删除历史)。"""
        page = self.get_object()
        if page.status == "archived":
            return JsonResponse({"result": False, "message": "已归档知识页面不可恢复版本,请先恢复归档"}, status=400)
        version_id = request.data.get("version_id")
        if not version_id:
            return JsonResponse({"result": False, "message": "version_id 必填"}, status=400)
        try:
            restore_version(page, version_id, operator=getattr(request.user, "username", ""))
        except PageServiceError as service_error:
            return _directory_service_error(service_error)
        page.refresh_from_db()
        cascade(page.knowledge_base, [page.id], "restore")
        log_operation(request, "execute", "opspilot", f"恢复知识页面版本: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def restore_from_archive(self, request, pk=None):
        """通过 generation 发布恢复归档页面。"""
        page = self.get_object()
        try:
            result = _restore_archived_pages_by_write_route(
                page.knowledge_base,
                page_ids=[page.pk],
                base_generation_id=request.data.get("base_generation_id"),
                structure_version=request.data.get("structure_version"),
                operator=(getattr(request.user, "username", "") or ""),
            )
        except DirectoryServiceError as service_error:
            return _directory_service_error(service_error)
        page.refresh_from_db()
        log_operation(
            request,
            "execute",
            "opspilot",
            f"恢复归档知识页面: {page.title}",
        )
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "page": self.get_serializer(page).data,
                    "generation": result,
                },
            }
        )


class WikiBuildRecordViewSet(WikiTeamScopeMixin, AuthViewSet):
    """构建记录:浏览 + 重试/继续/取消(spec 4.4)。"""

    queryset = BuildRecord.objects.all().order_by("-id")
    serializer_class = BuildRecordSerializer
    ordering = ("-id",)
    http_method_names = ["get", "head", "options", "post"]

    @HasPermission("wiki_list-View")
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        # 队列租约/排队项是调度书签，不是用户可读的构建历史
        queryset = queryset.exclude(trigger__in=(QUEUE_ITEM_TRIGGER, RUNNER_TRIGGER))
        kb_id = request.GET.get("knowledge_base")
        if kb_id:
            try:
                reconcile_orphaned_material_builds(int(kb_id))
                repair_queue_runner_status_from_counts(int(kb_id))
            except (TypeError, ValueError):
                pass
            except Exception:  # noqa: BLE001 - 孤儿清理失败不阻断列表
                logger.exception("wiki build_record list reconcile failed kb=%s", kb_id)
            queryset = queryset.filter(knowledge_base_id=kb_id)
        status_filter = request.GET.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        trigger_filter = request.GET.get("trigger")
        if trigger_filter:
            queryset = queryset.filter(trigger=trigger_filter)
        material_name_filter = (request.GET.get("material_name") or "").strip()
        if material_name_filter and kb_id:
            try:
                queryset = _filter_build_records_by_material_name(
                    queryset,
                    knowledge_base_id=int(kb_id),
                    material_name=material_name_filter,
                )
            except (TypeError, ValueError):
                pass
        maintenance_status_filter = request.GET.get("maintenance_status")
        maintenance_stage_filter = request.GET.get("maintenance_stage")
        maintenance_stage_status_filter = request.GET.get("maintenance_stage_status")
        if maintenance_stage_filter and maintenance_stage_filter not in MAINTENANCE_STAGE_KEYS:
            return JsonResponse({"result": False, "message": f"不支持的维护阶段: {maintenance_stage_filter}"}, status=400)
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            page_size = max(int(request.GET.get("page_size", 20)), 1)
        except (TypeError, ValueError):
            page, page_size = 1, 20
        if any([maintenance_status_filter, maintenance_stage_filter, maintenance_stage_status_filter]):
            filtered_items = _filter_build_records_by_maintenance(
                list(queryset),
                maintenance_status_filter,
                maintenance_stage_filter,
                maintenance_stage_status_filter,
            )
            total = len(filtered_items)
            page_items = filtered_items[(page - 1) * page_size : (page - 1) * page_size + page_size]
        else:
            total = queryset.count()
            page_items = queryset[(page - 1) * page_size : (page - 1) * page_size + page_size]
        return JsonResponse({"result": True, "data": {"count": total, "items": self.get_serializer(page_items, many=True).data}})

    @HasPermission("wiki_list-View")
    def retrieve(self, request, *args, **kwargs):
        return JsonResponse({"result": True, "data": self.get_serializer(self.get_object()).data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def retry(self, request, pk=None):
        """按当前治理快照安全重试原构建入口。"""
        record = self.get_object()
        operator = getattr(request.user, "username", "")
        if record.trigger in {"decision", "material_delete"}:
            return JsonResponse(
                {
                    "result": False,
                    "message": "该记录只能通过 retry_maintenance 重试维护",
                },
                status=400,
            )
        if record.trigger not in {"rebuild", "material", "material_update"}:
            return JsonResponse(
                {
                    "result": False,
                    "message": "该构建类型不支持从此入口重试",
                    "code": "build_retry_trigger_unsupported",
                },
                status=400,
            )

        try:
            enqueue_retry_material = None
            with transaction.atomic():
                knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=record.knowledge_base_id)
                record = BuildRecord.objects.select_for_update().select_related("knowledge_base").get(pk=record.pk, knowledge_base=knowledge_base)
                if record.status == "running":
                    raise DirectoryServiceError(
                        "build_retry_in_progress",
                        "该构建记录正在运行，不能重复重试",
                        status_code=409,
                        retryable=True,
                    )
                if record.trigger in {"rebuild", "material_update"} and kb_has_user_build_in_progress(knowledge_base.pk, exclude_build_id=record.pk):
                    raise DirectoryServiceError(
                        "knowledge_base_build_in_progress",
                        "知识库存在运行中的构建任务，请等待完成后再重试",
                        status_code=409,
                        retryable=True,
                    )
                release_idle_runner_lease(knowledge_base.pk, operator=operator, kick_if_queued=False)

                task_identity = None
                if record.trigger == "rebuild":
                    materials = list(Material.objects.select_for_update().filter(knowledge_base=knowledge_base).order_by("id"))
                    task_identity = _opspilot_tasks._freeze_wiki_task_identity(
                        knowledge_base,
                        materials,
                    )
                    record.status = "running"
                    record.stage = "queued"
                    record.progress = 0
                    record.errors = []
                    record.activation = {}
                    record.save(
                        update_fields=[
                            "status",
                            "stage",
                            "progress",
                            "errors",
                            "activation",
                            "updated_at",
                        ]
                    )
                    _opspilot_tasks._persist_wiki_task_identity(
                        record,
                        task_identity,
                    )
                    task = _opspilot_tasks.wiki_rebuild_kb_task
                    task_args = (
                        knowledge_base.pk,
                        knowledge_base.llm_model_id,
                        operator,
                        record.pk,
                        None,
                        task_identity,
                    )
                else:
                    material_id = (record.inputs or {}).get("material_id")
                    # 可空 FK 不能和 FOR UPDATE 一起 select_related，PostgreSQL 会拒绝外连接空值边。
                    material = (
                        Material.objects.select_for_update()
                        .filter(
                            pk=material_id,
                            knowledge_base=knowledge_base,
                        )
                        .first()
                        if material_id
                        else None
                    )
                    if material is None:
                        raise DirectoryServiceError(
                            "retry_material_missing",
                            "原资料不存在,无法重试",
                            status_code=400,
                        )
                    classification_root_id = (record.inputs or {}).get("classification_root_id")
                    if classification_root_id in (None, ""):
                        classification_root_id = material.classification_root_id
                    if record.trigger == "material_update":
                        task_identity = _opspilot_tasks._freeze_wiki_task_identity(
                            knowledge_base,
                            [material],
                            classification_root_id=classification_root_id,
                        )
                        task = _opspilot_tasks.wiki_propose_update_task
                        task_args = (
                            material.pk,
                            knowledge_base.llm_model_id,
                            operator,
                            classification_root_id,
                            task_identity,
                        )
                    else:
                        enqueue_retry_material = material
                        task = None
                        task_args = None
        except DirectoryServiceError as service_error:
            return _directory_service_error(service_error)
        except BuildGenerationError as error:
            return _build_generation_error(error)

        if enqueue_retry_material is not None:
            unstick_material_for_cancelled_build(record)
            try:
                queue_result = enqueue_material_builds(
                    knowledge_base_id=record.knowledge_base_id,
                    material_ids=[enqueue_retry_material.pk],
                    operator=operator,
                )
            except MaterialBuildQueueError as error:
                return JsonResponse(
                    {
                        "result": False,
                        "code": error.code,
                        "message": error.message,
                        "details": error.details,
                        "retryable": error.status_code >= 500,
                    },
                    status=error.status_code,
                )
            except Exception:  # noqa: BLE001 - traceback 由 kick 持有
                return JsonResponse(
                    {
                        "result": False,
                        "message": "构建任务下发失败，请重试",
                        "code": "task_dispatch_failed",
                        "retryable": True,
                    },
                    status=503,
                )
            if enqueue_retry_material.pk in (queue_result.get("in_progress") or []):
                return JsonResponse(
                    {
                        "result": False,
                        "code": "material_build_in_progress",
                        "message": "资料正在构建中，请勿重复提交",
                        "retryable": True,
                    },
                    status=409,
                )
            return JsonResponse({"result": True, "data": {"async": True, "queue": queue_result}})

        try:
            task.delay(*task_args)
        except Exception as error:
            if record.trigger == "rebuild":
                with transaction.atomic():
                    WikiKnowledgeBase.objects.select_for_update().get(pk=record.knowledge_base_id)
                    failed = BuildRecord.objects.select_for_update().get(pk=record.pk)
                    if failed.status == "running" and failed.stage == "queued":
                        _opspilot_tasks._fail_wiki_task_build(
                            failed,
                            "task_dispatch_failed",
                            str(error),
                            retryable=True,
                        )
            return JsonResponse(
                {
                    "result": False,
                    "message": "构建任务下发失败，请重试",
                    "code": "task_dispatch_failed",
                    "retryable": True,
                },
                status=503,
            )
        return JsonResponse({"result": True, "data": {"async": True}})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def retry_maintenance(self, request, pk=None):
        """重试构建记录的级联维护:关系、索引和检查清扫按受影响页面增量重跑。"""
        record = self.get_object()
        selected_stages, error = _parse_maintenance_retry_stages(request)
        if error:
            return error

        try:
            record = _run_claimed_maintenance_retry(record, selected_stages)
        except MaintenanceRetryConflict as exc:
            return JsonResponse(
                {"result": False, "message": str(exc)},
                status=409,
            )
        if not record:
            return JsonResponse(
                {"result": False, "message": "该构建记录没有受影响页面,无法重试维护"},
                status=400,
            )
        log_operation(request, "execute", "opspilot", f"重试构建记录维护: #{record.id}")
        return JsonResponse({"result": True, "data": self.get_serializer(record).data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=False)
    def batch_retry_maintenance(self, request):
        """批量重试选中构建记录的级联维护,用于处理筛选出的失败阶段。"""
        raw_ids = request.data.get("ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            return JsonResponse({"result": False, "message": "ids 不能为空"}, status=400)
        record_ids = []
        seen = set()
        for raw_id in raw_ids:
            try:
                record_id = int(raw_id)
            except (TypeError, ValueError):
                return JsonResponse({"result": False, "message": "ids 必须为整数列表"}, status=400)
            if record_id not in seen:
                record_ids.append(record_id)
                seen.add(record_id)
        selected_stages, error = _parse_maintenance_retry_stages(request)
        if error:
            return error
        self.ensure_team_accessible_ids(BuildRecord.objects.all(), record_ids)
        try:
            kb_id = int(request.data.get("knowledge_base") or request.data.get("knowledge_base_id"))
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "knowledge_base 必填"}, status=400)
        kb = self.accessible_knowledge_base_or_none(kb_id)
        if not kb:
            return JsonResponse({"result": False, "message": "知识库不存在"}, status=400)

        records = self.get_queryset().filter(knowledge_base=kb, id__in=record_ids)
        record_map = {record.id: record for record in records}
        retried_records = []
        skipped_ids = []
        for record_id in record_ids:
            record = record_map.get(record_id)
            if not record:
                skipped_ids.append(record_id)
                continue
            try:
                retried_record = _run_claimed_maintenance_retry(
                    record,
                    selected_stages,
                )
            except MaintenanceRetryConflict:
                skipped_ids.append(record.id)
                continue
            if not retried_record:
                skipped_ids.append(record.id)
                continue
            retried_records.append(retried_record)
        log_operation(request, "execute", "opspilot", f"批量重试构建记录维护({len(retried_records)}项)")
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "retried": len(retried_records),
                    "skipped": len(skipped_ids),
                    "skipped_ids": skipped_ids,
                    "items": self.get_serializer(retried_records, many=True).data,
                },
            }
        )

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def cancel(self, request, pk=None):
        """取消:运行中的构建记录置 cancelled，并解开对应资料的构建中状态。"""
        record = self.get_object()
        if record.status == "running":
            with transaction.atomic():
                record = BuildRecord.objects.select_for_update().get(pk=record.pk)
                if record.status == "running":
                    record.status = "cancelled"
                    record.stage = "cancelled"
                    record.save(update_fields=["status", "stage", "updated_at"])
                    unstick_material_for_cancelled_build(record)
                    release_idle_runner_lease(
                        record.knowledge_base_id,
                        operator=getattr(request.user, "username", "") or "",
                    )
        return JsonResponse({"result": True, "data": self.get_serializer(record).data})
