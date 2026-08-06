"""Lock-owned transition that enables Wiki directory governance for one KB."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.opspilot.models import WikiKnowledgeBase
from apps.opspilot.services.wiki.directory_readiness_service import KnowledgeBaseReadinessResult, require_directory_enable_readiness


class WikiDirectoryEnableError(RuntimeError):
    """Stable domain failure raised before the enable transition writes."""

    retryable = False

    def __init__(self, code: str, message: str, *, details=None):
        self.code = code
        self.details = dict(details or {})
        super().__init__(message)


@dataclass(frozen=True)
class WikiDirectoryEnableResult:
    knowledge_base_id: int
    directory_enabled: bool
    changed: bool
    readiness: KnowledgeBaseReadinessResult


@transaction.atomic
def enable_wiki_directory(
    knowledge_base: WikiKnowledgeBase | int,
    *,
    operator: str = "",
) -> WikiDirectoryEnableResult:
    """Lock the KB, recheck readiness, and atomically switch it to enabled.

    This is the only public enable entry point.  The readiness query executes
    after ``select_for_update`` and before either migration field is persisted,
    so a concurrent build or governance writer cannot invalidate the decision
    between validation and publication.
    """

    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    if not isinstance(knowledge_base_id, int) or isinstance(knowledge_base_id, bool):
        raise ValueError("knowledge_base must be a persisted instance or integer ID")

    normalized_operator = str(operator or "").strip()
    if len(normalized_operator) > 32:
        raise ValueError("operator cannot exceed 32 characters")

    locked_knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
    readiness = require_directory_enable_readiness(locked_knowledge_base)
    changed = not locked_knowledge_base.directory_enabled
    if changed:
        locked_knowledge_base.directory_enabled = True
        locked_knowledge_base.directory_migration_state = "enabled"
        update_fields = ["directory_enabled", "directory_migration_state", "updated_at"]
        if normalized_operator:
            locked_knowledge_base.updated_by = normalized_operator
            update_fields.append("updated_by")
        locked_knowledge_base.save(update_fields=update_fields)
    elif locked_knowledge_base.directory_migration_state != "enabled":
        locked_knowledge_base.directory_migration_state = "enabled"
        locked_knowledge_base.save(update_fields=["directory_migration_state", "updated_at"])

    return WikiDirectoryEnableResult(
        knowledge_base_id=locked_knowledge_base.pk,
        directory_enabled=True,
        changed=changed,
        readiness=readiness,
    )
