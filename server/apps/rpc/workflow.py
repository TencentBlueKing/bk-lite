"""携带已认证调用者身份的编排中心 NATS 客户端。"""

from rest_framework.exceptions import PermissionDenied

from apps.core.utils.internal_event_auth import sign_internal_event
from apps.rpc.base import RpcClient

NATS_TRIGGER_SCOPE = "workflow.trigger_nats"
MANAGED_NATS_TRIGGER_SCOPE = "workflow.trigger_nats.managed_channel"
MANAGED_NATS_ACTOR = "managed-nats-channel"


def invoke_nats_workflow(request, *, trigger_id, subject, event):
    """在已认证的服务端请求中调用；事件正文不参与用户和组织的选择。"""
    from apps.opspilot.services.caller_identity import capture_caller_identity

    identity = capture_caller_identity(request)
    permissions = getattr(request.user, "permission", set())
    if isinstance(permissions, dict):
        permissions = permissions.get("workflow", set())
    if not getattr(request.user, "is_superuser", False) and "workflow-Execute" not in (permissions or ()):
        raise PermissionDenied("缺少流程执行权限")

    team = identity["team_id"]
    payload = {
        "data": {"trigger_id": str(trigger_id), "subject": subject, "team": team, "event": event},
        "actor_context": {"username": identity["username"], "domain": identity["domain"], "authorized_team_ids": [team]},
    }
    auth = sign_internal_event(NATS_TRIGGER_SCOPE, payload, caller="workflow")
    return RpcClient().run("trigger_orchestration_workflow_by_nats", **payload, internal_auth=auth)
