from django.db.models import Q
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.itsm.models import TicketStatus
from apps.itsm.serializers import TicketStatusSerializer, UserSearchSerializer
from apps.itsm.views.base import ItsmAPIView
from apps.itsm.services.notify.recipients import active_users

PAGE_SIZE = 10


def search_users(request, queryset):
    keyword = (request.GET.get("q") or "").strip()
    try:
        page = max(int(request.GET.get("page") or 1), 1)
    except (TypeError, ValueError):
        page = 1
    if keyword:
        queryset = queryset.filter(Q(username__icontains=keyword) | Q(display_name__icontains=keyword))
    total = queryset.count()
    start = (page - 1) * PAGE_SIZE
    items = queryset.order_by("username")[start : start + PAGE_SIZE] if start < total else []
    return {"items": UserSearchSerializer(items, many=True).data, "count": total, "page": page, "page_size": PAGE_SIZE}


class UserSearchView(ItsmAPIView):
    @HasPermission("portal-View,ticket-View,workflow-Edit,duty-Add,duty-Edit,org-Edit,rule-Add,rule-Edit")
    def get(self, request):
        queryset = active_users(request.user.domain)
        return Response(search_users(request, queryset))


class PublicStatusView(ItsmAPIView):
    @HasPermission("ticket-View")
    def get(self, request):
        items = TicketStatus.objects.order_by("order", "id")
        return Response({"items": TicketStatusSerializer(items, many=True).data})
