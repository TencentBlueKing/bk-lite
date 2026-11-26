from django.views.decorators.http import require_GET

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.views.access import api_errors, get_ticket


@require_GET
@api_errors
@HasPermission("ticket-View")
@HasPermission("asset_info-View", app_name="cmdb")
def ticket_vmware_assets(request, ticket_id):
    from apps.itsm.services.vmware_assets import resolve_cmdb_assets

    ticket = get_ticket(request, ticket_id)
    results = []
    executions = ticket.auto_executions.filter(domain=ticket.domain, kind="external", detail__delivery__has_key="machines").order_by("pk")
    for execution in executions:
        state = execution.detail["delivery"]
        machines = {key: item for key, item in state["machines"].items() if item.get("receipt")}
        if machines:
            links = resolve_cmdb_assets(request, state.get("plan", {}), machines)
            results.extend({"delivery_id": key, "hostname": item["receipt"].get("hostname"), "url": links.get(key)} for key, item in machines.items())
    return WebUtils.response_success({"items": results})
