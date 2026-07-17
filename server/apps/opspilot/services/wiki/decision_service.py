"""Wiki 决策服务(phase 2):稳定签名 + 规则 upsert/查询/撤销/回放。

设计来源:openspec streamline-wiki-knowledge-decisions
- 主签名 = SHA-256(policy_version + kb_id + decision_type + subject_key +
  schema_fingerprint + sorted_unique((material_id, content_hash)))
- 参与者去重 + 排序 → 签名与顺序/重复无关
- 上下文不完整(空 participants / 缺 material_id 或 content_hash / 缺 subject_key)→ 不创建规则
- 规则 upsert: 同 (kb, decision_type, decision_key) active 时复用同一条
- revoke 不回滚当前知识,仅把 status 改 revoked(下次同签名重新建决策)
- replay_count 是审计字段,自动回放命中时 +1
"""

import hashlib
import json
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

if TYPE_CHECKING:
    from apps.opspilot.models import WikiDecisionRule

POLICY_VERSION = "v1"


def _normalize_participants(participants: Iterable[Dict[str, Any]]) -> List[tuple]:
    """participants: [{material_id, content_hash}, ...] → 排序去重后的 (mat_id, hash) 元组列表。

    - material_id / content_hash 任一为 None / 空字符串 → 拒绝整个集合
    - 同 (mat_id, hash) 重复 → 去重
    - 排序按 (mat_id, hash) 元组比较
    """
    seen = set()
    items = []
    for p in participants or []:
        mat_id = p.get("material_id")
        content_hash = (p.get("content_hash") or "").strip()
        if mat_id is None or mat_id == "" or not content_hash:
            raise ValueError("participants must all include material_id and content_hash")
        key = (mat_id, content_hash)
        if key in seen:
            continue
        seen.add(key)
        items.append(key)
    items.sort()
    return items


def compute_decision_signature(
    *,
    knowledge_base_id: int,
    decision_type: str,
    subject_key: str,
    schema_fingerprint: str,
    participants: Iterable[Dict[str, Any]],
) -> str:
    """生成知识冲突/页面身份的稳定 SHA-256 签名(64 hex 字符)。

    主签名不依赖资料在界面中的"当前/新"位置,只依赖:
      policy_version + kb_id + decision_type + subject_key +
      schema_fingerprint + sorted_unique(material_id, content_hash)
    """
    normalized = _normalize_participants(participants)
    participants_str = "|".join(f"{mid}#{h}" for mid, h in normalized)
    payload = f"{POLICY_VERSION}|{knowledge_base_id}|{decision_type}|{subject_key}|{schema_fingerprint}|{participants_str}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_schema_fingerprint(kb) -> str:
    """Schema 指纹:KB 的 schema_md + generation_rules 内容 hash(版本相关)。"""
    generation_rules = json.dumps(
        kb.generation_rules or {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload = f"{(kb.schema_md or '').strip()}|{generation_rules}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def subject_key_for_page(*, page_type: str, canonical_title: str) -> str:
    """页面身份 subject_key:page_type + canonical_title key。"""
    from apps.opspilot.services.wiki.title_service import compact_title_key

    return f"page::{page_type}::{compact_title_key(canonical_title)}"


def compute_page_identity_decision_key(
    *,
    knowledge_base_id: int,
    page_type: str,
    canonical_title_a: str,
    canonical_title_b: str,
    schema_fingerprint: str,
) -> str:
    """phase 5 工具:页面身份对的决策签名(不依赖 page id,用 canonical title + page_type 排序)。

    排序保证 AB 和 BA 是同一签名。
    """
    from apps.opspilot.services.wiki.title_service import compact_title_key

    a = compact_title_key(canonical_title_a or "")
    b = compact_title_key(canonical_title_b or "")
    pair = sorted([a, b])
    subject = f"identity::{pair[0]}::{pair[1]}"
    payload = f"{POLICY_VERSION}|page_identity|{knowledge_base_id}|{page_type}|{subject}|{schema_fingerprint}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_participant_complete(participants: Iterable[Dict[str, Any]]) -> bool:
    """所有参与者都必须有 material_id + content_hash 才算上下文完整。"""
    if not participants:
        return False
    for p in participants:
        if p.get("material_id") in (None, "") or not (p.get("content_hash") or "").strip():
            return False
    return True


def create_rule_if_eligible(
    *,
    knowledge_base,
    decision_type: str,
    subject_key: str,
    schema_fingerprint: str,
    participants: Iterable[Dict[str, Any]],
    action: str,
    match_snapshot: Optional[Dict[str, Any]] = None,
    result_snapshot: Optional[Dict[str, Any]] = None,
    source_check=None,
    result_page=None,
    result_version=None,
    result_page_id: Optional[int] = None,
    result_version_id: Optional[int] = None,
) -> Optional["WikiDecisionRule"]:
    """签名 + 完整上下文校验通过 → upsert WikiDecisionRule(active),否则返回 None。

    已有同签名 active 规则时,update 字段(upsert 语义,opsppec/tasks.md 2.4 行为)。

    result_page / result_version 接受 Model 实例(自动取 id),也接受 result_page_id /
    result_version_id 整数 ID,兼容上层两种调用习惯。
    """
    from apps.opspilot.models import WikiDecisionRule

    if not subject_key or not subject_key.strip():
        return None
    participants = list(participants or [])
    if decision_type != "page_identity" and not is_participant_complete(participants):
        return None

    decision_key = compute_decision_signature(
        knowledge_base_id=knowledge_base.id,
        decision_type=decision_type,
        subject_key=subject_key,
        schema_fingerprint=schema_fingerprint,
        participants=participants,
    )
    resolved_page_id = result_page.id if result_page is not None else result_page_id
    resolved_version_id = result_version.id if result_version is not None else result_version_id
    defaults = {
        "subject_key": subject_key,
        "match_snapshot": match_snapshot or {"participants": list(participants)},
        "result_snapshot": result_snapshot or {},
        "action": action,
        "source_check": source_check,
        "result_page_id": resolved_page_id,
        "result_version_id": resolved_version_id,
        "status": WikiDecisionRule.STATUS_ACTIVE,
    }
    rule, created = WikiDecisionRule.objects.update_or_create(
        knowledge_base=knowledge_base,
        decision_type=decision_type,
        decision_key=decision_key,
        defaults=defaults,
    )
    return rule


def find_active_rule(knowledge_base, decision_type: str, decision_key: str):
    """查 active 规则,revoked 视为不存在(openspec 2.4 行为)。"""
    from apps.opspilot.models import WikiDecisionRule

    return WikiDecisionRule.objects.filter(
        knowledge_base=knowledge_base,
        decision_type=decision_type,
        decision_key=decision_key,
        status=WikiDecisionRule.STATUS_ACTIVE,
    ).first()


def build_participants_from_materials(materials) -> list:
    """从 material 列表构造参与者快照，不丢弃不完整项。"""
    participants = []
    for material in materials or []:
        if material is None:
            continue
        material_version = getattr(material, "current_version", None)
        participants.append(
            {
                "material_id": getattr(material, "id", None),
                "material_version_id": getattr(material_version, "id", None),
                "content_hash": (getattr(material_version, "content_hash", "") or getattr(material, "content_hash", "") or ""),
            }
        )
    return participants


def build_participants_from_page_evidence(page, *, incoming_snapshot=None) -> list:
    """冻结页面全部证据与本次新资料，供候选、审批和回放共用。

    证据优先使用 ``material_version.content_hash``，为空时回退
    ``material.content_hash``。不完整项仍保留，由 ``is_participant_complete``
    统一阻止规则创建或回放，避免退化成来源子集。
    """
    participants = []
    evidences = page.evidences.select_related("material", "material_version").order_by("id")
    for evidence in evidences:
        material_version = evidence.material_version
        participants.append(
            {
                "material_id": evidence.material_id,
                "material_version_id": evidence.material_version_id,
                "content_hash": (getattr(material_version, "content_hash", "") or getattr(evidence.material, "content_hash", "") or ""),
            }
        )
    if incoming_snapshot is not None:
        participants.append(dict(incoming_snapshot))
    return participants


_PAGE_IDENTITY_FIELDS = (
    "page_id",
    "title",
    "page_type",
    "canonical_title",
    "canonical_title_key",
    "compact_title_key",
    "current_version_id",
    "body_hash",
)


def build_page_identity_snapshot(knowledge_base, page) -> dict:
    """Freeze the semantic page identity plus the exact source participant set."""
    from apps.opspilot.services.wiki.title_service import canonical_title, compact_title_key

    canonical = canonical_title(knowledge_base, page.title)
    current = page.current_version if page.current_version_id else None
    evidences = list(page.evidences.select_related("material", "material_version").order_by("id"))
    source_names = list(dict.fromkeys(evidence.material.name for evidence in evidences if evidence.material_id))
    source_participants = [
        {
            "material_id": evidence.material_id,
            "material_version_id": evidence.material_version_id,
            "content_hash": (getattr(evidence.material_version, "content_hash", "") or getattr(evidence.material, "content_hash", "") or ""),
        }
        for evidence in evidences
    ]
    body = current.body if current else ""
    return {
        "page_id": page.id,
        "title": page.title,
        "page_type": page.page_type,
        "canonical_title": canonical,
        "canonical_title_key": compact_title_key(canonical),
        "compact_title_key": compact_title_key(page.title),
        "current_version_id": page.current_version_id,
        "version_label": f"v{current.no}" if current else "",
        "body_hash": hashlib.sha256(body.encode("utf-8")).hexdigest()[:32] if body else "",
        "source_label": ", ".join(source_names),
        "source_count": len(evidences),
        "source_participants": source_participants,
        "relation_count": page.relations_out.count() + page.relations_in.count(),
        "contribution": page.contribution,
    }


def _normalized_identity_participants(value):
    if not isinstance(value, list):
        return None
    normalized = set()
    for participant in value:
        if not isinstance(participant, dict):
            return None
        material_id = participant.get("material_id")
        content_hash = (participant.get("content_hash") or "").strip()
        if material_id in (None, ""):
            return None
        normalized.add((material_id, content_hash))
    return normalized


def _identity_snapshot_matches(frozen, live):
    if not isinstance(frozen, dict) or not isinstance(live, dict):
        return False
    if any(field not in frozen for field in _PAGE_IDENTITY_FIELDS):
        return False
    if any(frozen.get(field) != live.get(field) for field in _PAGE_IDENTITY_FIELDS):
        return False
    frozen_participants = _normalized_identity_participants(frozen.get("source_participants"))
    live_participants = _normalized_identity_participants(live.get("source_participants"))
    return frozen_participants is not None and frozen_participants == live_participants


def page_identity_context_stale_reason(
    *,
    knowledge_base_id,
    decision_key,
    context,
    schema_fingerprint,
    related_page_ids,
    live_identities,
):
    """Return why a frozen page-identity decision is stale, or ``None``."""
    if not isinstance(context, dict):
        return "页面身份检查缺少冻结上下文"
    subject_key = context.get("subject_key")
    frozen_schema = context.get("schema_fingerprint")
    frozen_identities = context.get("page_identities")
    target_identity = context.get("target_identity")
    if (
        context.get("decision_type") != "page_identity"
        or not decision_key
        or not subject_key
        or not frozen_schema
        or not isinstance(frozen_identities, list)
        or len(frozen_identities) != 2
        or not isinstance(target_identity, dict)
        or not target_identity
    ):
        return "页面身份检查缺少冻结上下文"
    expected_key = compute_decision_signature(
        knowledge_base_id=knowledge_base_id,
        decision_type="page_identity",
        subject_key=subject_key,
        schema_fingerprint=frozen_schema,
        participants=[],
    )
    if expected_key != decision_key:
        return "页面身份检查签名与冻结上下文不一致"
    if schema_fingerprint != frozen_schema:
        return "Schema 已发生变化"

    try:
        related_ids = [int(page_id) for page_id in related_page_ids]
    except (TypeError, ValueError):
        return "页面身份决策的关联页面集合已变化"
    frozen_by_id = {}
    for identity in frozen_identities:
        if not isinstance(identity, dict):
            return "页面身份检查缺少冻结上下文"
        page_id = identity.get("page_id")
        if page_id in (None, "") or page_id in frozen_by_id:
            return "页面身份检查缺少冻结上下文"
        frozen_by_id[page_id] = identity
    if len(related_ids) != 2 or len(set(related_ids)) != 2 or set(related_ids) != set(frozen_by_id):
        return "页面身份决策的关联页面集合已变化"

    live_by_id = {
        identity.get("page_id"): identity for identity in live_identities if isinstance(identity, dict) and identity.get("page_id") not in (None, "")
    }
    if len(live_by_id) != 2 or set(live_by_id) != set(frozen_by_id):
        return "页面身份决策不再包含两个有效页面"
    for page_id, frozen in frozen_by_id.items():
        if not _identity_snapshot_matches(frozen, live_by_id[page_id]):
            return "页面身份、版本、正文或来源参与集合已变化"

    target_page_id = target_identity.get("page_id")
    frozen_target = frozen_by_id.get(target_page_id)
    if frozen_target is None or not _identity_snapshot_matches(target_identity, frozen_target):
        return "页面合并目标身份与冻结上下文不一致"
    return None


def replay_decision(
    *,
    knowledge_base,
    decision_type: str,
    subject_key: str,
    schema_fingerprint: str,
    participants,
    page,
    candidate_body=None,
):
    """phase 4 核心入口:build / update / rebuild 流程在创建候选前调。

    返回 (result, rule):
      - ("replayed", rule):命中有效规则且当前页面仍满足结果前置条件(不创建 CheckItem)
      - ("pending", None):未命中/规则已失效,需创建 CheckItem 让用户决策
      - ("unchanged", None):候选正文与当前正文相同,无需决策也无需规则

    调用方根据 result:
      - replayed: 复用 rule.action 执行(由调用方继续,本函数不应用)
      - pending: 调 create_candidate 创建新候选,后续由用户 decide
      - unchanged: 直接跳过,不创建 CheckItem 也不写 Rule
    """
    from apps.opspilot.services.wiki.check_service import _body_hash

    participants = list(participants or [])
    current_body = page.current_version.body if page.current_version_id else ""
    if candidate_body is not None and _body_hash(candidate_body) == _body_hash(current_body):
        return "unchanged", None

    if not is_participant_complete(participants):
        # 上下文不完整 → 让人决策
        return "pending", None

    decision_key = compute_decision_signature(
        knowledge_base_id=knowledge_base.id,
        decision_type=decision_type,
        subject_key=subject_key,
        schema_fingerprint=schema_fingerprint,
        participants=participants,
    )
    rule = find_active_rule(knowledge_base, decision_type, decision_key)
    if rule is None:
        return "pending", None

    if decision_type == "knowledge_conflict":
        expected_body_hash = (rule.result_snapshot or {}).get("body_hash") or ""
        if not expected_body_hash or _body_hash(current_body) != expected_body_hash:
            # 审批后正文发生变化时旧规则不再适用。
            return "pending", None

    if page.current_version_id is None:
        return "pending", None

    if not mark_replayed(rule):
        return "pending", None
    return "replayed", rule


def mark_replayed(rule) -> bool:
    """Claim an active rule atomically before replaying it."""
    from django.db.models import F
    from django.utils import timezone

    from apps.opspilot.models import WikiDecisionRule

    now = timezone.now()
    updated = WikiDecisionRule.objects.filter(
        pk=rule.pk,
        status=WikiDecisionRule.STATUS_ACTIVE,
    ).update(
        replay_count=F("replay_count") + 1,
        last_replayed_at=now,
        updated_at=now,
    )
    try:
        rule.refresh_from_db(
            fields=[
                "status",
                "replay_count",
                "last_replayed_at",
                "updated_at",
            ]
        )
    except WikiDecisionRule.DoesNotExist:
        return False
    return updated == 1


def _sync_source_check_revocation(rule, *, reason, operator, revoked_at):
    if not rule.source_check_id:
        return

    from django.db import transaction

    from apps.opspilot.models import CheckItem

    with transaction.atomic():
        check = CheckItem.objects.select_for_update().filter(pk=rule.source_check_id, knowledge_base_id=rule.knowledge_base_id).first()
        if check is None:
            return
        related = dict(check.related) if isinstance(check.related, dict) else {}
        snapshot = related.get("rule_snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("id") != rule.id:
            return
        snapshot = dict(snapshot)
        snapshot.update(
            {
                "status": "revoked",
                "revoked_reason": reason,
                "revoked_by": operator or "",
                "revoked_at": revoked_at,
            }
        )
        related["rule_snapshot"] = snapshot
        resolution = related.get("resolution")
        if isinstance(resolution, dict):
            resolution = dict(resolution)
            resolution["rule_status"] = "revoked"
            resolution["revoked_reason"] = reason
            related["resolution"] = resolution
        check.related = related
        check.save(update_fields=["related", "updated_at"])


def revoke_rule(rule, *, reason="", operator=""):
    """撤销单条规则并保存审计原因；当前知识不回滚。"""
    from django.utils import timezone

    from apps.opspilot.models import WikiDecisionRule

    revoked_reason = (reason or "").strip()
    revoked_at = timezone.now().isoformat()
    result_snapshot = dict(rule.result_snapshot or {})
    result_snapshot["revoked_reason"] = revoked_reason
    result_snapshot["revoked_by"] = operator or ""
    result_snapshot["revoked_at"] = revoked_at
    rule.status = WikiDecisionRule.STATUS_REVOKED
    rule.result_snapshot = result_snapshot
    update_fields = ["status", "result_snapshot", "updated_at"]
    if operator:
        rule.updated_by = operator
        update_fields.append("updated_by")
    rule.save(update_fields=update_fields)
    _sync_source_check_revocation(
        rule,
        reason=revoked_reason,
        operator=operator,
        revoked_at=revoked_at,
    )
    return rule


def _rule_page_identity_snapshots(rule) -> list:
    snapshots = []
    match_snapshot = rule.match_snapshot if isinstance(rule.match_snapshot, dict) else {}
    result_snapshot = rule.result_snapshot if isinstance(rule.result_snapshot, dict) else {}
    snapshots.extend(item for item in match_snapshot.get("page_identities", []) or [] if isinstance(item, dict))
    target_identity = result_snapshot.get("target_identity")
    if isinstance(target_identity, dict):
        snapshots.append(target_identity)
    snapshots.extend(item for item in result_snapshot.get("source_identities", []) or [] if isinstance(item, dict))
    return snapshots


def revoke_rules_for_materials(
    materials,
    *,
    reason="material removed",
    operator="",
) -> int:
    """撤销任何参与者引用指定资料的规则，并保留失效审计。"""
    from apps.opspilot.models import WikiDecisionRule

    material_ids = {material.id for material in materials if getattr(material, "id", None)}
    if not material_ids:
        return 0
    affected = 0
    rules = WikiDecisionRule.objects.filter(status=WikiDecisionRule.STATUS_ACTIVE)
    for rule in rules:
        match_snapshot = rule.match_snapshot if isinstance(rule.match_snapshot, dict) else {}
        participants = match_snapshot.get("participants") or []
        if not any(isinstance(participant, dict) and participant.get("material_id") in material_ids for participant in participants):
            continue
        revoke_rule(rule, reason=reason, operator=operator)
        affected += 1
    return affected


def revoke_rules_for_pages(
    pages,
    *,
    decision_type=None,
    actions=None,
    reason="page removed",
    operator="",
) -> int:
    """撤销结果页或冻结页面身份对任一成员引用指定页面的规则。"""
    from apps.opspilot.models import WikiDecisionRule

    page_ids = {page.id for page in pages if getattr(page, "id", None)}
    if not page_ids:
        return 0
    affected = 0
    rules = WikiDecisionRule.objects.filter(status=WikiDecisionRule.STATUS_ACTIVE)
    if decision_type:
        rules = rules.filter(decision_type=decision_type)
    if actions:
        rules = rules.filter(action__in=set(actions))
    for rule in rules:
        snapshot_page_ids = {identity.get("page_id") for identity in _rule_page_identity_snapshots(rule) if identity.get("page_id") not in (None, "")}
        if rule.result_page_id not in page_ids and not (snapshot_page_ids & page_ids):
            continue
        revoke_rule(rule, reason=reason, operator=operator)
        affected += 1
    return affected


def revoke_rules_for_identity_change(
    knowledge_base,
    old_subject_key: str,
    *,
    reason="page identity changed",
    operator="",
) -> int:
    """撤销直接 subject 或冻结 identity pair 任一成员匹配旧身份的规则。"""
    from apps.opspilot.models import WikiDecisionRule

    if not old_subject_key or not old_subject_key.strip():
        return 0
    affected = 0
    rules = WikiDecisionRule.objects.filter(
        knowledge_base=knowledge_base,
        status=WikiDecisionRule.STATUS_ACTIVE,
    )
    for rule in rules:
        matched = rule.subject_key == old_subject_key
        if not matched:
            for identity in _rule_page_identity_snapshots(rule):
                identity_subject = identity.get("subject_key") or subject_key_for_page(
                    page_type=identity.get("page_type") or "concept",
                    canonical_title=(
                        identity.get("canonical_title")
                        or identity.get("canonical_title_key")
                        or identity.get("compact_title_key")
                        or identity.get("title")
                        or ""
                    ),
                )
                if identity_subject == old_subject_key:
                    matched = True
                    break
        if not matched:
            continue
        revoke_rule(rule, reason=reason, operator=operator)
        affected += 1
    return affected
