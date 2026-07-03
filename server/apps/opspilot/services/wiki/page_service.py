"""知识页面版本管理:人工创建/编辑/恢复都生成新版本,当前有效版本始终明确。

对应 spec §8(页面编辑)、§9(版本管理:每次变化生成新版本,可比较与恢复)。
"""

import difflib

from django.db import transaction

from apps.opspilot.models import KnowledgePage, PageVersion
from apps.opspilot.services.wiki.check_service import create_candidate


def _next_no(page):
    last = page.page_versions.order_by("-no").first()
    return (last.no + 1) if last else 1


@transaction.atomic
def _new_current_version(page, body, change_type, created_by, meta_snapshot=None):
    """创建一个新版本并置为当前,旧的当前版本取消 is_current。"""
    page.page_versions.filter(is_current=True).update(is_current=False)
    version = PageVersion.objects.create(
        page=page,
        no=_next_no(page),
        body=body,
        change_type=change_type,
        is_current=True,
        created_by=created_by or "",
        meta_snapshot=meta_snapshot or {},
    )
    page.current_version = version
    page.save(update_fields=["current_version", "updated_at"])
    return version


@transaction.atomic
def create_manual_page(knowledge_base, page_type, title, body="", tags=None, created_by=""):
    """人工创建知识页面(贡献来源=human)。"""
    page = KnowledgePage.objects.create(
        knowledge_base=knowledge_base,
        page_type=page_type,
        title=title,
        tags=tags or [],
        contribution="human",
        update_method="human_edit",
        created_by=created_by or "",
    )
    _new_current_version(page, body=body, change_type="human_edit", created_by=created_by)
    return page


def _answer_source_meta(source_conversation_id="", source_message_id="", source_channel="qa"):
    return {
        "type": "qa_answer",
        "conversation_id": str(source_conversation_id),
        "message_id": str(source_message_id or ""),
        "channel": str(source_channel or "qa"),
    }


@transaction.atomic
def save_answer_page(
    knowledge_base,
    page_type,
    title,
    body,
    tags=None,
    source_conversation_id="",
    source_message_id="",
    source_channel="qa",
    created_by="",
):
    """将 QA/Bot 回答沉淀为知识页面,并记录来源对话。"""
    page = KnowledgePage.objects.create(
        knowledge_base=knowledge_base,
        page_type=page_type,
        title=title,
        tags=tags or [],
        contribution="mixed",
        update_method="qa_answer",
        created_by=created_by or "",
    )
    _new_current_version(
        page,
        body=body,
        change_type="qa_answer",
        created_by=created_by,
        meta_snapshot={"source": _answer_source_meta(source_conversation_id, source_message_id, source_channel)},
    )
    return page


@transaction.atomic
def save_answer_candidate_page(
    knowledge_base,
    page_type,
    title,
    body,
    tags=None,
    source_conversation_id="",
    source_message_id="",
    source_channel="qa",
    created_by="",
):
    """将 QA/Bot 回答保存为待审核候选页,接受前不进入正式知识消费面。"""
    source = _answer_source_meta(source_conversation_id, source_message_id, source_channel)
    page = KnowledgePage.objects.create(
        knowledge_base=knowledge_base,
        page_type=page_type,
        title=title,
        tags=tags or [],
        contribution="mixed",
        update_method="qa_answer",
        status="pending_review",
        created_by=created_by or "",
    )
    return create_candidate(
        page,
        body=body,
        reason="qa_answer_pending_review",
        check_type="qa_answer_candidate",
        created_by=created_by,
        related={"pages": [page.id], "source": source},
        suggested_actions=["accept", "reject", "edit_accept"],
        change_type="qa_answer_candidate",
        meta_snapshot={"source": source},
    )


@transaction.atomic
def import_markdown_page(knowledge_base, page_type, title, body, tags=None, source_meta=None, operator=""):
    """导入 Markdown 为知识页面;同标题同类型的非归档页面更新为新版本。"""
    page = (
        KnowledgePage.objects.filter(knowledge_base=knowledge_base, title=title, page_type=page_type)
        .exclude(status="archived")
        .order_by("id")
        .first()
    )
    if page:
        page.tags = tags or []
        if page.contribution == "ai":
            page.contribution = "mixed"
        page.update_method = "markdown_import"
        page.status = "active"
        page.updated_by = operator or ""
        page.save(update_fields=["tags", "contribution", "update_method", "status", "updated_by", "updated_at"])
        _new_current_version(
            page,
            body=body,
            change_type="markdown_import",
            created_by=operator,
            meta_snapshot={"source": source_meta or {}},
        )
        return page, False

    page = KnowledgePage.objects.create(
        knowledge_base=knowledge_base,
        page_type=page_type,
        title=title,
        tags=tags or [],
        contribution="human",
        update_method="markdown_import",
        status="active",
        created_by=operator or "",
    )
    _new_current_version(
        page,
        body=body,
        change_type="markdown_import",
        created_by=operator,
        meta_snapshot={"source": source_meta or {}},
    )
    return page, True


@transaction.atomic
def edit_page(page, body=None, title=None, tags=None, updated_by=""):
    """人工编辑页面:更新元数据并生成新版本。AI 页面被人工编辑后贡献来源升级为 mixed。"""
    if title is not None:
        page.title = title
    if tags is not None:
        page.tags = tags
    if page.contribution == "ai":
        page.contribution = "mixed"
    page.update_method = "human_edit"
    page.updated_by = updated_by or ""
    page.save(update_fields=["title", "tags", "contribution", "update_method", "updated_by", "updated_at"])
    new_body = body if body is not None else (page.current_version.body if page.current_version_id else "")
    return _new_current_version(page, body=new_body, change_type="human_edit", created_by=updated_by)


@transaction.atomic
def restore_version(page, version_id, operator=""):
    """恢复历史版本:复制其正文为新版本(change_type=restore),不删除历史。"""
    target = page.page_versions.get(id=version_id)
    return _new_current_version(page, body=target.body, change_type="restore", created_by=operator)


def diff_versions(page, from_id, to_id):
    """返回两个版本正文的逐行统一 diff(unified diff 行列表),用于版本对比可视化。"""
    versions = {v.id: v for v in page.page_versions.filter(id__in=[from_id, to_id])}
    a, b = versions.get(from_id), versions.get(to_id)
    if not a or not b:
        raise ValueError("version not found")
    return list(
        difflib.unified_diff(
            (a.body or "").splitlines(),
            (b.body or "").splitlines(),
            fromfile=f"v{a.no}",
            tofile=f"v{b.no}",
            lineterm="",
        )
    )
