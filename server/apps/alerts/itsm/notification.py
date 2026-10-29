"""失败通知使用现有渠道 Outbox；提交通知意图时锁内重读授权。"""
from django.db import transaction

from apps.alerts.common.notify.dispatcher import build_channel_params
from apps.alerts.itsm.config import ItsmError, connections, get_connection
from apps.alerts.itsm.service import _teams
from apps.alerts.models.action import ActionExecution
from apps.alerts.models.itsm import AlertItsmTicket
from apps.alerts.models.models import Alert
from apps.alerts.service.outbox import enqueue_outbox
from apps.core.utils.user_group import normalize_user_group_ids
from apps.system_mgmt.models.channel import Channel
from apps.system_mgmt.models.user import User


def notify_failure(execution_id, *, fault_key=None):
    initial = ActionExecution.objects.get(pk=execution_id)
    try:
        with transaction.atomic():
            alert = Alert.objects.select_for_update().get(pk=initial.alert_id)
            link = AlertItsmTicket.objects.select_for_update().filter(alert=alert).first()
            execution = ActionExecution.objects.select_for_update().get(pk=execution_id)
            team = _teams(link.team if link else execution.input_snapshot.get("team"), alert.team)
            reference = execution.input_snapshot.get("config", {}).get("connection")
            if not reference:
                # 快照超限时没有归属规则，只通知该团队部署指定的运维接收人。
                reference = next(
                    (key for key, value in connections(team).items() if team and set(team).issubset(set(map(str, value.get("teams", []))))), None
                )
            conn = get_connection(reference, team)
            notification = conn.get("failure_notification") or {}
            users = list(User.objects.select_for_update().filter(username__in=notification.get("usernames", []), disabled=False).order_by("pk"))
            allowed_users = [user.username for user in users if _teams(normalize_user_group_ids(user.group_list), team)]
            channels = [
                {"id": channel.pk, "channel_type": channel.channel_type}
                for channel in Channel.objects.select_for_update().filter(pk__in=notification.get("channel_ids", [])).order_by("pk")
                if _teams(channel.team, team)
            ]
            if not allowed_users or not channels:
                raise ItsmError("失败通知接收人或渠道未配置，或不在关联团队内")
            message = (link.close_error or link.sync_error) if fault_key and link else execution.result.get("message", "请查看执行记录")
            params = build_channel_params(
                allowed_users,
                channels,
                [alert],
                alert.alert_id,
                title="ITSM 联动异常" if fault_key else "ITSM 建单异常",
                content=f"告警 {alert.alert_id}，执行 {execution.pk}：{message}",
            )
            enqueue_outbox("notification", {"params": params}, f"itsm-notification:{fault_key or execution_id}")
            execution.result = {**execution.result, "notification": "queued"}
            execution.save(update_fields=["result", "updated_at"])
    except ItsmError as exc:
        with transaction.atomic():
            execution = ActionExecution.objects.select_for_update().get(pk=execution_id)
            execution.result = {**execution.result, "notification": str(exc)}
            execution.save(update_fields=["result", "updated_at"])
        raise ItsmError("ITSM 失败通知配置不可用", "failed") from None
