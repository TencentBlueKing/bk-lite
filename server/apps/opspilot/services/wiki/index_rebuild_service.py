"""Wiki 索引重建记录服务。

页面级、资料级重建都走同一套阶段统计和 BuildRecord 记录格式,避免前端诊断口径分叉。
"""

from apps.opspilot.models import BuildRecord


def _stage_success(count=0):
    return {"status": "success", "count": count}


def _stage_failed(error):
    return {"status": "failed", "error": str(error)}


def _final_status(stages):
    return "partial" if any(stage.get("status") == "failed" for stage in stages.values()) else "success"


def rebuild_page_indexes(
    knowledge_base,
    pages,
    *,
    trigger,
    event,
    operator="",
    inputs=None,
    index_fn,
    chunk_index_fn,
):
    """重建一组页面的页面级与 chunk 级索引,返回落库后的 BuildRecord。"""
    page_list = list(pages or [])
    affected_page_ids = [page.id for page in page_list]
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger=trigger,
        operator=operator,
        inputs=inputs or {},
        affected_pages=affected_page_ids,
        stage="indexing",
        progress=10,
        status="running",
    )

    indexed_pages = 0
    indexed_chunks = 0
    page_errors = []
    chunk_errors = []
    for page in page_list:
        if not page.current_version_id:
            page_errors.append(f"{page.title}: 无当前版本")
            chunk_errors.append(f"{page.title}: 无当前版本")
            continue
        if index_fn(page.current_version, knowledge_base.embed_provider):
            indexed_pages += 1
        else:
            page_errors.append(f"{page.title}: 页面索引未生成")

        chunk_count = chunk_index_fn(page, knowledge_base.embed_provider)
        if chunk_count:
            indexed_chunks += chunk_count
        else:
            chunk_errors.append(f"{page.title}: 分块索引未生成")

    stages = {
        "page_embedding": _stage_failed("; ".join(page_errors)) if page_errors else _stage_success(indexed_pages),
        "chunk_embedding": _stage_failed("; ".join(chunk_errors)) if chunk_errors else _stage_success(indexed_chunks),
    }
    status = _final_status(stages)
    maintenance = {
        "status": status,
        "event": event,
        "affected_page_ids": affected_page_ids,
        "stages": stages,
        "indexed_pages": indexed_pages,
        "indexed_chunks": indexed_chunks,
    }
    build.stage = "done"
    build.progress = 100
    build.status = status
    build.counts = {"indexed_pages": indexed_pages, "indexed_chunks": indexed_chunks}
    build.maintenance = maintenance
    build.save(update_fields=["stage", "progress", "status", "counts", "maintenance", "updated_at"])
    return build
