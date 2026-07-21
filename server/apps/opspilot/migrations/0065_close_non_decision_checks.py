from django.db import migrations, models
from django.utils import timezone

DECISION_CHECK_TYPES = (
    "cannot_merge",
    "material_update",
    "duplicate",
    "conflict",
)


def _has_complete_knowledge_conflict_context(check):
    context = check.decision_context if isinstance(check.decision_context, dict) else {}
    participants = context.get("participants")
    incoming = context.get("incoming")
    page_identity = context.get("page_identity")
    if not isinstance(participants, list) or not participants:
        return False
    if not isinstance(incoming, dict) or not isinstance(page_identity, dict) or not page_identity:
        return False
    participant_pairs = set()
    for participant in participants:
        if not isinstance(participant, dict):
            return False
        material_id = participant.get("material_id")
        content_hash = (participant.get("content_hash") or "").strip()
        if material_id in (None, "") or not content_hash:
            return False
        participant_pairs.add((material_id, content_hash))
    incoming_pair = (
        incoming.get("material_id"),
        (incoming.get("content_hash") or "").strip(),
    )
    return bool(
        check.decision_key
        and check.candidate_version_id
        and context.get("decision_type") == "knowledge_conflict"
        and context.get("subject_key")
        and context.get("schema_fingerprint")
        and context.get("locked_current_version_id") not in (None, "")
        and context.get("candidate_version_id") == check.candidate_version_id
        and context.get("current_body_hash")
        and context.get("candidate_body_hash")
        and page_identity.get("page_id") not in (None, "")
        and incoming_pair[0] not in (None, "")
        and incoming_pair[1]
        and incoming_pair in participant_pairs
    )


def _has_complete_page_identity_context(check):
    context = check.decision_context if isinstance(check.decision_context, dict) else {}
    identities = context.get("page_identities")
    return bool(
        check.decision_key
        and context.get("decision_type") == "page_identity"
        and context.get("subject_key")
        and context.get("schema_fingerprint")
        and isinstance(identities, list)
        and len(identities) == 2
        and all(isinstance(identity, dict) and identity for identity in identities)
        and isinstance(context.get("target_identity"), dict)
        and context["target_identity"]
    )


def _has_complete_decision_context(check):
    if check.check_type in ("cannot_merge", "material_update"):
        return _has_complete_knowledge_conflict_context(check)
    if check.check_type in ("duplicate", "conflict"):
        return _has_complete_page_identity_context(check)
    return False


def close_non_decision_checks(apps, schema_editor):
    """关闭历史诊断审批，并把旧 QA 新知识候选直接准入。"""
    CheckItem = apps.get_model("opspilot", "CheckItem")
    KnowledgePage = apps.get_model("opspilot", "KnowledgePage")
    PageVersion = apps.get_model("opspilot", "PageVersion")
    processed_at = timezone.now()

    checks = CheckItem.objects.filter(status="open").order_by("id")
    for check in checks.iterator():
        is_decision = check.check_type in DECISION_CHECK_TYPES
        if is_decision and _has_complete_decision_context(check):
            continue
        action = "automatic_maintenance"
        if check.check_type == "qa_answer_candidate" and check.candidate_version_id:
            candidate = PageVersion.objects.filter(
                pk=check.candidate_version_id,
                page__knowledge_base_id=check.knowledge_base_id,
            ).first()
            if candidate is not None:
                PageVersion.objects.filter(
                    page_id=candidate.page_id,
                    is_current=True,
                ).exclude(
                    pk=candidate.pk
                ).update(is_current=False)
                PageVersion.objects.filter(pk=candidate.pk).update(is_current=True, change_type="qa_answer")
                KnowledgePage.objects.filter(pk=candidate.page_id).update(
                    current_version_id=candidate.pk,
                    status="active",
                    update_method="qa_answer",
                )
                action = "automatic_admission"

        related = dict(check.related) if isinstance(check.related, dict) else {}
        related["resolution"] = {
            "action": action,
            "operator": "system_migration",
            "processed_at": processed_at.isoformat(),
        }
        if is_decision:
            related["resolution"]["reason"] = "decision_context_incomplete"
        CheckItem.objects.filter(pk=check.pk).update(
            status="auto_resolved",
            suggested_actions=[],
            related=related,
            updated_by="system",
            updated_at=processed_at,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0064_decision_rule"),
    ]

    operations = [
        migrations.RunPython(
            close_non_decision_checks,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="checkitem",
            constraint=models.CheckConstraint(
                check=(~models.Q(status="open") | models.Q(check_type__in=DECISION_CHECK_TYPES)),
                name="wiki_check_open_decision_only",
            ),
        ),
    ]
