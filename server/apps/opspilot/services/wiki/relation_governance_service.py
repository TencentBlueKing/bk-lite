"""Governance generation for explicitly rebuilding derived Wiki relations."""

from apps.opspilot.models import BuildRecord, WikiKnowledgeBase
from apps.opspilot.services.wiki.build_generation_service import begin_build_generation, finalize_build_generation


def rebuild_active_generation_relations(knowledge_base, *, operator=""):
    knowledge_base = WikiKnowledgeBase.objects.select_related("active_generation").get(pk=knowledge_base.pk)
    active = knowledge_base.active_generation
    record = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="relation_rebuild",
        operator=operator or "",
        inputs={"knowledge_base_id": knowledge_base.pk},
        stage="generating",
        status="running",
    )
    context = begin_build_generation(
        knowledge_base,
        record,
        source_fingerprints=list(getattr(active, "source_fingerprints", None) or []),
        pipeline_version="wiki-relation-governance-v1",
        kind="governance",
        operator=operator,
    )
    activation, relations = finalize_build_generation(
        context,
        build_record=record,
        page_actions=[],
        directory_trace=[],
    )
    record.refresh_from_db()
    record.counts = {"relations": relations["relation_count"]}
    record.stage = "done"
    record.status = "success"
    record.progress = 100
    record.save(update_fields=["counts", "stage", "status", "progress", "updated_at"])
    return {
        "build_record": record,
        "generation_id": activation.active_generation_id,
        "relations": relations,
    }


__all__ = ["rebuild_active_generation_relations"]
