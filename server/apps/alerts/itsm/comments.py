"""已有工单上的生命周期留言。不改工单流程，失败不改变告警状态。"""

from apps.alerts.itsm.client import ItsmClient
from apps.alerts.itsm.config import ItsmError, get_connection
from apps.alerts.itsm.service import _teams
from apps.alerts.models.itsm import AlertItsmTicket
from apps.alerts.models.models import Alert
from apps.alerts.service.outbox import enqueue_outbox

COMMENT_TEXT = {
    "assigned": "【告警中心】告警已分派。工单流程不因此流转。",
    "acknowledged": "【告警中心】告警已认领。工单流程不因此流转。",
    "resolved": "【告警中心】告警已恢复。工单保持打开。",
    "closed": "【告警中心】告警已关闭。仅同步备注，不改工单状态。",
}


def enqueue_comment(alert, event_name, *, retry_key=""):
    # 原生 ITSM OpenAPI 没有留言接口；入队只会给每个生命周期事件记一条无法重发成功的失败。
    if not ItsmClient.supports_comment or event_name not in COMMENT_TEXT:
        return None
    link = AlertItsmTicket.objects.select_related("rule").filter(alert=alert).exclude(ticket_id="").exclude(ticket_id__isnull=True).first()
    if not link or not link.rule or not link.rule.is_active or event_name not in (link.rule.trigger_events or []):
        return None
    key = f"itsm-comment-retry:{link.pk}:{retry_key}" if retry_key else f"itsm-comment:{link.pk}:{event_name}"
    record, _ = enqueue_outbox("itsm_comment", {"link_id": link.pk, "event_name": event_name}, key)
    return record


def deliver_comment(link_id, event_name):
    content = COMMENT_TEXT.get(event_name)
    if not content:
        return
    link = AlertItsmTicket.objects.filter(pk=link_id).exclude(ticket_id="").first()
    if not link:
        return
    try:
        teams = _teams(link.team, Alert.objects.get(pk=link.alert_id).team)
        connection = get_connection(link.connection, teams, link.instance_id)
        ItsmClient(connection).comment(link.ticket_id, content)
        error = ""
    except Alert.DoesNotExist:
        error = "告警已不存在，无法发送留言"
    except ItsmError as exc:
        error = str(exc)
    AlertItsmTicket.objects.filter(pk=link_id).update(comment_event=event_name, comment_error=error)
