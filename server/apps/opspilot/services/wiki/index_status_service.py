"""Wiki 页面对象级索引状态。

状态从当前页面版本、chunk 索引与最近构建维护结果派生，避免再引入一份需要同步的状态表。
"""

from collections import defaultdict

from apps.opspilot.models import BuildRecord, PageChunk
from apps.opspilot.services.wiki.embedding_service import chunk_markdown

_INDEX_STAGE_KEYS = ("page_embedding", "chunk_embedding")
_INDEX_REBUILD_TRIGGERS = {"kb_reindex", "material_reindex", "page_reindex"}


def _stage_failure(stage):
    if not isinstance(stage, dict) or stage.get("status") != "failed":
        return None
    return {"status": "failed", "error": stage.get("error", "")}


def _is_running_index_record(record):
    return record.status == "running" and (record.stage == "indexing" or record.trigger in _INDEX_REBUILD_TRIGGERS)


def _stage_indexing(record):
    return {
        "status": "indexing",
        "build_record_id": record.id,
        "trigger": record.trigger,
        "stage": record.stage,
    }


def failed_index_stages_for_pages(pages, limit=30):
    """返回 {page_id: {stage_key: stage_override}}，优先保留最近索引运行/失败状态。"""
    pages = list(pages or [])
    page_ids_by_kb = defaultdict(set)
    for page in pages:
        page_ids_by_kb[page.knowledge_base_id].add(page.id)

    overrides = {page.id: {} for page in pages}
    for kb_id, page_ids in page_ids_by_kb.items():
        records = BuildRecord.objects.filter(knowledge_base_id=kb_id).order_by("-id")[:limit]
        for record in records:
            maintenance = record.maintenance if isinstance(record.maintenance, dict) else {}
            affected_ids = set(maintenance.get("affected_page_ids") or record.affected_pages or [])
            matched_ids = page_ids & affected_ids
            if not matched_ids:
                continue
            if _is_running_index_record(record):
                for page_id in matched_ids:
                    for stage_key in _INDEX_STAGE_KEYS:
                        overrides.setdefault(page_id, {}).setdefault(stage_key, _stage_indexing(record))
                continue
            stages = maintenance.get("stages") if isinstance(maintenance.get("stages"), dict) else {}
            for stage_key in _INDEX_STAGE_KEYS:
                failure = _stage_failure(stages.get(stage_key))
                if not failure:
                    continue
                for page_id in matched_ids:
                    overrides.setdefault(page_id, {}).setdefault(stage_key, failure)
    return overrides


def _skipped(reason):
    return {"status": "skipped", "reason": reason}


def _not_indexed(**extra):
    return {"status": "not_indexed", **extra}


def _indexed(**extra):
    return {"status": "indexed", **extra}


def page_index_detail(page, failure_lookup=None):
    """返回页面级和 chunk 级索引状态明细。"""
    failures = (failure_lookup or {}).get(page.id) or {}
    page_failure = failures.get("page_embedding")
    chunk_failure = failures.get("chunk_embedding")
    if not page.knowledge_base.embed_provider_id:
        detail = {
            "page_embedding": page_failure or _skipped("no_embed_provider"),
            "chunk_embedding": chunk_failure or _skipped("no_embed_provider"),
        }
        detail["status"] = _combined_status(detail)
        return detail

    current_version = page.current_version
    body = (current_version.body if current_version else "") or ""
    if not current_version:
        page_status = _not_indexed(reason="no_current_version")
        chunk_status = _not_indexed(reason="no_current_version", indexed_chunks=0, expected_chunks=0)
    elif not body.strip():
        page_status = _skipped("empty_body")
        chunk_status = {**_skipped("empty_body"), "indexed_chunks": 0, "expected_chunks": 0}
    else:
        page_status = _indexed() if current_version.embedding else _not_indexed()
        expected_chunks = len(chunk_markdown(body))
        chunks = PageChunk.objects.filter(page=page, version=current_version).only("embedding")
        indexed_chunks = sum(1 for chunk in chunks if chunk.embedding)
        chunk_status = (
            _indexed(indexed_chunks=indexed_chunks, expected_chunks=expected_chunks)
            if expected_chunks and indexed_chunks >= expected_chunks
            else _not_indexed(indexed_chunks=indexed_chunks, expected_chunks=expected_chunks)
        )

    detail = {
        "page_embedding": page_failure or page_status,
        "chunk_embedding": chunk_failure or chunk_status,
    }
    detail["status"] = _combined_status(detail)
    return detail


def _combined_status(detail):
    statuses = {detail[key]["status"] for key in _INDEX_STAGE_KEYS if key in detail}
    if "failed" in statuses:
        return "failed"
    if "indexing" in statuses:
        return "indexing"
    if "not_indexed" in statuses:
        return "not_indexed"
    if statuses == {"indexed"}:
        return "indexed"
    return "skipped"
