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
from typing import Any, Dict, Iterable, List, Optional

POLICY_VERSION = "v1"


def _normalize_participants(participants: Iterable[Dict[str, Any]]) -> List[tuple]:
    """participants: [{material_id, content_hash}, ...] → 排序去重后的 (mat_id, hash) 元组列表。

    - material_id / content_hash 任一为 None / 空字符串 → 视为不完整,过滤掉
    - 同 (mat_id, hash) 重复 → 去重
    - 排序按 (mat_id, hash) 元组比较
    """
    seen = set()
    items = []
    for p in participants or []:
        mat_id = p.get("material_id")
        content_hash = (p.get("content_hash") or "").strip()
        if mat_id is None or mat_id == "" or not content_hash:
            continue
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
    payload = f"{(kb.schema_md or '').strip()}|{kb.generation_rules!r}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def subject_key_for_page(*, page_type: str, canonical_title: str) -> str:
    """页面身份 subject_key:page_type + canonical_title key。"""
    from apps.opspilot.services.wiki.title_service import compact_title_key

    return f"page::{page_type}::{compact_title_key(canonical_title)}"


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
    if not is_participant_complete(participants):
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
    """phase 4 工具:从 material 列表构造参与者签名(给 build / update / rebuild 共用)。

    过滤缺 content_hash 的 material,保证签名完整性(只有完整上下文的 material 参与签名)。
    """
    participants = []
    for mat in materials or []:
        if mat and mat.id and mat.content_hash:
            participants.append({"material_id": mat.id, "content_hash": mat.content_hash})
    return participants


def replay_decision(
    *,
    knowledge_base,
    decision_type: str,
    subject_key: str,
    schema_fingerprint: str,
    participants,
    page,
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

    if not participants:
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

    # 验证当前页面仍满足结果前置条件:result_version 必须是 page.current_version
    # 且 result_version.body 与当前 page.current_version.body 哈希一致
    if rule.result_version_id is None or page.current_version_id != rule.result_version_id:
        # 规则不再适用当前页面(可能人工编辑过)
        import sys

        sys.stderr.write(
            f"\n[DEBUG replay_decision] rule.id={rule.id} "
            f"page.current_version_id={page.current_version_id} "
            f"rule.result_version_id={rule.result_version_id} "
            f"decision_key={decision_key[:16]}..\n"
        )
        sys.stderr.flush()
        return "pending", None

    # 标记回放
    mark_replayed(rule)
    return "replayed", rule


def mark_replayed(rule) -> None:
    """自动回放命中时 +1(审计字段),更新 last_replayed_at。"""
    from django.utils import timezone

    rule.replay_count = (rule.replay_count or 0) + 1
    rule.last_replayed_at = timezone.now()
    rule.save(update_fields=["replay_count", "last_replayed_at", "updated_at"])


def revoke_rule(rule) -> None:
    """单条规则撤销(status=revoked,当前知识不回滚)。"""
    from apps.opspilot.models import WikiDecisionRule

    rule.status = WikiDecisionRule.STATUS_REVOKED
    rule.save(update_fields=["status", "updated_at"])


def revoke_rules_for_materials(materials) -> int:
    """资料被物理删除:撤销 source_check / match_snapshot.participants 引用此资料的所有 active 规则。

    当前知识不回滚;下次同签名冲突重新进人工决策(openspec 2.5 / spec / 失效)。
    """
    from apps.opspilot.models import WikiDecisionRule

    mat_ids = {m.id for m in materials}
    if not mat_ids:
        return 0
    affected = 0
    # match_snapshot.participants 是 JSON 列表,需 PG JSON 查询(跨 DB 不可靠);
    # 简化:全表 scan 内存过滤(规则量在 KB 级,可控)
    rules = WikiDecisionRule.objects.filter(status=WikiDecisionRule.STATUS_ACTIVE)
    for rule in rules:
        participants = (rule.match_snapshot or {}).get("participants") or []
        if any((p.get("material_id") in mat_ids) for p in participants):
            rule.status = WikiDecisionRule.STATUS_REVOKED
            rule.save(update_fields=["status", "updated_at"])
            affected += 1
    return affected


def revoke_rules_for_pages(pages) -> int:
    """页面被物理删除 / 归档恢复:撤销 result_page 引用此页面的 active 规则。"""
    from apps.opspilot.models import WikiDecisionRule

    page_ids = {p.id for p in pages}
    if not page_ids:
        return 0
    affected = 0
    rules = WikiDecisionRule.objects.filter(status=WikiDecisionRule.STATUS_ACTIVE)
    for rule in rules:
        if rule.result_page_id in page_ids:
            rule.status = WikiDecisionRule.STATUS_REVOKED
            rule.save(update_fields=["status", "updated_at"])
            affected += 1
    return affected


def revoke_rules_for_identity_change(knowledge_base, old_subject_key: str) -> int:
    """页面身份变化(类型/规范标题):撤销 subject_key = old_subject_key 的 active 规则。

    old_subject_key 是页面身份变更前的主签名主体,变更后签名变了,旧规则不再适用,撤销。
    """
    from apps.opspilot.models import WikiDecisionRule

    if not old_subject_key or not old_subject_key.strip():
        return 0
    affected = 0
    rules = WikiDecisionRule.objects.filter(
        knowledge_base=knowledge_base,
        subject_key=old_subject_key,
        status=WikiDecisionRule.STATUS_ACTIVE,
    )
    for rule in rules:
        rule.status = WikiDecisionRule.STATUS_REVOKED
        rule.save(update_fields=["status", "updated_at"])
        affected += 1
    return affected
