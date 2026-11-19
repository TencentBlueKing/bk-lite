from django.db.models import Q
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.itsm.models import TicketStatus
from apps.itsm.serializers import TicketStatusSerializer, UserSearchSerializer
from apps.itsm.views.base import ItsmAPIView
from apps.system_mgmt.models import User

PAGE_SIZE = 10


class UserSearchView(ItsmAPIView):
    @HasPermission("portal-View,ticket-View,workflow-Edit")
    def get(self, request):
        keyword = (request.GET.get("q") or "").strip()
        try:
            page = max(int(request.GET.get("page") or 1), 1)
        except (TypeError, ValueError):
            page = 1
        queryset = User.objects.filter(domain=request.user.domain, disabled=False)
        if keyword:
            queryset = queryset.filter(Q(username__icontains=keyword) | Q(display_name__icontains=keyword))
        queryset = queryset.order_by("username")
        total = queryset.count()
        start = (page - 1) * PAGE_SIZE
        items = queryset[start : start + PAGE_SIZE]
        return Response(
            {
                "items": UserSearchSerializer(items, many=True).data,
                "count": total,
                "page": page,
                "page_size": PAGE_SIZE,
            }
        )


class PublicStatusView(ItsmAPIView):
    @HasPermission("ticket-View")
    def get(self, request):
        items = TicketStatus.objects.order_by("order", "id")
        return Response({"items": TicketStatusSerializer(items, many=True).data})
