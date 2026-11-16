"""按域编排服务工作台；所有工单聚合沿用工单查看范围。"""
import base64
import binascii
import io
import json
from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from PIL import Image, UnidentifiedImageError

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import ItsmSetting
from apps.itsm.models.extend import Announcement
from apps.itsm.services.ticket.listing import personal_group
from apps.itsm.views.access import api_errors, domain_of, has_permission, method_permission, ticket_scope

WIDGETS = {"stats", "services", "todo", "tickets", "trend", "announcements", "quick", "recents", "favorites"}
DEFAULT_LAYOUT = {
    "title": "服务工作台",
    "subtitle": "发现所需服务，让每一次协作更高效",
    "background": "blue",
    "widgets": [
        {"type": key, "width": width}
        for key, width in [
            ("stats", 12),
            ("services", 12),
            ("todo", 6),
            ("announcements", 6),
            ("trend", 6),
            ("tickets", 6),
            ("quick", 12),
            ("recents", 6),
            ("favorites", 6),
        ]
    ],
}


def validate_layout(value):
    if not isinstance(value, dict) or set(value) != {"title", "subtitle", "background", "widgets"}:
        raise ValueError("门户配置无效")
    for key, limit in [("title", 60), ("subtitle", 160), ("background", 1500000)]:
        if not isinstance(value[key], str) or len(value[key]) > limit:
            raise ValueError("门户配置超出限制")
    if not value["title"].strip():
        raise ValueError("请填写标题")
    widgets = value["widgets"]
    if not isinstance(widgets, list) or len(widgets) > len(WIDGETS):
        raise ValueError("组件数量无效")
    seen = set()
    for item in widgets:
        if not isinstance(item, dict) or set(item) != {"type", "width"} or item["type"] not in WIDGETS or item["width"] not in [6, 12]:
            raise ValueError("组件配置无效")
        if item["type"] in seen:
            raise ValueError("组件不能重复")
        seen.add(item["type"])
    background = value["background"]
    if background not in {"", "blue", "violet", "mint"}:
        try:
            header, content = background.split(",", 1)
            if header not in {"data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"}:
                raise ValueError("图片格式无效")
            raw = base64.b64decode(content, validate=True)
            if len(raw) > 1024 * 1024:
                raise ValueError("图片不能超过 1 MB")
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > 16000000:
                    raise ValueError("图片尺寸超出限制")
                image.verify()
        except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("图片无效") from exc
    return value


@csrf_exempt
@api_errors
@method_permission("portal-View", "workflow-Edit")
def portal_layout(request):
    if request.method == "GET":
        setting = ItsmSetting.objects.filter(domain=domain_of(request), key="portal_layout").first()
        return WebUtils.response_success(setting.value if setting else DEFAULT_LAYOUT)
    if request.method != "PUT":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    value = validate_layout(json.loads(request.body))
    ItsmSetting.objects.update_or_create(
        domain=domain_of(request), key="portal_layout", defaults={"value": value, "updated_by": request.user.username}
    )
    return WebUtils.response_success(value)


@api_errors
@HasPermission("portal-View")
def portal_dashboard(request):
    query = ticket_scope(request) if has_permission(request, "ticket-View") else ticket_scope(request).none()
    todo = personal_group(query, "mine", request.user.username)
    stats = query.aggregate(
        total=Count("id"),
        finished=Count("id", filter=Q(status__key="finished")),
        active=Count("id", filter=Q(status__key__in=["new", "processing", "suspended"])),
    )
    stats["todo"] = todo.count()
    today = timezone.localdate()
    since = today - timedelta(days=13)

    def counts(field):
        return {
            item["day"]: item["count"]
            for item in query.filter(**{field + "__date__gte": since}).annotate(day=TruncDate(field)).values("day").annotate(count=Count("id"))
        }

    created, finished = counts("created_at"), counts("finished_at")

    def items(qs):
        return [
            {
                "id": item.id,
                "sn": item.sn,
                "title": item.title,
                "status": item.status.name if item.status else "—",
                "created_at": item.created_at.isoformat(),
            }
            for item in qs.select_related("status").only("id", "sn", "title", "status__name", "created_at").order_by("-id")[:6]
        ]

    return WebUtils.response_success(
        {
            "stats": stats,
            "tickets": items(query),
            "todo": items(todo),
            "trend": [
                {"date": (day := since + timedelta(days=offset)).isoformat(), "created": created.get(day, 0), "finished": finished.get(day, 0)}
                for offset in range(14)
            ],
            "announcements": list(
                Announcement.objects.filter(domain=domain_of(request), is_enabled=True)
                .order_by("-id")
                .values("id", "title", "content", "created_at")[:8]
            ),
            "can_view_tickets": has_permission(request, "ticket-View"),
        }
    )
