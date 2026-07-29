from apps.operation_analysis.common.audit_log import log_ops_analysis_operation


def log_share_access(
    request,
    *,
    action: str,
    link=None,
    principal=None,
    visitor=None,
    result: str = "ok",
    reason: str = "",
    dashboard=None,
):
    """分享访问审计：双身份写入 summary，不记录原始 token。"""
    actor = visitor or getattr(request, "user", None)
    visitor_name = getattr(actor, "username", "") or ""
    visitor_domain = getattr(actor, "domain", "") or ""

    sharer_name = ""
    sharer_domain = ""
    link_id = ""
    space_id = ""
    tenant = ""
    resource_type = ""
    resource_id = ""

    if principal is not None:
        sharer_name = getattr(principal.user, "username", "") or ""
        sharer_domain = getattr(principal.user, "domain", "") or ""
        link_id = str(getattr(principal.link, "id", "") or "")
        space_id = str(getattr(principal, "space_id", "") or "")
        tenant = getattr(principal, "tenant_domain", "") or ""
        resource_type = getattr(principal, "resource_type", "") or ""
        resource_id = str(getattr(getattr(principal, "resource", None), "id", "") or "")
        if not resource_id:
            resource_id = str(getattr(principal.link, "dashboard_instance_id", "") or "")
    elif link is not None:
        sharer_name = getattr(link, "sharer_username", "") or ""
        sharer_domain = getattr(link, "sharer_domain", "") or ""
        link_id = str(getattr(link, "id", "") or "")
        space_id = str(getattr(link, "space_id", "") or "")
        tenant = getattr(link, "tenant_domain", "") or ""
        resource_type = getattr(link, "resource_type", "") or ""
        resource_id = str(getattr(link, "dashboard_instance_id", "") or "")

    if dashboard is not None and not resource_id:
        resource_id = str(getattr(dashboard, "id", "") or "")
        if not resource_type:
            resource_type = "dashboard"

    summary = (
        f"dashboard_share action={action} result={result}"
        f" link_id={link_id} resource_type={resource_type} resource_id={resource_id}"
        f" space_id={space_id} tenant={tenant}"
        f" sharer={sharer_name}@{sharer_domain}"
        f" visitor={visitor_name}@{visitor_domain}"
    )
    if reason:
        summary = f"{summary} reason={reason}"

    action_type = "execute" if action not in {"create", "update", "delete"} else action
    if action == "create":
        action_type = "create"
    log_ops_analysis_operation(request, action_type, summary)
