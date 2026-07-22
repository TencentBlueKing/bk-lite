"""安全更新 + 检查/审核（`specs/changes/streamline-wiki-knowledge-decisions/spec.md` phase 3）。

风险变更不污染当前有效版本:生成候选版本(PageVersion change_type=candidate, is_current=False)+ CheckItem。
phase 3: 决策中心 API `decide_check` 取代通用 accept/reject,
按 check_type 路由到知识冲突 3 选 1(keep_current/use_new/edit_accept)或
页面合并 2 选 1(keep_separate/merge),所有动作写入 WikiDecisionRule。
也提供系统检查扫描:孤立页面、缺来源等(MVP 子集)。
"""

import hashlib
import logging
from collections import Counter, defaultdict
from itertools import combinations

from django.db import transaction
from django.utils import timezone

from apps.opspilot.models import (
    BuildRecord,
    CheckItem,
    KnowledgePage,
    Material,
    MaterialVersion,
    PageEvidence,
    PageRelation,
    PageVersion,
    WikiKnowledgeBase,
)
from apps.opspilot.services.wiki.cascade_service import cascade
from apps.opspilot.services.wiki.decision_service import (
    POLICY_VERSION,
    build_page_identity_snapshot,
    build_participants_from_page_evidence,
    compute_decision_signature,
    compute_schema_fingerprint,
    create_rule_if_eligible,
    find_active_rule,
    is_participant_complete,
    mark_replayed,
    page_identity_context_stale_reason,
    subject_key_for_page,
)
from apps.opspilot.services.wiki.embedding_service import clear_page_vectors
from apps.opspilot.services.wiki.graph_service import analyze_graph
from apps.opspilot.services.wiki.relation_service import LINK_RE, normalize_wikilink_key
from apps.opspilot.services.wiki.title_service import canonical_title, compact_title_key

# phase 3.1: 各 decision_type 允许的动作集合
_KNOWLEDGE_CONFLICT_ACTIONS = {"keep_current", "use_new", "edit_accept"}
_PAGE_IDENTITY_ACTIONS = {"keep_separate", "merge"}
_DECISION_TYPE_BY_CHECK_TYPE = {
    "cannot_merge": "knowledge_conflict",
    "material_update": "knowledge_conflict",
    "duplicate": "page_identity",
    "conflict": "page_identity",
}
_CHECK_TYPES_BY_DECISION_TYPE = {
    decision_type: tuple(key for key, value in _DECISION_TYPE_BY_CHECK_TYPE.items() if value == decision_type)
    for decision_type in {"knowledge_conflict", "page_identity"}
}


def _participant_counter(participants):
    return Counter(
        (
            item.get("material_id"),
            (item.get("content_hash") or "").strip(),
        )
        for item in participants or []
        if isinstance(item, dict)
    )


def _diagnostic_identity(check_type, related, *, source_page_id=None):
    related = related if isinstance(related, dict) else {}
    target_key = (related.get("target_key") or "").strip()
    if not target_key:
        target_key = normalize_wikilink_key(related.get("target") or "")
    if target_key:
        return (check_type, source_page_id, "target", target_key)

    relation_id = related.get("relation_id") or related.get("relation")
    if relation_id not in (None, ""):
        return (check_type, source_page_id, "relation", str(relation_id))

    page_ids = []
    for page_id in related.get("pages", []) or []:
        if isinstance(page_id, bool):
            continue
        try:
            page_ids.append(int(page_id))
        except (TypeError, ValueError):
            continue
    return (
        check_type,
        source_page_id,
        related.get("graph_insight") or "",
        tuple(sorted(set(page_ids))),
    )


def _find_diagnostic(
    knowledge_base,
    check_type,
    related,
    *,
    source_page_id=None,
):
    identity = _diagnostic_identity(
        check_type,
        related,
        source_page_id=source_page_id,
    )
    candidates = CheckItem.objects.filter(
        knowledge_base=knowledge_base,
        check_type=check_type,
    ).order_by("id")
    for candidate in candidates:
        if (
            _diagnostic_identity(
                check_type,
                candidate.related,
                source_page_id=source_page_id,
            )
            == identity
        ):
            return candidate
    return None


DECISION_CHECK_TYPES = frozenset(_DECISION_TYPE_BY_CHECK_TYPE)


def _automatic_diagnostic_related(related):
    """把健康/图谱发现记录为只读审计结果，而不是用户待决策。"""
    value = dict(related) if isinstance(related, dict) else {}
    value["resolution"] = {
        "action": "automatic_maintenance",
        "operator": "system",
        "processed_at": timezone.now().isoformat(),
    }
    return value


def _close_diagnostic(check, related=None):
    check.status = "auto_resolved"
    check.suggested_actions = []
    check.related = _automatic_diagnostic_related(check.related if related is None else related)
    check.updated_by = "system"
    check.save(update_fields=["status", "suggested_actions", "related", "updated_by", "updated_at"])


def _auto_resolve_invalid_decision(check, original_check, detail, reason):
    """持久化关闭已经无法安全执行的旧决策；正常返回以提交当前原子事务。"""
    related = dict(check.related) if isinstance(check.related, dict) else {}
    related["resolution"] = {
        "action": "automatic_maintenance",
        "reason": reason,
        "detail": str(detail),
        "operator": "system",
        "processed_at": timezone.now().isoformat(),
    }
    check.related = related
    check.status = "auto_resolved"
    check.suggested_actions = []
    check.updated_by = "system"
    check.save(
        update_fields=[
            "related",
            "status",
            "suggested_actions",
            "updated_by",
            "updated_at",
        ]
    )
    _recount_pending_review(check)
    original_check.related = check.related
    original_check.status = check.status
    original_check.suggested_actions = []
    original_check.updated_by = check.updated_by
    return None


def _auto_resolve_stale_decision(check, original_check, detail):
    return _auto_resolve_invalid_decision(
        check,
        original_check,
        detail,
        "decision_context_stale",
    )


def _auto_resolve_incomplete_decision(check, original_check, detail):
    return _auto_resolve_invalid_decision(
        check,
        original_check,
        detail,
        "decision_context_incomplete",
    )


# phase 3.4: 锁当前版本的键(供测试断言)
_LOCK_KEY = "locked_current_version_id"


def _has_frozen_page_identity_context(check):
    context = check.decision_context if isinstance(check.decision_context, dict) else {}
    return bool(
        check.decision_key
        and context.get("decision_type") == "page_identity"
        and context.get("subject_key")
        and context.get("schema_fingerprint")
        and isinstance(context.get("page_identities"), list)
        and len(context["page_identities"]) == 2
        and isinstance(context.get("target_identity"), dict)
        and context["target_identity"]
    )


def _has_frozen_knowledge_conflict_context(check):
    context = check.decision_context if isinstance(check.decision_context, dict) else {}
    participants = context.get("participants")
    incoming = context.get("incoming")
    page_identity = context.get("page_identity")
    if not isinstance(participants, list) or not is_participant_complete(participants):
        return False
    if not isinstance(incoming, dict) or not isinstance(page_identity, dict):
        return False
    incoming_pair = (
        incoming.get("material_id"),
        (incoming.get("content_hash") or "").strip(),
    )
    participant_pairs = {
        (participant.get("material_id"), (participant.get("content_hash") or "").strip())
        for participant in participants
        if isinstance(participant, dict)
    }
    return bool(
        check.decision_key
        and check.candidate_version_id
        and context.get("decision_type") == "knowledge_conflict"
        and context.get("subject_key")
        and context.get("schema_fingerprint")
        and context.get(_LOCK_KEY) not in (None, "")
        and context.get("candidate_version_id") not in (None, "")
        and context.get("current_body_hash")
        and context.get("candidate_body_hash")
        and page_identity.get("page_id") not in (None, "")
        and incoming_pair[0] not in (None, "")
        and incoming_pair[1]
        and incoming_pair in participant_pairs
    )


def _has_complete_frozen_decision_context(check):
    decision_type = _DECISION_TYPE_BY_CHECK_TYPE.get(check.check_type)
    if decision_type == "knowledge_conflict":
        return _has_frozen_knowledge_conflict_context(check)
    if decision_type == "page_identity":
        return _has_frozen_page_identity_context(check)
    return False


@transaction.atomic
def close_incomplete_open_decision(check):
    """在展示前收口无法安全执行的 open 决策，返回是否发生关闭。"""
    original_check = check
    locked_kb = WikiKnowledgeBase.objects.select_for_update().get(
        pk=check.knowledge_base_id,
    )
    check = CheckItem.objects.select_for_update().get(
        pk=check.pk,
        knowledge_base=locked_kb,
    )
    check.knowledge_base = locked_kb
    if check.status != "open" or check.check_type not in DECISION_CHECK_TYPES:
        return False
    if _has_complete_frozen_decision_context(check):
        return False
    _auto_resolve_incomplete_decision(
        check,
        original_check,
        "审批缺少完整冻结上下文",
    )
    return True


def _recount_pending_review(check):
    """回算涉及该 check 的 BuildRecord.counts['pending_review'] 字段(Issue #待审批 25 飘)。

    BuildRecord.counts 是构建时的快照,后续接受/拒绝/resolve 检查时只改
    CheckItem.status,从不回写 counts,导致 BuildRecordTab 列表展示的 pending_review
    数字永远是构建时的值,与 CheckTab 实际剩余待审批不一致。

    来源:
      - check 有 candidate_version → 直接用它.build_record_id 定位 build(精确)
      - check 无 candidate_version(resolve_check 场景,如孤立页/缺来源扫描项)→
        回算 knowledge_base 下所有 build(这些检查项不绑定 build,但展示给用户
        的数字应一致;实际 KB 下的 build 数量有限,重算成本可忽略)

    save_fields 只动 counts + updated_at,避免触发 build_record 上其他字段的副作用。
    """
    if check.candidate_version_id and getattr(check.candidate_version, "build_record_id", None):
        build_ids = [check.candidate_version.build_record_id]
    else:
        build_ids = list(BuildRecord.objects.filter(knowledge_base=check.knowledge_base).values_list("id", flat=True))

    for bid in build_ids:
        build = BuildRecord.objects.filter(id=bid).first()
        if not build:
            continue
        # 仅数"通过 candidate_version 关联到此 build 且状态 open"的 CheckItem。
        # 系统扫描产生的检查(无 candidate_version)不在此计数中——它们本身没有 build 归属,
        # 但因方案 A' fallback 重算后,会反映到 KB 下所有 build 的 pending_review 里,
        # 这是当前 build.counts 数据模型能给出的最接近真实值。
        open_count = CheckItem.objects.filter(
            status="open",
            candidate_version__build_record=build,
        ).count()
        counts = dict(build.counts or {})
        if counts.get("pending_review") == open_count:
            continue
        counts["pending_review"] = open_count
        build.counts = counts
        build.save(update_fields=["counts", "updated_at"])


logger = logging.getLogger("opspilot")


def _log_maintenance_callback_exception(message, *args):
    try:
        logger.exception(message, *args)
    except Exception:
        pass


def _freeze_decision_audit(check, *, decision_type, action, operator, rule):
    processed_at = timezone.now().isoformat()
    related = dict(check.related) if isinstance(check.related, dict) else {}
    related["resolution"] = {
        "action": action,
        "operator": operator or "",
        "processed_at": processed_at,
        "decision_type": decision_type,
        "rule_id": getattr(rule, "id", None),
        "rule_status": getattr(rule, "status", ""),
    }
    if rule is None:
        related.pop("rule_snapshot", None)
    else:
        result_snapshot = dict(rule.result_snapshot) if isinstance(rule.result_snapshot, dict) else {}
        related["rule_snapshot"] = {
            "id": rule.id,
            "decision_type": rule.decision_type,
            "decision_key": rule.decision_key,
            "status": rule.status,
            "action": rule.action,
            "operator": operator or "",
            "processed_at": processed_at,
            "match_snapshot": (dict(rule.match_snapshot) if isinstance(rule.match_snapshot, dict) else {}),
            "result_snapshot": result_snapshot,
            "replay_count": rule.replay_count,
            "last_replayed_at": (rule.last_replayed_at.isoformat() if rule.last_replayed_at else None),
            "revoked_reason": result_snapshot.get("revoked_reason") or "",
            "revoked_by": result_snapshot.get("revoked_by") or "",
            "revoked_at": result_snapshot.get("revoked_at") or "",
        }
    check.related = related
    check.save(update_fields=["related", "updated_at"])


def _schedule_check_maintenance(
    check,
    affected_page_ids,
    event,
    *,
    operator="",
    deleted_titles=None,
    source_build_record_id=None,
):
    """Persist a retryable maintenance job and run external cascade only after commit."""
    affected_page_ids = list(dict.fromkeys(affected_page_ids or []))
    deleted_titles = list(dict.fromkeys(deleted_titles or []))
    inputs = {
        "decision_check_id": check.id,
        "maintenance_event": event,
    }
    if source_build_record_id:
        inputs["source_build_record_id"] = source_build_record_id
    pending_maintenance = {
        "status": "pending",
        "event": event,
        "affected_page_ids": affected_page_ids,
        "stages": {},
    }
    record = BuildRecord.objects.create(
        knowledge_base=check.knowledge_base,
        trigger="decision",
        operator=operator or "",
        inputs=inputs,
        stage="maintenance_pending",
        progress=90,
        affected_pages=affected_page_ids,
        maintenance=pending_maintenance,
        status="running",
        created_by=operator or "",
        updated_by=operator or "",
    )
    related = dict(check.related) if isinstance(check.related, dict) else {}
    related["maintenance"] = {
        "build_record_id": record.id,
        "status": "pending",
    }
    check.related = related
    check.save(update_fields=["related", "updated_at"])

    record_id = record.id
    check_id = check.id
    knowledge_base_id = check.knowledge_base_id

    def run_maintenance():
        try:
            callback_error = ""
            try:
                decision_record = BuildRecord.objects.select_related("knowledge_base").get(
                    pk=record_id,
                    knowledge_base_id=knowledge_base_id,
                )
                cascade_kwargs = {}
                if deleted_titles:
                    cascade_kwargs["deleted_titles"] = deleted_titles
                result = cascade(
                    decision_record.knowledge_base,
                    affected_page_ids,
                    event,
                    **cascade_kwargs,
                )
                if not isinstance(result, dict):
                    raise TypeError("cascade must return a maintenance mapping")
                result = dict(result)
            except Exception as exc:
                callback_error = str(exc)
                result = {
                    "status": "partial",
                    "event": event,
                    "affected_page_ids": affected_page_ids,
                    "stages": {
                        "cascade": {
                            "status": "failed",
                            "error": callback_error,
                        }
                    },
                }
                _log_maintenance_callback_exception(
                    "wiki decision maintenance cascade failed check=%s record=%s",
                    check_id,
                    record_id,
                )

            final_status = (
                "failed" if callback_error or result.get("status") == "failed" else "partial" if result.get("status") == "partial" else "success"
            )
            persisted = False
            try:
                decision_record = BuildRecord.objects.get(pk=record_id)
                decision_record.maintenance = result
                decision_record.status = final_status
                decision_record.stage = "done"
                decision_record.progress = 100
                decision_record.errors = [callback_error] if callback_error else []
                decision_record.save(
                    update_fields=[
                        "maintenance",
                        "status",
                        "stage",
                        "progress",
                        "errors",
                        "updated_at",
                    ]
                )
                persisted = True
            except Exception:
                _log_maintenance_callback_exception(
                    "wiki decision maintenance record persistence failed check=%s record=%s",
                    check_id,
                    record_id,
                )

            if persisted:
                try:
                    persisted_check = CheckItem.objects.get(pk=check_id)
                    persisted_related = dict(persisted_check.related) if isinstance(persisted_check.related, dict) else {}
                    persisted_related["maintenance"] = {
                        "build_record_id": record_id,
                        "status": result.get("status") or decision_record.status,
                    }
                    persisted_check.related = persisted_related
                    persisted_check.save(update_fields=["related", "updated_at"])
                except Exception:
                    _log_maintenance_callback_exception(
                        "wiki decision maintenance check summary persistence failed check=%s record=%s",
                        check_id,
                        record_id,
                    )

            if source_build_record_id:
                try:
                    with transaction.atomic():
                        source_record = BuildRecord.objects.select_for_update().get(pk=source_build_record_id)
                        source_maintenance = dict(source_record.maintenance) if isinstance(source_record.maintenance, dict) else {}
                        decision_children = dict(source_maintenance.get("decision_children") or {})
                        decision_children[str(check_id)] = {
                            "check_id": check_id,
                            "build_record_id": record_id,
                            "status": final_status,
                            "event": event,
                            "affected_page_ids": list(result.get("affected_page_ids") or affected_page_ids),
                            "maintenance": result,
                        }
                        source_maintenance["decision_children"] = decision_children
                        source_record.maintenance = source_maintenance
                        source_record.save(update_fields=["maintenance", "updated_at"])
                except Exception:
                    _log_maintenance_callback_exception(
                        "wiki decision maintenance source mirror failed check=%s source_record=%s",
                        check_id,
                        source_build_record_id,
                    )
        except Exception:
            _log_maintenance_callback_exception(
                "wiki decision maintenance callback failed unexpectedly check=%s record=%s",
                check_id,
                record_id,
            )

    transaction.on_commit(run_maintenance)
    return record


def _schedule_rule_replay_maintenance(
    rule,
    affected_page_ids,
    event,
    *,
    operator="decision_replay",
    deleted_titles=None,
):
    """Persist rule-first merge maintenance without creating a transient CheckItem."""
    affected_page_ids = list(dict.fromkeys(affected_page_ids or []))
    deleted_titles = list(dict.fromkeys(deleted_titles or []))
    pending_maintenance = {
        "status": "pending",
        "event": event,
        "affected_page_ids": affected_page_ids,
        "deleted_titles": deleted_titles,
        "stages": {},
    }
    record = BuildRecord.objects.create(
        knowledge_base=rule.knowledge_base,
        trigger="decision",
        operator=operator or "",
        inputs={
            "decision_rule_id": rule.id,
            "decision_reused": True,
            "decision_action": rule.action,
            "maintenance_event": event,
            "deleted_titles": deleted_titles,
        },
        stage="maintenance_pending",
        progress=90,
        affected_pages=affected_page_ids,
        maintenance=pending_maintenance,
        status="running",
        created_by=operator or "",
        updated_by=operator or "",
    )
    record_id = record.id
    rule_id = rule.id
    knowledge_base_id = rule.knowledge_base_id

    def run_maintenance():
        try:
            callback_error = ""
            try:
                decision_record = BuildRecord.objects.select_related("knowledge_base").get(
                    pk=record_id,
                    knowledge_base_id=knowledge_base_id,
                )
                cascade_kwargs = {}
                if deleted_titles:
                    cascade_kwargs["deleted_titles"] = deleted_titles
                result = cascade(
                    decision_record.knowledge_base,
                    affected_page_ids,
                    event,
                    **cascade_kwargs,
                )
                if not isinstance(result, dict):
                    raise TypeError("cascade must return a maintenance mapping")
                result = dict(result)
                result.setdefault("deleted_titles", deleted_titles)
            except Exception as exc:
                callback_error = str(exc)
                result = {
                    "status": "partial",
                    "event": event,
                    "affected_page_ids": affected_page_ids,
                    "deleted_titles": deleted_titles,
                    "stages": {
                        "cascade": {
                            "status": "failed",
                            "error": callback_error,
                        }
                    },
                }
                _log_maintenance_callback_exception(
                    "wiki rule replay maintenance cascade failed rule=%s record=%s",
                    rule_id,
                    record_id,
                )

            try:
                decision_record = BuildRecord.objects.get(pk=record_id)
                decision_record.maintenance = result
                decision_record.status = (
                    "failed" if callback_error or result.get("status") == "failed" else "partial" if result.get("status") == "partial" else "success"
                )
                decision_record.stage = "done"
                decision_record.progress = 100
                decision_record.errors = [callback_error] if callback_error else []
                decision_record.save(
                    update_fields=[
                        "maintenance",
                        "status",
                        "stage",
                        "progress",
                        "errors",
                        "updated_at",
                    ]
                )
            except Exception:
                _log_maintenance_callback_exception(
                    "wiki rule replay maintenance persistence failed rule=%s record=%s",
                    rule_id,
                    record_id,
                )
        except Exception:
            _log_maintenance_callback_exception(
                "wiki rule replay maintenance callback failed unexpectedly rule=%s record=%s",
                rule_id,
                record_id,
            )

    transaction.on_commit(run_maintenance)
    return record


@transaction.atomic
def create_candidate(
    page,
    body,
    reason,
    check_type="cannot_merge",
    build_record=None,
    created_by="",
    related=None,
    suggested_actions=None,
    change_type="candidate",
    meta_snapshot=None,
    incoming_material=None,
    incoming_material_version=None,
):
    """为风险变更冻结决策上下文并创建候选版本，不改动当前版本。"""
    if check_type not in DECISION_CHECK_TYPES:
        raise ValueError("candidate checks are limited to knowledge conflict or page identity decisions")
    locked_kb = WikiKnowledgeBase.objects.select_for_update().get(pk=page.knowledge_base_id)
    page = KnowledgePage.objects.select_for_update().get(pk=page.pk, knowledge_base=locked_kb)
    page.knowledge_base = locked_kb
    decision_type = _DECISION_TYPE_BY_CHECK_TYPE.get(check_type, "")
    schema_fingerprint = compute_schema_fingerprint(page.knowledge_base) if decision_type else ""
    canonical = canonical_title(page.knowledge_base, page.title)
    subject_key = (
        subject_key_for_page(
            page_type=page.page_type or "concept",
            canonical_title=canonical,
        )
        if decision_type
        else ""
    )

    if incoming_material is None and incoming_material_version is not None:
        incoming_material = incoming_material_version.material
    if incoming_material is not None and incoming_material.knowledge_base_id != page.knowledge_base_id:
        raise ValueError("incoming material must belong to the same knowledge base")
    if incoming_material_version is not None and incoming_material is not None and incoming_material_version.material_id != incoming_material.id:
        raise ValueError("incoming material version does not belong to material")
    if incoming_material is not None and incoming_material_version is None:
        incoming_material_version = getattr(incoming_material, "current_version", None)

    incoming_snapshot = None
    if incoming_material is not None:
        incoming_snapshot = {
            "material_id": incoming_material.id,
            "material_version_id": getattr(incoming_material_version, "id", None),
            "content_hash": (getattr(incoming_material_version, "content_hash", "") or incoming_material.content_hash or ""),
        }

    participants = build_participants_from_page_evidence(page, incoming_snapshot=incoming_snapshot) if decision_type == "knowledge_conflict" else []
    decision_key = ""
    if subject_key and is_participant_complete(participants):
        decision_key = compute_decision_signature(
            knowledge_base_id=page.knowledge_base_id,
            decision_type=decision_type,
            subject_key=subject_key,
            schema_fingerprint=schema_fingerprint,
            participants=participants,
        )
        existing = (
            CheckItem.objects.select_related("candidate_version")
            .filter(
                knowledge_base=page.knowledge_base,
                check_type__in=_CHECK_TYPES_BY_DECISION_TYPE[decision_type],
                decision_key=decision_key,
                status="open",
            )
            .order_by("id")
            .first()
        )
        if existing is not None:
            return existing
    last = page.page_versions.order_by("-no").first()
    next_no = (last.no + 1) if last else 1
    candidate = PageVersion.objects.create(
        page=page,
        no=next_no,
        body=body,
        change_type=change_type,
        is_current=False,
        build_record=build_record,
        created_by=created_by or "",
        meta_snapshot=meta_snapshot or {},
    )
    decision_context = {
        _LOCK_KEY: page.current_version_id,
        "decision_type": decision_type,
        "subject_key": subject_key,
        "schema_fingerprint": schema_fingerprint,
        "participants": participants,
        "incoming": incoming_snapshot or {},
        "current_body_hash": _body_hash(page.current_version.body) if page.current_version else "",
        "candidate_body_hash": _body_hash(body),
        "candidate_version_id": candidate.id,
        "reason": reason or "",
        "page_identity": {
            "page_id": page.id,
            "title": page.title,
            "canonical_title": canonical,
            "compact_title_key": compact_title_key(canonical),
            "page_type": page.page_type,
        },
    }
    if suggested_actions is None:
        suggested_actions = sorted(_KNOWLEDGE_CONFLICT_ACTIONS) if decision_type == "knowledge_conflict" else sorted(_PAGE_IDENTITY_ACTIONS)
    check = CheckItem.objects.create(
        knowledge_base=page.knowledge_base,
        check_type=check_type,
        status="open",
        related=related or {"pages": [page.id]},
        candidate_version=candidate,
        suggested_actions=suggested_actions,
        decision_key=decision_key,
        decision_context=decision_context,
        created_by=created_by or "",
        updated_by=created_by or "",
    )
    return check


@transaction.atomic
def accept_candidate(check, operator=""):
    """接受候选版本:置为当前有效版本,关闭检查。"""
    candidate = check.candidate_version
    if not candidate:
        raise ValueError("check has no candidate_version")
    page = candidate.page
    page.page_versions.filter(is_current=True).update(is_current=False)
    candidate.is_current = True
    candidate.save(update_fields=["is_current"])
    page.current_version = candidate
    if page.contribution == "human":
        page.contribution = "mixed"
    update_fields = ["current_version", "contribution", "updated_at"]
    if page.status != "active":
        page.status = "active"
        update_fields.append("status")
    if candidate.change_type == "qa_answer_candidate":
        page.update_method = "qa_answer"
        update_fields.append("update_method")
    page.save(update_fields=update_fields)
    check.status = "resolved"
    check.save(update_fields=["status", "updated_at"])
    _recount_pending_review(check)
    _schedule_check_maintenance(
        check,
        [page.id],
        "accept",
        operator=operator,
        source_build_record_id=candidate.build_record_id,
    )
    return candidate


@transaction.atomic
def decide_check(  # noqa: C901
    check,
    action,
    operator="",
    body="",
    material=None,
):
    """原子执行冻结的语义决策，并写入可回放规则。"""
    original_check = check
    locked_kb = WikiKnowledgeBase.objects.select_for_update().get(
        pk=check.knowledge_base_id,
    )
    check = CheckItem.objects.select_for_update().get(
        pk=check.pk,
        knowledge_base=locked_kb,
    )
    check.knowledge_base = locked_kb
    if check.status != "open":
        raise ValueError(f"check not open: status={check.status}")

    decision_type = _DECISION_TYPE_BY_CHECK_TYPE.get(check.check_type)
    if decision_type == "knowledge_conflict":
        allowed = _KNOWLEDGE_CONFLICT_ACTIONS
    elif decision_type == "page_identity":
        allowed = _PAGE_IDENTITY_ACTIONS
    else:
        raise ValueError(f"check.check_type {check.check_type!r} not in decision-center scope; use resolve_check for system-scoped items")
    if action not in allowed:
        raise ValueError(f"action {action!r} not allowed for decision_type {decision_type!r}; allowed={sorted(allowed)}")
    if action == "edit_accept" and not (body or "").strip():
        raise ValueError("edit_accept requires non-empty body")
    if material is not None and material.knowledge_base_id != check.knowledge_base_id:
        raise ValueError("资料必须属于同一知识库")
    if decision_type == "page_identity":
        if not _has_frozen_page_identity_context(check):
            return _auto_resolve_stale_decision(
                check,
                original_check,
                "历史页面身份检查缺少冻结上下文",
            )
        return _decide_page_identity(check, action, operator, original_check)
    if not _has_frozen_knowledge_conflict_context(check):
        return _auto_resolve_incomplete_decision(
            check,
            original_check,
            "知识冲突检查缺少完整冻结上下文",
        )
    if not check.candidate_version_id:
        return _auto_resolve_stale_decision(
            check,
            original_check,
            "知识冲突检查缺少候选版本",
        )

    candidate = (
        PageVersion.objects.select_for_update()
        .filter(
            pk=check.candidate_version_id,
        )
        .first()
    )
    if candidate is None:
        return _auto_resolve_stale_decision(check, original_check, "候选版本不存在")
    page = (
        KnowledgePage.objects.select_for_update()
        .filter(
            pk=candidate.page_id,
            knowledge_base_id=check.knowledge_base_id,
        )
        .first()
    )
    if page is None:
        return _auto_resolve_stale_decision(
            check,
            original_check,
            "候选版本页面不存在或不属于当前知识库",
        )
    current_version = PageVersion.objects.select_for_update().filter(pk=page.current_version_id).first() if page.current_version_id else None
    context = dict(check.decision_context or {})
    frozen_participants = context.get("participants")
    frozen_rule_context_complete = _has_frozen_knowledge_conflict_context(check)
    locked_version_id = context.get(_LOCK_KEY)
    if locked_version_id is not None and page.current_version_id != locked_version_id:
        return _auto_resolve_stale_decision(
            check,
            original_check,
            f"当前版本已变化: {page.current_version_id} != {locked_version_id}",
        )
    frozen_candidate_id = context.get("candidate_version_id")
    if frozen_candidate_id is not None and candidate.id != frozen_candidate_id:
        return _auto_resolve_stale_decision(
            check,
            original_check,
            "候选版本已变化",
        )
    frozen_current_hash = context.get("current_body_hash")
    if frozen_current_hash and _body_hash(current_version.body if current_version else "") != frozen_current_hash:
        return _auto_resolve_stale_decision(
            check,
            original_check,
            "当前知识正文已变化",
        )
    frozen_candidate_hash = context.get("candidate_body_hash")
    if frozen_candidate_hash and _body_hash(candidate.body) != frozen_candidate_hash:
        return _auto_resolve_stale_decision(
            check,
            original_check,
            "候选知识正文已变化",
        )

    incoming_snapshot = context.get("incoming")
    if not isinstance(incoming_snapshot, dict):
        incoming_snapshot = {}
    frozen_incoming_id = incoming_snapshot.get("material_id")
    if material is not None and frozen_incoming_id and material.id != frozen_incoming_id:
        raise ValueError("提交资料与冻结的决策上下文不一致")

    evidence_material = None
    evidence_material_version = None
    if frozen_incoming_id:
        evidence_material = (
            Material.objects.select_for_update()
            .filter(
                pk=frozen_incoming_id,
                knowledge_base_id=check.knowledge_base_id,
            )
            .first()
        )
        if evidence_material is None:
            return _auto_resolve_stale_decision(
                check,
                original_check,
                "冻结的新资料不存在或不属于当前知识库",
            )
        frozen_version_id = incoming_snapshot.get("material_version_id")
        if frozen_version_id:
            evidence_material_version = MaterialVersion.objects.filter(
                pk=frozen_version_id,
                material_id=evidence_material.id,
            ).first()
            if evidence_material_version is None:
                return _auto_resolve_stale_decision(
                    check,
                    original_check,
                    "冻结的资料版本不存在或不属于该资料",
                )
    elif material is not None:
        evidence_material = material
        evidence_material_version = getattr(material, "current_version", None)
        incoming_snapshot = {
            "material_id": material.id,
            "material_version_id": getattr(evidence_material_version, "id", None),
            "content_hash": (getattr(evidence_material_version, "content_hash", "") or material.content_hash or ""),
        }

    frozen_participants = context.get("participants")
    current_schema_fingerprint = compute_schema_fingerprint(check.knowledge_base)
    if frozen_rule_context_complete:
        live_material_version = None
        if evidence_material.current_version_id:
            live_material_version = (
                MaterialVersion.objects.select_for_update()
                .filter(
                    pk=evidence_material.current_version_id,
                    material_id=evidence_material.id,
                )
                .first()
            )
        live_incoming_snapshot = {
            "material_id": evidence_material.id,
            "material_version_id": getattr(live_material_version, "id", None),
            "content_hash": (getattr(live_material_version, "content_hash", "") or evidence_material.content_hash or ""),
        }
        live_participants = build_participants_from_page_evidence(
            page,
            incoming_snapshot=live_incoming_snapshot,
        )
        if current_schema_fingerprint != context["schema_fingerprint"]:
            return _auto_resolve_stale_decision(
                check,
                original_check,
                "Schema 已发生变化",
            )
        if _participant_counter(live_participants) != _participant_counter(frozen_participants):
            return _auto_resolve_stale_decision(
                check,
                original_check,
                "参与资料或资料内容已发生变化",
            )
        participants = live_participants
        incoming_snapshot = live_incoming_snapshot
        evidence_material_version = live_material_version
        schema_fingerprint = current_schema_fingerprint
    else:
        if isinstance(frozen_participants, list):
            participants = [dict(item) for item in frozen_participants]
        else:
            participants = build_participants_from_page_evidence(page)
        if evidence_material is not None and not frozen_incoming_id:
            participant_key = (
                incoming_snapshot.get("material_id"),
                incoming_snapshot.get("content_hash"),
            )
            existing_keys = {(item.get("material_id"), item.get("content_hash")) for item in participants}
            if participant_key not in existing_keys:
                participants.append(dict(incoming_snapshot))
        schema_fingerprint = context.get("schema_fingerprint") or current_schema_fingerprint

    subject_key = context.get("subject_key") or subject_key_for_page(
        page_type=page.page_type or "concept",
        canonical_title=canonical_title(check.knowledge_base, page.title),
    )
    original_body_hash = _body_hash(current_version.body) if current_version else ""

    if action == "keep_current":
        result_version = current_version
    elif action == "use_new":
        page.page_versions.filter(is_current=True).update(is_current=False)
        candidate.is_current = True
        candidate.save(update_fields=["is_current", "updated_at"])
        page.current_version = candidate
        update_fields = ["current_version", "updated_at"]
        if page.contribution == "human":
            page.contribution = "mixed"
            update_fields.append("contribution")
        if page.status != "active":
            page.status = "active"
            update_fields.append("status")
        page.save(update_fields=update_fields)
        result_version = candidate
    else:
        result_version = _create_edited_version(page, body, candidate=candidate)
        page.page_versions.filter(is_current=True).update(is_current=False)
        result_version.is_current = True
        result_version.save(update_fields=["is_current", "updated_at"])
        page.current_version = result_version
        update_fields = ["current_version", "updated_at"]
        if page.contribution == "human":
            page.contribution = "mixed"
            update_fields.append("contribution")
        if page.status != "active":
            page.status = "active"
            update_fields.append("status")
        page.save(update_fields=update_fields)

    if action in {"use_new", "edit_accept"} and evidence_material is not None:
        _add_evidence_for_decision(
            page,
            evidence_material,
            evidence_material_version,
            source="decide_check",
        )

    check.status = "resolved"
    check.updated_by = operator or ""
    check.save(update_fields=["status", "updated_by", "updated_at"])
    result_body_hash = _body_hash(result_version.body) if result_version else ""
    match_snapshot = {
        "participants": participants,
        "schema_fingerprint": schema_fingerprint,
        "policy_version": POLICY_VERSION,
        "subject_key": subject_key,
        "current_body_hash": context.get("current_body_hash") or original_body_hash,
        "candidate_body_hash": context.get("candidate_body_hash") or _body_hash(candidate.body),
        "incoming": incoming_snapshot,
        "page_identity": context.get("page_identity")
        or {
            "page_id": page.id,
            "title": page.title,
            "canonical_title": canonical_title(check.knowledge_base, page.title),
            "page_type": page.page_type,
        },
    }
    incoming_pair = (
        incoming_snapshot.get("material_id"),
        (incoming_snapshot.get("content_hash") or "").strip(),
    )
    if action == "keep_current":
        winner_participants = [
            dict(item)
            for item in participants
            if (
                item.get("material_id"),
                (item.get("content_hash") or "").strip(),
            )
            != incoming_pair
        ]
    elif action == "use_new":
        winner_participants = [dict(incoming_snapshot)]
    else:
        winner_participants = [dict(item) for item in participants]
    result_snapshot = {
        "action": action,
        "winner_action": action,
        "operator": operator or "",
        "body_hash": result_body_hash,
        "result_page_id": page.id,
        "result_version_id": getattr(result_version, "id", None),
        "winner_participants": winner_participants,
    }
    if action == "edit_accept":
        result_snapshot["adopted_participants"] = winner_participants
        result_snapshot["edited_result"] = {
            "result_version_id": getattr(result_version, "id", None),
            "body_hash": result_body_hash,
        }
    rule = create_rule_if_eligible(
        knowledge_base=check.knowledge_base,
        decision_type=decision_type,
        subject_key=subject_key if frozen_rule_context_complete else "",
        schema_fingerprint=schema_fingerprint,
        participants=participants,
        action=action,
        match_snapshot=match_snapshot,
        result_snapshot=result_snapshot,
        source_check=check,
        result_page=page,
        result_version=result_version,
    )
    if rule is not None and operator:
        update_fields = ["updated_by", "updated_at"]
        rule.updated_by = operator
        if not rule.created_by:
            rule.created_by = operator
            update_fields.append("created_by")
        rule.save(update_fields=update_fields)

    _freeze_decision_audit(
        check,
        decision_type=decision_type,
        action=action,
        operator=operator,
        rule=rule,
    )
    _recount_pending_review(check)
    _schedule_check_maintenance(
        check,
        [page.id],
        "accept",
        operator=operator,
        source_build_record_id=candidate.build_record_id,
    )
    original_check.status = check.status
    original_check.related = check.related
    original_check.updated_by = check.updated_by
    return rule


def _body_hash(body: str) -> str:
    """正文指纹(短哈希,审计/回放前置条件比较用)。"""
    if not body:
        return ""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


def _create_edited_version(page, body, candidate):
    """edit_accept:从候选继承 build_record / change_type,创建新当前版本。"""
    last = page.page_versions.order_by("-no").first()
    next_no = (last.no + 1) if last else 1
    return PageVersion.objects.create(
        page=page,
        no=next_no,
        body=body,
        change_type="human_edit",  # 编辑后采用 = 人工编辑
        is_current=False,  # 由 caller 置 True
        build_record=candidate.build_record if candidate else None,
        created_by="human_edit",
        meta_snapshot=(candidate.meta_snapshot if candidate else {}),
    )


def _add_evidence_for_decision(page, material, material_version, source=""):
    """按 page + material + frozen version 幂等补齐决策证据。"""
    existing = (
        PageEvidence.objects.filter(
            page=page,
            material=material,
            material_version=material_version,
        )
        .order_by("id")
        .first()
    )
    if existing is not None:
        return existing
    return PageEvidence.objects.create(
        page=page,
        material=material,
        material_version=material_version,
        locator=f"decision:{source}" if source else "",
    )


def _participants_from_check(check, material=None) -> list:
    """从 check.related + 可选 material 构造参与者集合。

    优先取 related.materials(若已存),否则从 candidate_version 反推,再 fallback material。
    """
    related = check.related or {}
    if isinstance(related, dict):
        mats = related.get("materials") or []
        participants = []
        for m in mats:
            if isinstance(m, dict):
                mat_id = m.get("id")
                content_hash = m.get("content_hash") or ""
            else:
                mat_id = getattr(m, "id", None)
                content_hash = getattr(m, "content_hash", "")
            if mat_id and content_hash:
                participants.append({"material_id": mat_id, "content_hash": content_hash})
        if participants:
            return participants
    # fallback: 用调用方传入的 material
    if material is not None and material.id and material.content_hash:
        return [{"material_id": material.id, "content_hash": material.content_hash}]
    return []


@transaction.atomic
def reject_candidate(check, operator=""):
    """拒绝候选版本:删除候选版本,关闭检查,当前有效版本不变。"""
    candidate = check.candidate_version
    check.status = "dismissed"
    check.candidate_version = None
    check.save(update_fields=["status", "candidate_version", "updated_at"])
    if candidate and not candidate.is_current:
        page = candidate.page
        delete_shell_page = page.current_version_id is None and not page.page_versions.exclude(id=candidate.id).exists()
        candidate.delete()
        if delete_shell_page:
            page.delete()
    _recount_pending_review(check)
    return check


@transaction.atomic
def resolve_check(check, operator="", note=""):
    """将无需候选版本的检查项标记为已处理,并记录处理结果。"""
    if check.status != "open":
        raise ValueError("only open checks can be resolved")
    if check.candidate_version_id:
        raise ValueError("candidate checks must be accepted or rejected")
    related = dict(check.related) if isinstance(check.related, dict) else {}
    related["resolution"] = {
        "action": "manual_resolve",
        "operator": operator or "",
        "note": note or "",
        "processed_at": timezone.now().isoformat(),
    }
    check.related = related
    check.status = "resolved"
    check.save(update_fields=["related", "status", "updated_at"])
    _recount_pending_review(check)
    return check


def _ordered_page_ids(related):
    related = related if isinstance(related, dict) else {}
    ordered_ids = []
    seen = set()
    for page_id in related.get("pages", []) or []:
        try:
            parsed = int(page_id)
        except (TypeError, ValueError):
            continue
        if parsed in seen:
            continue
        ordered_ids.append(parsed)
        seen.add(parsed)
    return ordered_ids


def _pages_for_identity(knowledge_base, related, *, for_update=False):
    ordered_ids = _ordered_page_ids(related)
    queryset = KnowledgePage.objects.filter(
        knowledge_base=knowledge_base,
        id__in=ordered_ids,
        status="active",
    )
    if for_update:
        queryset = queryset.select_for_update()
    pages = {page.id: page for page in queryset}
    return [pages[page_id] for page_id in ordered_ids if page_id in pages]


def _related_pages_for_merge(check, *, for_update=False):
    return _pages_for_identity(
        check.knowledge_base,
        check.related,
        for_update=for_update,
    )


def _page_identity_snapshot(knowledge_base, page):
    return build_page_identity_snapshot(knowledge_base, page)


def _stable_identity_tuple(identity):
    return (
        identity.get("page_type") or "",
        identity.get("canonical_title_key") or "",
        identity.get("compact_title_key") or "",
    )


def _freeze_page_identity_context(knowledge_base, pages, related):
    identities = [_page_identity_snapshot(knowledge_base, page) for page in pages]
    related = related if isinstance(related, dict) else {}
    canonical = (related.get("canonical_title") or "").strip()
    canonical_key = compact_title_key(canonical)
    target_identity = None
    if canonical_key:
        exact_candidates = [identity for identity in identities if identity["compact_title_key"] == canonical_key]
        canonical_candidates = [identity for identity in identities if identity["canonical_title_key"] == canonical_key]
        if exact_candidates:
            target_identity = min(exact_candidates, key=_stable_identity_tuple)
        elif canonical_candidates:
            target_identity = min(canonical_candidates, key=_stable_identity_tuple)
    if target_identity is None:
        target_identity = min(identities, key=_stable_identity_tuple)

    identity_keys = ["::".join(_stable_identity_tuple(identity)) for identity in identities]
    raw_subject_key = "identity::" + "|".join(sorted(identity_keys))
    subject_key = raw_subject_key
    if len(subject_key) > 190:
        subject_key = f"{raw_subject_key[:120]}::{hashlib.sha256(raw_subject_key.encode('utf-8')).hexdigest()}"
    schema_fingerprint = compute_schema_fingerprint(knowledge_base)
    decision_key = compute_decision_signature(
        knowledge_base_id=knowledge_base.id,
        decision_type="page_identity",
        subject_key=subject_key,
        schema_fingerprint=schema_fingerprint,
        participants=[],
    )
    context = {
        "decision_type": "page_identity",
        "subject_key": subject_key,
        "schema_fingerprint": schema_fingerprint,
        "page_identities": identities,
        "target_identity": dict(target_identity),
    }
    return context, decision_key


def _identity_matches(left, right):
    return _stable_identity_tuple(left) == _stable_identity_tuple(right)


def _target_page_from_context(knowledge_base, pages, context):
    target_identity = context.get("target_identity") or {}
    live = [(page, _page_identity_snapshot(knowledge_base, page)) for page in pages]
    frozen_page_id = target_identity.get("page_id")
    for page, identity in live:
        if page.id == frozen_page_id and _identity_matches(target_identity, identity):
            return page
    for page, identity in live:
        if _identity_matches(target_identity, identity):
            return page
    raise ValueError("页面身份已过期: frozen target identity no longer exists")


def _merge_target(check, pages):
    related = check.related if isinstance(check.related, dict) else {}
    canonical = (related.get("canonical_title") or "").strip()
    if canonical:
        canonical_key = compact_title_key(canonical)
        for page in pages:
            if compact_title_key(page.title) == canonical_key:
                return page, canonical
    return pages[0], canonical


def _merged_duplicate_body(target, sources):
    pieces = []
    current = (target.current_version.body if target.current_version_id else "") or ""
    if current.strip():
        pieces.append(current.strip())
    for source in sources:
        body = (source.current_version.body if source.current_version_id else "") or ""
        body = body.strip()
        if not body or body in pieces:
            continue
        pieces.append(f"## 合并自: {source.title}\n\n{body}")
    return "\n\n".join(pieces).strip()


def _move_page_evidence(target, sources):
    moved = 0
    for evidence in PageEvidence.objects.filter(page__in=sources):
        exists = PageEvidence.objects.filter(
            page=target,
            material_id=evidence.material_id,
            material_version_id=evidence.material_version_id,
            locator=evidence.locator,
        ).exists()
        if exists:
            evidence.delete()
            continue
        evidence.page = target
        evidence.save(update_fields=["page", "updated_at"])
        moved += 1
    return moved


def _merge_page_identity_pages(pages, target, canonical, operator):
    """Apply the page mutations shared by reviewed and rule-first merges."""
    sources = [page for page in pages if page.id != target.id]
    source_ids = [page.id for page in sources]
    source_titles = [page.title for page in sources]
    body = _merged_duplicate_body(target, sources)
    target.page_versions.filter(is_current=True).update(is_current=False)
    last = target.page_versions.order_by("-no").first()
    version = PageVersion.objects.create(
        page=target,
        no=(last.no + 1) if last else 1,
        body=body,
        change_type="merge_duplicate",
        is_current=True,
        created_by=operator or "",
        meta_snapshot={
            "merged_page_ids": source_ids,
            "merged_titles": source_titles,
            "canonical_title": canonical or target.title,
        },
    )
    if canonical:
        target.title = canonical
    target.current_version = version
    target.tags = list(dict.fromkeys(sum((page.tags or [] for page in pages), [])))
    target.status = "active"
    target.contribution = "mixed"
    target.update_method = "merge_duplicate"
    target.updated_by = operator or ""
    target.save(
        update_fields=[
            "title",
            "tags",
            "current_version",
            "status",
            "contribution",
            "update_method",
            "updated_by",
            "updated_at",
        ]
    )

    for source in sources:
        source.status = "archived"
        source.update_method = "merge_duplicate"
        source.updated_by = operator or ""
        source.save(update_fields=["status", "update_method", "updated_by", "updated_at"])

    moved_evidence = _move_page_evidence(target, sources)
    clear_page_vectors(source_ids)
    return {
        "target_page_id": target.id,
        "archived_page_ids": source_ids,
        "moved_evidence": moved_evidence,
        "_archived_titles": source_titles,
    }


def _apply_page_identity_merge(check, pages, target, canonical, operator):
    merge_result = _merge_page_identity_pages(
        pages,
        target,
        canonical,
        operator,
    )
    source_ids = merge_result["archived_page_ids"]
    source_titles = merge_result.pop("_archived_titles")
    related = dict(check.related) if isinstance(check.related, dict) else {}
    related["merged_into"] = target.id
    related["archived_pages"] = source_ids
    check.related = related
    check.status = "resolved"
    check.updated_by = operator or ""
    check.save(update_fields=["related", "status", "updated_by", "updated_at"])
    _recount_pending_review(check)
    maintenance_record = _schedule_check_maintenance(
        check,
        [target.id, *source_ids],
        "merge_duplicate",
        operator=operator,
        deleted_titles=source_titles,
    )
    return {
        **merge_result,
        "maintenance": dict(maintenance_record.maintenance or {}),
        "maintenance_build_record_id": maintenance_record.id,
    }


def _replay_page_identity_rule(knowledge_base, pages, related, rule):
    if rule.action == "keep_separate":
        return mark_replayed(rule)
    if rule.action != "merge":
        return False

    result_snapshot = rule.result_snapshot if isinstance(rule.result_snapshot, dict) else {}
    match_snapshot = rule.match_snapshot if isinstance(rule.match_snapshot, dict) else {}
    target_identity = result_snapshot.get("target_identity") or match_snapshot.get("target_identity")
    if not isinstance(target_identity, dict) or not target_identity:
        return False
    try:
        target = _target_page_from_context(
            knowledge_base,
            pages,
            {"target_identity": target_identity},
        )
    except ValueError:
        return False

    related = related if isinstance(related, dict) else {}
    canonical = (related.get("canonical_title") or target_identity.get("canonical_title") or target.title or "").strip()
    replayed_source_identities = [_page_identity_snapshot(knowledge_base, page) for page in pages if page.id != target.id]
    if not mark_replayed(rule):
        return False
    merge_result = _merge_page_identity_pages(
        pages,
        target,
        canonical,
        "decision_replay",
    )
    source_titles = merge_result.pop("_archived_titles")
    result_version = target.current_version if target.current_version_id else None
    live_target_identity = _page_identity_snapshot(knowledge_base, target)
    rule.result_page = target
    rule.result_version = result_version
    rule.result_snapshot = {
        **result_snapshot,
        "target_identity": {
            **target_identity,
            **live_target_identity,
            "result_body_hash": _body_hash(result_version.body) if result_version else "",
        },
        "source_identities": replayed_source_identities,
        "result_page_id": target.id,
        "result_version_id": getattr(result_version, "id", None),
    }
    rule.updated_by = "decision_replay"
    rule.save(update_fields=["result_page", "result_version", "result_snapshot", "updated_by", "updated_at"])
    _schedule_rule_replay_maintenance(
        rule,
        [target.id, *merge_result["archived_page_ids"]],
        "merge_duplicate",
        deleted_titles=source_titles,
    )
    return True


def _decide_page_identity(check, action, operator, original_check):
    pages = _related_pages_for_merge(check, for_update=True)
    if len(pages) != 2:
        return _auto_resolve_stale_decision(
            check,
            original_check,
            "页面身份决策不再包含两个有效页面",
        )

    if not _has_frozen_page_identity_context(check):
        return _auto_resolve_stale_decision(
            check,
            original_check,
            "页面身份检查缺少冻结上下文",
        )
    context = dict(check.decision_context)
    stale_reason = page_identity_context_stale_reason(
        knowledge_base_id=check.knowledge_base_id,
        decision_key=check.decision_key,
        context=context,
        schema_fingerprint=compute_schema_fingerprint(check.knowledge_base),
        related_page_ids=(check.related or {}).get("pages", []),
        live_identities=[_page_identity_snapshot(check.knowledge_base, page) for page in pages],
    )
    if stale_reason:
        return _auto_resolve_stale_decision(check, original_check, stale_reason)
    frozen_rule_context_complete = True

    try:
        target = _target_page_from_context(check.knowledge_base, pages, context)
    except ValueError as exc:
        return _auto_resolve_stale_decision(check, original_check, exc)
    frozen_target_identity = context["target_identity"]
    source_identities = [
        dict(identity) for identity in context["page_identities"] if identity.get("page_id") != frozen_target_identity.get("page_id")
    ]
    merge_result = None
    if action == "merge":
        related = check.related if isinstance(check.related, dict) else {}
        canonical = (related.get("canonical_title") or frozen_target_identity.get("canonical_title") or "").strip()
        merge_result = _apply_page_identity_merge(
            check,
            pages,
            target,
            canonical,
            operator,
        )
    else:
        related = dict(check.related) if isinstance(check.related, dict) else {}
        related["resolution"] = {
            "action": "keep_separate",
            "operator": operator or "",
            "processed_at": timezone.now().isoformat(),
        }
        check.related = related
        check.status = "resolved"
        check.updated_by = operator or ""
        check.save(update_fields=["related", "status", "updated_by", "updated_at"])
        _recount_pending_review(check)

    result_version = target.current_version if target.current_version_id else None
    match_snapshot = {
        "page_identities": context["page_identities"],
        "target_identity": frozen_target_identity,
        "schema_fingerprint": context.get("schema_fingerprint") or compute_schema_fingerprint(check.knowledge_base),
        "policy_version": POLICY_VERSION,
        "subject_key": context["subject_key"],
    }
    result_snapshot = {
        "action": action,
        "winner_action": action,
        "operator": operator or "",
        "target_identity": {
            **frozen_target_identity,
            "page_id": target.id,
            "result_body_hash": _body_hash(result_version.body) if result_version else "",
        },
        "source_identities": source_identities,
        "result_page_id": target.id,
        "result_version_id": getattr(result_version, "id", None),
    }
    rule = create_rule_if_eligible(
        knowledge_base=check.knowledge_base,
        decision_type="page_identity",
        subject_key=context["subject_key"] if frozen_rule_context_complete else "",
        schema_fingerprint=match_snapshot["schema_fingerprint"],
        participants=[],
        action=action,
        match_snapshot=match_snapshot,
        result_snapshot=result_snapshot,
        source_check=check,
        result_page=target,
        result_version=result_version,
    )
    if rule is not None and operator:
        update_fields = ["updated_by", "updated_at"]
        rule.updated_by = operator
        if not rule.created_by:
            rule.created_by = operator
            update_fields.append("created_by")
        rule.save(update_fields=update_fields)

    _freeze_decision_audit(
        check,
        decision_type="page_identity",
        action=action,
        operator=operator,
        rule=rule,
    )
    original_check.status = check.status
    original_check.related = check.related
    original_check.decision_key = check.decision_key
    original_check.decision_context = check.decision_context
    original_check.updated_by = check.updated_by
    original_check._merge_result = merge_result
    return rule


@transaction.atomic
def merge_duplicate_check(check, operator=""):
    """兼容旧入口，并将确认合并记录为语义化 page_identity 规则。"""
    if check.check_type != "duplicate":
        raise ValueError("only duplicate checks can be merged")
    if check.status != "open":
        raise ValueError("only open checks can be merged")
    rule = decide_check(check, action="merge", operator=operator)
    result = getattr(check, "_merge_result", None)
    if result is None and rule is None:
        check.refresh_from_db(fields=["status"])
        if check.status == "auto_resolved":
            return None
    if result is None:
        raise ValueError("duplicate merge did not produce a result")
    return result


def scan_health(knowledge_base):
    """系统检查扫描(spec 4.5):孤立、缺有效来源、来源全部失效、过期、疑似重复、冲突、失效关系、低置信度。

    幂等:同类型同页面已存在 open 检查则不重复创建。返回新建的 CheckItem 列表。
    (冲突/低置信为规则启发式;「不符合 Schema」「重要知识缺失」需 schema→类型映射,不在规则扫描内,
    由构建期 cannot_merge 等覆盖无法安全合并类。)
    """
    created = []
    kb = knowledge_base
    pages = list(KnowledgePage.objects.filter(knowledge_base=kb, status="active"))
    by_title = defaultdict(list)
    by_canonical_title = defaultdict(list)
    canonical_titles = {}

    for page in pages:
        has_relation = page.relations_out.exists() or page.relations_in.exists()
        evidences = list(PageEvidence.objects.filter(page=page).select_related("material"))
        has_evidence = bool(evidences)
        by_title[(page.title or "").strip().lower()].append(page)
        canonical = canonical_title(kb, page.title)
        canonical_key = (canonical or "").strip().lower()
        if canonical_key:
            by_canonical_title[canonical_key].append(page)
            canonical_titles[canonical_key] = canonical

        # 孤立:既无关系也无证据
        if not has_relation and not has_evidence:
            created += ensure_check(kb, "orphan", page)
        # 纯 AI 页面无证据 → 缺来源
        elif page.contribution == "ai" and not has_evidence:
            created += ensure_check(kb, "no_source", page)

        # 来源全部失效:有证据但所有证据资料均失效/解析失败
        if has_evidence and all(e.material.status in ("failed", "invalid") for e in evidences):
            created += ensure_check(kb, "all_sources_invalid", page)
        # 过期:证据资料处于「已更新待重建」
        if any(e.material.status == "updated" for e in evidences):
            created += ensure_check(kb, "stale", page)
        # 低置信:AI 页面正文过短
        cur = page.current_version
        if page.contribution == "ai" and cur and len((cur.body or "").strip()) < 30:
            created += ensure_check(kb, "low_confidence", page)

    # 页面身份决策始终按唯一二元组生成；诊断类检查仍按页面独立保留。
    seen_identity_pairs = set()
    for title, group in by_title.items():
        if not title or len(group) < 2:
            continue
        for left, right in combinations(sorted(group, key=lambda item: item.id), 2):
            pair_key = (left.id, right.id)
            if pair_key in seen_identity_pairs:
                continue
            seen_identity_pairs.add(pair_key)
            check_type = "conflict" if left.page_type != right.page_type else "duplicate"
            created += ensure_check(
                kb,
                check_type,
                left,
                related={"pages": [left.id, right.id]},
            )

    # 规范标题成组:标题不同但归一到同一 canonical title → 疑似同义重复。
    for canonical_key, group in by_canonical_title.items():
        if not canonical_key or len(group) < 2:
            continue
        title_keys = {(p.title or "").strip().lower() for p in group if (p.title or "").strip()}
        if len(title_keys) < 2:
            continue
        for left, right in combinations(sorted(group, key=lambda item: item.id), 2):
            pair_key = (left.id, right.id)
            if pair_key in seen_identity_pairs:
                continue
            seen_identity_pairs.add(pair_key)
            check_type = "conflict" if left.page_type != right.page_type else "duplicate"
            created += ensure_check(
                kb,
                check_type,
                left,
                related={
                    "pages": [left.id, right.id],
                    "canonical_title": canonical_titles[canonical_key],
                },
            )

    # 失效关系:关系指向非 active 页面
    broken = PageRelation.objects.filter(from_page__knowledge_base=kb).exclude(to_page__status="active").select_related("from_page")
    for rel in broken:
        created += ensure_check(kb, "broken_relation", rel.from_page)

    created += _missing_wikilink_checks(kb, pages)
    created += _graph_insight_checks(kb)
    return created


def _missing_wikilink_checks(knowledge_base, pages):
    active_keys = set()
    for page in pages:
        active_keys.add(normalize_wikilink_key(page.title))
        canonical = canonical_title(knowledge_base, page.title)
        if canonical:
            active_keys.add(normalize_wikilink_key(canonical))

    missing = {}
    for page in pages:
        body = page.current_version.body if page.current_version_id else ""
        for match in LINK_RE.finditer(body or ""):
            target = match.group(1).strip()
            canonical = canonical_title(knowledge_base, target)
            target_keys = {normalize_wikilink_key(target)}
            if canonical:
                target_keys.add(normalize_wikilink_key(canonical))
            target_keys = {key for key in target_keys if key}
            if not target_keys or active_keys & target_keys:
                continue
            target_key = sorted(target_keys)[0]
            item = missing.setdefault(target_key, {"target": canonical or target, "page_ids": set(), "source_titles": set()})
            item["page_ids"].add(page.id)
            item["source_titles"].add(page.title)

    created = []
    for target_key, item in sorted(missing.items()):
        page_ids = sorted(item["page_ids"])
        existing = (
            CheckItem.objects.filter(
                knowledge_base=knowledge_base,
                check_type="missing",
                related__target_key=target_key,
            )
            .order_by("id")
            .first()
        )
        if existing is not None:
            if existing.status == "open":
                _close_diagnostic(existing)
            continue
        if not page_ids:
            continue
        related = {
            "pages": page_ids,
            "graph_insight": "knowledge_gap",
            "target": item["target"],
            "target_key": target_key,
            "suggested_queries": _missing_suggested_queries(item["target"], item["source_titles"]),
        }
        created.append(
            CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type="missing",
                status="auto_resolved",
                related=_automatic_diagnostic_related(related),
                suggested_actions=[],
                created_by="system",
                updated_by="system",
            )
        )
    return created


def _missing_suggested_queries(target, source_titles):
    queries = []
    target = (target or "").strip()
    if target:
        queries.append(target)
    for title in sorted(source_titles or []):
        title = (title or "").strip()
        if not title or not target:
            continue
        queries.append(f"{title} {target}")
    return list(dict.fromkeys(queries))


def _graph_insight_checks(knowledge_base):
    graph = analyze_graph(knowledge_base)
    insights = graph.get("insights") or {}
    sparse_page_ids = [page_id for community in insights.get("sparse_communities", []) for page_id in community.get("page_ids", []) if page_id]
    cross_edge_page_ids = [page_id for edge in insights.get("cross_community_edges", []) for page_id in (edge.get("from"), edge.get("to")) if page_id]
    pages = {
        page.id: page
        for page in KnowledgePage.objects.filter(
            knowledge_base=knowledge_base,
            status="active",
            id__in=[
                *[item.get("id") for item in insights.get("bridge_nodes", []) if item.get("id")],
                *sparse_page_ids,
                *cross_edge_page_ids,
            ],
        )
    }
    created = []
    for item in insights.get("bridge_nodes", []):
        page = pages.get(item.get("id"))
        if not page:
            continue
        related = {
            "pages": [page.id],
            "graph_insight": "bridge_node",
            "degree": item.get("degree", 0),
            "component_count_after_removal": item.get("component_count_after_removal", 0),
        }
        created += ensure_check(
            knowledge_base,
            "bridge_node",
            page,
            suggested_actions=["review_graph", "supplement_source", "restructure_page"],
            related=related,
        )
    for item in insights.get("cross_community_edges", []):
        page_ids = sorted(page_id for page_id in [item.get("from"), item.get("to")] if page_id in pages)
        if len(page_ids) != 2:
            continue
        existing = (
            CheckItem.objects.filter(
                knowledge_base=knowledge_base,
                check_type="cross_community_edge",
                related__pages__contains=page_ids,
            )
            .order_by("id")
            .first()
        )
        if existing is not None:
            if existing.status == "open":
                _close_diagnostic(existing)
            continue
        related = {
            "pages": page_ids,
            "graph_insight": "cross_community_edge",
            "from": item.get("from"),
            "to": item.get("to"),
            "from_title": item.get("from_title", ""),
            "to_title": item.get("to_title", ""),
            "weight": item.get("weight", 0),
            "signals": item.get("signals", {}),
            "from_community": item.get("from_community", -1),
            "to_community": item.get("to_community", -1),
        }
        created.append(
            CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type="cross_community_edge",
                status="auto_resolved",
                related=_automatic_diagnostic_related(related),
                suggested_actions=[],
                created_by="system",
                updated_by="system",
            )
        )
    for item in insights.get("sparse_communities", []):
        page_ids = [page_id for page_id in item.get("page_ids", []) if page_id in pages]
        if not page_ids:
            continue
        related = {
            "pages": page_ids,
            "graph_insight": "sparse_community",
            "density": item.get("density", 0),
            "edge_count": item.get("edge_count", 0),
            "possible_edges": item.get("possible_edges", 0),
        }
        created += ensure_check(
            knowledge_base,
            "sparse_community",
            pages[page_ids[0]],
            suggested_actions=["review_graph", "supplement_source", "restructure_page"],
            related=related,
        )
    # 惊奇连接:跨社区强边且两侧标题不共享显著词
    for item in insights.get("surprise_links", []):
        page_ids = sorted(page_id for page_id in [item.get("from"), item.get("to")] if page_id in pages)
        if len(page_ids) != 2:
            continue
        existing = (
            CheckItem.objects.filter(
                knowledge_base=knowledge_base,
                check_type="surprise_link",
                related__pages__contains=page_ids,
            )
            .order_by("id")
            .first()
        )
        if existing is not None:
            if existing.status == "open":
                _close_diagnostic(existing)
            continue
        related = {
            "pages": page_ids,
            "graph_insight": "surprise_link",
            "from": item.get("from"),
            "to": item.get("to"),
            "from_title": item.get("from_title", ""),
            "to_title": item.get("to_title", ""),
            "weight": item.get("weight", 0),
            "signals": item.get("signals", {}),
            "from_community": item.get("from_community", -1),
            "to_community": item.get("to_community", -1),
        }
        created.append(
            CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type="surprise_link",
                status="auto_resolved",
                related=_automatic_diagnostic_related(related),
                suggested_actions=[],
                created_by="system",
                updated_by="system",
            )
        )
    return created


@transaction.atomic
def ensure_check(knowledge_base, check_type, page, suggested_actions=None, related=None):
    """幂等创建检查；页面身份项冻结稳定身份对与明确目标。"""
    knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(
        pk=knowledge_base.pk,
    )
    if page.knowledge_base_id != knowledge_base.id:
        raise ValueError("page must belong to the same knowledge base")
    related_value = related or {"pages": [page.id]}
    decision_type = _DECISION_TYPE_BY_CHECK_TYPE.get(check_type)
    if decision_type == "page_identity":
        pages = _pages_for_identity(
            knowledge_base,
            related_value,
            for_update=True,
        )
        if len(pages) != 2:
            return []
        related_value = dict(related_value) if isinstance(related_value, dict) else {}
        related_value["pages"] = [identity_page.id for identity_page in pages]
        decision_context, decision_key = _freeze_page_identity_context(
            knowledge_base,
            pages,
            related_value,
        )
        rule = find_active_rule(
            knowledge_base,
            "page_identity",
            decision_key,
        )
        if rule is not None and _replay_page_identity_rule(
            knowledge_base,
            pages,
            related_value,
            rule,
        ):
            return []
        exists = CheckItem.objects.filter(
            knowledge_base=knowledge_base,
            check_type__in=_CHECK_TYPES_BY_DECISION_TYPE["page_identity"],
            decision_key=decision_key,
            status="open",
        ).exists()
        if exists:
            return []
        return [
            CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type=check_type,
                status="open",
                related=related_value,
                suggested_actions=suggested_actions or sorted(_PAGE_IDENTITY_ACTIONS),
                decision_key=decision_key,
                decision_context=decision_context,
            )
        ]

    if decision_type == "knowledge_conflict":
        raise ValueError("knowledge conflict checks require a candidate version")

    existing = _find_diagnostic(
        knowledge_base,
        check_type,
        related_value,
        source_page_id=page.id,
    )
    if existing is not None:
        _close_diagnostic(existing, related_value)
        return []

    return [
        CheckItem.objects.create(
            knowledge_base=knowledge_base,
            check_type=check_type,
            status="auto_resolved",
            related=_automatic_diagnostic_related(related_value),
            suggested_actions=[],
            created_by="system",
            updated_by="system",
        )
    ]
