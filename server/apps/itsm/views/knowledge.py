import json
from uuid import uuid4

from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import itsm_logger as logger
from apps.core.logger import safe_exception_info
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models.extend import KnowledgeArticle, KnowledgeAttachmentCleanup
from apps.itsm.services.attachment import BUCKET, download_url, storage_client
from apps.itsm.services.basic_settings import attachment_type_allowed
from apps.itsm.services.knowledge_attachments import cleanup_attachment, queue_attachment_cleanup, reserve_upload
from apps.itsm.views.access import api_errors, domain_of, has_permission, ticket_scope

PUBLISHED_STATUSES = ("published", "synced")
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024
MAX_TICKET_ID = 2**63 - 1


def _contents(article):
    return {
        "id": article.id,
        "title": article.title,
        "category": article.category,
        "content_format": article.content_format,
        "status": "published" if article.status in PUBLISHED_STATUSES else "draft",
        "updated_at": article.updated_at.isoformat(),
    }


def _attachment_data(item, *, can_delete):
    return {"id": item.id, "name": item.name, "size": item.size, "can_delete": can_delete}


def _can_manage_attachments(request, article):
    return has_permission(request, "knowledge-Edit") or (
        has_permission(request, "knowledge-Add") and article.created_by == request.user.username and article.status == "draft"
    )


def _detail(request, article):
    can_link_tickets = has_permission(request, "ticket-View")
    can_upload = has_permission(request, "knowledge-View") and _can_manage_attachments(request, article)
    return {
        **_contents(article),
        "content": article.content,
        "tickets": (
            list(article.tickets.filter(pk__in=ticket_scope(request)).order_by("pk").values("id", "sn", "title")) if can_link_tickets else []
        ),
        "attachments": [_attachment_data(item, can_delete=can_upload) for item in article.attachments.order_by("pk")],
        "can_link_tickets": can_link_tickets,
        "can_upload": can_upload,
    }


def _permissions(request):
    return {f"can_{action.lower()}": has_permission(request, f"knowledge-{action}") for action in ("Add", "Edit", "Delete")}


def _article_scope(request):
    return KnowledgeArticle.objects.filter(domain=domain_of(request))


def _visible_articles(queryset, permissions, username):
    if permissions["can_edit"] or permissions["can_delete"]:
        return queryset
    criteria = Q(status__in=PUBLISHED_STATUSES)
    if permissions["can_add"]:
        criteria |= Q(created_by=username)
    return queryset.filter(criteria)


def _apply_article_values(article, payload, *, creating):
    if not isinstance(payload, dict):
        return "请提交有效的知识文章"
    title = payload.get("title", article.title)
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
        return "标题需要填写 1 至 200 个字符"
    content = payload.get("content", article.content)
    if not isinstance(content, str):
        return "正文需要填写文本"
    content_format = payload.get("content_format", article.content_format)
    if content_format not in KnowledgeArticle.ContentFormat.values:
        return "请选择有效的正文格式"
    category = payload.get("category", article.category)
    if not isinstance(category, str) or len(category.strip()) > 128:
        return "分类最长 128 个字符"
    status = payload.get("status", article.status)
    if "status" in payload and status not in ("draft", "published"):
        return "请选择草稿或已发布状态"
    if creating and status != "draft":
        return "请先保存草稿，再发布文章"
    changed_content = (content, content_format) != (article.content, article.content_format)
    if status in PUBLISHED_STATUSES and (article.status not in PUBLISHED_STATUSES or changed_content):
        if not article.has_publishable_content(content, content_format):
            return "发布前请填写正文"
    article.title, article.content, article.status = title.strip(), content, status
    article.content_format, article.category = content_format, category.strip()
    return ""


def knowledge_resources(request, *, item_id=None):
    domain, username = domain_of(request), request.user.username
    queryset = _article_scope(request)
    if request.method == "GET":
        permissions = _permissions(request)
        visible = _visible_articles(queryset, permissions, username)
        if item_id is not None:
            return WebUtils.response_success(_detail(request, get_object_or_404(visible, id=item_id)))
        categories = list(visible.exclude(category="").order_by("category").values_list("category", flat=True).distinct())
        if keyword := request.GET.get("q", "").strip():
            visible = visible.filter(title__icontains=keyword)
        if category := request.GET.get("category", "").strip():
            visible = visible.filter(category=category)
        status = request.GET.get("status")
        if status == "published":
            visible = visible.filter(status__in=PUBLISHED_STATUSES)
        elif status == "draft":
            visible = visible.exclude(status__in=PUBLISHED_STATUSES)
        page_size = min(100, max(1, int(request.GET.get("page_size") or 20)))
        paginator = Paginator(visible.defer("content").order_by("-updated_at", "-id"), page_size)
        page = paginator.get_page(request.GET.get("page", 1))
        return WebUtils.response_success(
            {
                "items": [_contents(article) for article in page],
                "count": paginator.count,
                "categories": categories,
                "can_link_tickets": has_permission(request, "ticket-View"),
                **permissions,
            }
        )

    return _write_article(request, queryset, domain, username, item_id=item_id)


@transaction.atomic
def _write_article(request, queryset, domain, username, *, item_id):
    creating = item_id is None
    allowed_methods = {"POST"} if creating else {"PUT", "PATCH", "DELETE"}
    if request.method not in allowed_methods:
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    if creating:
        article = KnowledgeArticle(domain=domain, created_by=username)
    else:
        article = get_object_or_404(queryset.select_for_update(), id=item_id)
    if request.method == "DELETE":
        queue_attachment_cleanup(article.attachments.values_list("object_name", flat=True))
        article.delete()
        return WebUtils.response_success({"id": item_id})
    payload = json.loads(request.body or b"{}")
    error = _apply_article_values(article, payload, creating=creating)
    if error:
        return WebUtils.response_error(error_message=error)
    visible_tickets = None
    if "ticket_ids" in payload:
        raw_ids = payload["ticket_ids"]
        if not isinstance(raw_ids, list) or any(type(ticket_id) is not int or not 1 <= ticket_id <= MAX_TICKET_ID for ticket_id in raw_ids):
            return WebUtils.response_error(error_message="请选择有效的关联工单")
        selected_tickets = set(raw_ids)
        if has_permission(request, "ticket-View"):
            visible_tickets = ticket_scope(request)
            if visible_tickets.filter(pk__in=selected_tickets).count() != len(selected_tickets):
                raise PermissionError()
        elif selected_tickets:
            raise PermissionError()
    article.updated_by = username
    article.updated_by_domain = domain
    article.save()
    if visible_tickets is not None:
        existing_tickets = set(article.tickets.filter(pk__in=visible_tickets).values_list("pk", flat=True))
        article.tickets.remove(*(existing_tickets - selected_tickets))
        article.tickets.add(*(selected_tickets - existing_tickets))
    return WebUtils.response_success(_detail(request, article))


def _require_attachment_editor(request, article_id, *, lock=True):
    if not (has_permission(request, "knowledge-Edit") or has_permission(request, "knowledge-Add")):
        raise PermissionError()
    articles = _article_scope(request)
    article = get_object_or_404(articles.select_for_update() if lock else articles, pk=article_id)
    if not _can_manage_attachments(request, article):
        raise PermissionError()
    return article


@csrf_exempt
@require_POST
@api_errors
@HasPermission("knowledge-View")
def upload_knowledge_attachment(request, article_id):
    article = _require_attachment_editor(request, article_id, lock=False)
    upload = request.FILES.get("file")
    if upload is None:
        return WebUtils.response_error(error_message="请选择附件")
    if not attachment_type_allowed(article.domain, upload.name):
        return WebUtils.response_error("文件扩展名不在允许的附件类型中")
    if upload.size > MAX_ATTACHMENT_SIZE:
        return WebUtils.response_error(error_message="附件不得超过 20 MB")
    if not settings.MINIO_ACCESS_KEY or not settings.MINIO_SECRET_KEY:
        return WebUtils.response_error(error_message="对象存储未配置", status_code=502)
    reservation = reserve_upload(f"knowledge/{article.id}/{uuid4().hex}")
    try:
        with transaction.atomic():
            # 清理任务与上传共用这把锁，避免回收仍在传输的对象。
            intent = KnowledgeAttachmentCleanup.objects.select_for_update().get(pk=reservation.pk)
            storage_client().put_object(BUCKET, intent.object_name, upload, upload.size, content_type="application/octet-stream")
            article = _require_attachment_editor(request, article_id)
            item = article.attachments.create(name=upload.name, size=upload.size, object_name=intent.object_name)
            intent.delete()
    except Exception:
        try:
            cleanup_attachment(reservation.object_name, force=True)
        except Exception as error:
            logger.warning(
                "event=itsm_knowledge_attachment_cleanup_failed cleanup_id=%s failed_stage=%s error_type=%s",
                reservation.pk,
                "compensate_upload",
                type(error).__name__,
                exc_info=safe_exception_info(error),
            )
        raise
    return WebUtils.response_success(_attachment_data(item, can_delete=True))


@csrf_exempt
@require_http_methods(["DELETE"])
@api_errors
@HasPermission("knowledge-View")
@transaction.atomic
def delete_knowledge_attachment(request, article_id, attachment_id):
    article = _require_attachment_editor(request, article_id)
    item = get_object_or_404(article.attachments, pk=attachment_id)
    queue_attachment_cleanup([item.object_name])
    item.delete()
    return WebUtils.response_success({"deleted": True})


@require_GET
@api_errors
@HasPermission("knowledge-View")
def download_knowledge_attachment(request, article_id, attachment_id):
    visible = _visible_articles(_article_scope(request), _permissions(request), request.user.username)
    article = get_object_or_404(visible, pk=article_id)
    item = get_object_or_404(article.attachments, pk=attachment_id)
    response = WebUtils.response_success({"url": download_url(item)})
    response["Cache-Control"] = "no-store"
    return response
