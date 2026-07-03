import logging

from apps.opspilot.models import KnowledgePage
from apps.opspilot.services.wiki.embedding_service import clear_page_vectors, index_version, reindex_page_chunks
from apps.opspilot.services.wiki.relation_service import rebuild_relations, sync_relations_for_pages
from apps.opspilot.services.wiki.sweep_service import drop_page_references, sweep_open_checks

logger = logging.getLogger("opspilot")
_FULL_RELATION_REBUILD = rebuild_relations
MAINTENANCE_STAGE_KEYS = (
    "relations",
    "page_embedding",
    "chunk_embedding",
    "check_sweep",
    "deleted_page_prune",
)


def _stage_success(count=0):
    return {"status": "success", "count": count}


def _stage_failed(exc):
    return {"status": "failed", "error": str(exc)}


def _stage_skipped(reason):
    return {"status": "skipped", "reason": reason}


def _finalize_status(result):
    failed = [stage for stage in result["stages"].values() if stage.get("status") == "failed"]
    result["status"] = "partial" if failed else "success"
    return result


def _selected_stages(stages):
    if stages is None:
        return None
    return {stage for stage in stages if stage in MAINTENANCE_STAGE_KEYS}


def _runs_stage(selected, stage):
    return selected is None or stage in selected


def _runs_any_stage(selected, stages):
    return selected is None or bool(selected.intersection(stages))


def cascade(
    knowledge_base,
    affected_page_ids=None,
    event="build",
    deleted_titles=None,
    prune_deleted_pages=False,
    stages=None,
):
    """Best-effort downstream maintenance after Wiki page lifecycle changes."""
    affected_page_ids = list(affected_page_ids or [])
    selected = _selected_stages(stages)
    result = {
        "status": "success",
        "event": event,
        "affected_page_ids": affected_page_ids,
        "stages": {},
        "relations": 0,
        "indexed_pages": 0,
        "indexed_chunks": 0,
        "cleared_pages": 0,
        "auto_resolved": 0,
        "pruned_checks": 0,
        "pruned_build_records": 0,
    }
    if _runs_stage(selected, "relations"):
        try:
            result["relations"] = len(sync_relations_for_pages(knowledge_base, affected_page_ids, deleted_titles=deleted_titles))
            result["stages"]["relations"] = _stage_success(result["relations"])
        except Exception as exc:
            logger.exception("wiki cascade relation rebuild failed kb=%s", knowledge_base.id)
            result["stages"]["relations"] = _stage_failed(exc)
    if _runs_any_stage(selected, {"page_embedding", "chunk_embedding"}):
        try:
            if event in ("delete", "page_delete", "material_delete"):
                result["cleared_pages"] = clear_page_vectors(affected_page_ids)
                if _runs_stage(selected, "page_embedding"):
                    result["stages"]["page_embedding"] = _stage_success(result["cleared_pages"])
                if _runs_stage(selected, "chunk_embedding"):
                    result["stages"]["chunk_embedding"] = _stage_success(result["cleared_pages"])
            else:
                pages = KnowledgePage.objects.filter(id__in=affected_page_ids, status="active").select_related("current_version")
                for page in pages:
                    if _runs_stage(selected, "page_embedding") and page.current_version:
                        if index_version(page.current_version, knowledge_base.embed_provider):
                            result["indexed_pages"] += 1
                    if _runs_stage(selected, "chunk_embedding"):
                        result["indexed_chunks"] += reindex_page_chunks(page, knowledge_base.embed_provider)
                if _runs_stage(selected, "page_embedding"):
                    result["stages"]["page_embedding"] = _stage_success(result["indexed_pages"])
                if _runs_stage(selected, "chunk_embedding"):
                    result["stages"]["chunk_embedding"] = _stage_success(result["indexed_chunks"])
        except Exception as exc:
            logger.exception("wiki cascade index update failed kb=%s event=%s", knowledge_base.id, event)
            if _runs_stage(selected, "page_embedding"):
                result["stages"]["page_embedding"] = _stage_failed(exc)
            if _runs_stage(selected, "chunk_embedding"):
                result["stages"]["chunk_embedding"] = _stage_failed(exc)
    if _runs_stage(selected, "check_sweep"):
        try:
            result["auto_resolved"] = sweep_open_checks(knowledge_base)
            result["stages"]["check_sweep"] = _stage_success(result["auto_resolved"])
        except Exception as exc:
            logger.exception("wiki cascade check sweep failed kb=%s", knowledge_base.id)
            result["stages"]["check_sweep"] = _stage_failed(exc)
    if _runs_stage(selected, "deleted_page_prune"):
        if prune_deleted_pages:
            try:
                pruned = drop_page_references(knowledge_base, affected_page_ids)
                result["pruned_checks"] = pruned["checks"]
                result["pruned_build_records"] = pruned["build_records"]
                result["stages"]["deleted_page_prune"] = _stage_success(result["pruned_checks"] + result["pruned_build_records"])
            except Exception as exc:
                logger.exception("wiki cascade prune deleted pages failed kb=%s", knowledge_base.id)
                result["stages"]["deleted_page_prune"] = _stage_failed(exc)
        else:
            result["stages"]["deleted_page_prune"] = _stage_skipped("prune_deleted_pages_disabled")
    return _finalize_status(result)
