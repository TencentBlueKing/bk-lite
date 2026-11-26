from django.core.paginator import Paginator
from django.db.models import BigIntegerField
from django.db.models.functions import Coalesce
from django.views.decorators.http import require_GET

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import TriggerLog
from apps.itsm.services.trigger_catalog import CatalogPage, trigger_option_catalog
from apps.itsm.views.access import api_errors, domain_of, get_ticket


@require_GET
@api_errors
@HasPermission("rule-View")
def trigger_options(request):
    return WebUtils.response_success(trigger_option_catalog(domain_of(request), request.user, CatalogPage.parse(request.GET)))


@require_GET
@api_errors
@HasPermission("ticket-View")
def trigger_logs(request, ticket_id):
    ticket = get_ticket(request, ticket_id)
    queryset = (
        TriggerLog.objects.filter(ticket_id=ticket.id, domain=ticket.domain)
        .annotate(occurrence=Coalesce("run_id", "id", output_field=BigIntegerField()))
        .order_by("-occurrence", "position", "id")
    )
    page_size = max(1, min(100, int(request.GET.get("page_size") or 20)))
    paginator = Paginator(queryset, page_size)
    page = paginator.get_page(int(request.GET.get("page") or 1))
    items = [
        {
            "id": log.id,
            "run_id": log.run_id,
            "trigger_name": log.trigger_name,
            "event": log.event,
            "action": log.action,
            "position": log.position,
            "status": log.status,
            "message": log.message,
            "created_at": log.created_at.isoformat(),
        }
        for log in page
    ]
    return WebUtils.response_success({"items": items, "count": paginator.count})
