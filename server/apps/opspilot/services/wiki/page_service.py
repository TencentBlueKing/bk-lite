"""知识页面版本管理:人工创建/编辑/恢复都生成新版本,当前有效版本始终明确。

对应 spec §8(页面编辑)、§9(版本管理:每次变化生成新版本,可比较与恢复)。
"""

import difflib

from django.db import transaction

from apps.opspilot.models import KnowledgePage, PageVersion
from apps.opspilot.services.wiki.decision_service import revoke_rules_for_identity_change, subject_key_for_page
from apps.opspilot.services.wiki.title_service import canonical_title


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
def edit_page(
    page,
    body=None,
    title=None,
    tags=None,
    page_type=None,
    updated_by="",
):
    """人工编辑页面，并在稳定身份变化前撤销相关页面身份规则。"""
    next_title = page.title if title is None else title
    next_page_type = page.page_type if page_type is None else page_type
    if next_title != page.title or next_page_type != page.page_type:
        old_subject_key = subject_key_for_page(
            page_type=page.page_type or "concept",
            canonical_title=canonical_title(page.knowledge_base, page.title),
        )
        revoke_rules_for_identity_change(
            page.knowledge_base,
            old_subject_key,
            reason="page identity changed",
            operator=updated_by,
        )
    page.title = next_title
    page.page_type = next_page_type
    if tags is not None:
        page.tags = tags
    if page.contribution == "ai":
        page.contribution = "mixed"
    page.update_method = "human_edit"
    page.updated_by = updated_by or ""
    page.save(
        update_fields=[
            "title",
            "page_type",
            "tags",
            "contribution",
            "update_method",
            "updated_by",
            "updated_at",
        ]
    )
    new_body = body if body is not None else (page.current_version.body if page.current_version_id else "")
    return _new_current_version(
        page,
        body=new_body,
        change_type="human_edit",
        created_by=updated_by,
    )


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
