# -- coding: utf-8 --
# @File: alter_operator.py
# @Time: 2025/5/28 16:31
# @Author: windyzhao

from django.utils import timezone
from django.db import transaction

from apps.alerts.models.alert_operator import AlertAssignment
from apps.alerts.models.models import Alert
from apps.alerts.utils.operator_log import record_operator_log
from apps.alerts.constants.constants import (
    AlertStatus,
    AlertOperate,
    LogTargetType,
    LogAction,
)
from apps.alerts.service.base import get_default_notify_params
from apps.alerts.utils.operator_scope import validate_alert_assignees
from apps.core.logger import alert_logger as logger


class AlertOperator(object):
    """
    告警操作类 做告警的操作
    完成手动的过程：
    待响应——处理中——关闭
    未分派——待响应——处理中——关闭
    待响应——处理中——转派——待响应——处理中——关闭
    未分派——待响应——处理中——转派——待响应——处理中——关闭
    """

    def __init__(self, user, allowed_alert_ids=None):
        self.user = user
        self.status_map = dict(AlertStatus.CHOICES)
        self.allowed_alert_ids = None if allowed_alert_ids is None else {str(item) for item in allowed_alert_ids}

    def _is_alert_allowed(self, alert_id: str) -> bool:
        if self.allowed_alert_ids is None:
            return True
        return str(alert_id) in self.allowed_alert_ids

    def operate(self, action: str, alert_id: str, data: dict) -> dict:
        """
        执行告警操作
        :param alert_id: 告警ID
        :param action: 操作类型
        :param data: 附加数据
        :return: 操作结果
        """
        logger.info(
            "[AlertOperator] 用户 %s 开始执行告警操作: action=%s, alert_id=%s",
            self.user, action, alert_id,
        )

        # 查找对应的操作方法
        func = getattr(self, f"_{action}_alert", None)
        if not func:
            logger.error("[AlertOperator] 不支持的操作类型: %s", action)
            raise ValueError(f"Unsupported action: {action}")

        if not self._is_alert_allowed(alert_id):
            logger.warning("[AlertOperator] 用户 %s 无权限操作告警: alert_id=%s", self.user, alert_id)
            return {"result": False, "message": "您没有权限操作此告警", "data": {}}

        try:
            result = func(alert_id, data)
            logger.info(
                "[AlertOperator] 告警操作执行成功: action=%s, alert_id=%s, result=%s",
                action, alert_id, result,
            )
            return result
        except Exception as e:
            logger.error(
                "[AlertOperator] 告警操作执行失败: action=%s, alert_id=%s, error=%s",
                action, alert_id, e,
                exc_info=True,
            )
            raise

    @staticmethod
    def get_alert(alert_id) -> Alert:
        """
        获取告警对象并加锁，告警不存在时抛出 Alert.DoesNotExist
        """
        return Alert.objects.select_for_update().get(alert_id=alert_id)

    def _create_reminder_record(self, alert: Alert, assignment):
        """创建提醒记录（assignment 已由调用方查出并校验 is_active）"""
        try:
            from apps.alerts.service.reminder_service import ReminderService

            ReminderService.create_reminder_task(alert, assignment)
        except Exception:
            logger.exception("[AlertOperator] 创建提醒记录失败: alert_id=%s", alert.alert_id)

    def _stop_reminder_tasks(self, alert: Alert):
        """停止告警的提醒任务"""
        try:
            from apps.alerts.service.reminder_service import ReminderService

            ReminderService.stop_reminder_task(alert)
        except Exception as e:
            logger.error("[AlertOperator] 停止提醒任务失败: %s", e, exc_info=True)

    def _ensure_reminder_tasks(self, alert: Alert, assignment_id: str = None):
        """恢复或创建告警的提醒任务"""
        try:
            from apps.alerts.service.reminder_service import ReminderService

            normalized_assignment_id = None
            if assignment_id not in (None, ""):
                try:
                    normalized_assignment_id = int(assignment_id)
                except (TypeError, ValueError):
                    logger.warning(
                        "[AlertOperator] 提醒任务恢复失败，assignment_id 非法: alert_id=%s, assignment_id=%s",
                        alert.alert_id,
                        assignment_id,
                    )

            ReminderService.ensure_reminder_task(
                alert, assignment_id=normalized_assignment_id
            )
        except Exception as e:
            logger.error("[AlertOperator] 恢复提醒任务失败: %s", e, exc_info=True)

    def _create_escalation_task(self, alert: Alert, assignment):
        """分派时创建升级任务（assignment 已由调用方查出并校验 is_active）"""
        try:
            from apps.alerts.service.escalation_service import EscalationService

            EscalationService.create_escalation_task(alert, assignment)
        except Exception:
            logger.exception("[AlertOperator] 创建升级任务失败: alert_id=%s", alert.alert_id)

    def _stop_escalation_tasks(self, alert: Alert):
        """认领/解决/关闭后停止升级任务"""
        try:
            from apps.alerts.service.escalation_service import EscalationService

            EscalationService.stop_escalation_task(alert)
        except Exception as e:
            logger.error("[AlertOperator] 停止升级任务失败: %s", e, exc_info=True)

    def _reset_escalation_tasks(self, alert: Alert, assignment_id: str = None):
        """改派后升级计时重置到第一层"""
        try:
            from apps.alerts.service.escalation_service import EscalationService

            assignment = None
            if assignment_id not in (None, ""):
                assignment = AlertAssignment.objects.filter(
                    id=assignment_id, is_active=True
                ).first()
            EscalationService.reset_escalation_task(alert, assignment)
        except Exception as e:
            logger.error("[AlertOperator] 重置升级任务失败: %s", e, exc_info=True)

    def _assign_alert(self, alert_id: str, data: dict) -> dict:
        """
        分派告警：未分派 -> 待响应
        """
        logger.info("[AlertOperator] 开始分派告警: alert_id=%s", alert_id)

        with transaction.atomic():
            try:
                alert = self.get_alert(alert_id)
            except Alert.DoesNotExist:
                logger.error("[AlertOperator] 告警不存在: alert_id=%s", alert_id)
                return {"result": False, "message": "告警不存在", "data": {}}

            # 检查当前状态
            if alert.status != AlertStatus.UNASSIGNED:
                logger.warning(
                    "[AlertOperator] 告警状态不符合分派条件: alert_id=%s, current_status=%s",
                    alert_id, alert.status,
                )
                return {
                    "result": False,
                    "message": f"告警当前状态为{alert.get_status_display()}，无法进行分派操作",
                    "data": {},
                }

            # 获取分派人信息
            assignee = data.get("assignee", [])

            if not assignee:
                return {"result": False, "message": "请指定处理人", "data": {}}

            assignee, validation_message = validate_alert_assignees(alert, assignee)
            if validation_message:
                return {"result": False, "message": validation_message, "data": {}}

            # 更新告警状态和处理人
            alert.status = AlertStatus.PENDING
            alert.operate = AlertOperate.ASSIGN
            alert.operator = assignee
            alert.updated_at = timezone.now()
            alert.save()

            # 创建提醒记录（一次查出策略对象，复用给提醒/升级/通知，避免重复查询）
            assignment_id = data.get("assignment_id")  # 分派策略ID
            assignment = None
            if assignment_id:
                assignment = AlertAssignment.objects.filter(id=assignment_id, is_active=True).first()
                if assignment:
                    self._create_reminder_record(alert, assignment)
                    self._create_escalation_task(alert, assignment)
                else:
                    logger.error("[AlertOperator] 分派策略不存在或未激活: assignment_id=%s", assignment_id)

            from apps.alerts.action.engine import ActionEngine

            transaction.on_commit(lambda aid=alert.alert_id: ActionEngine.dispatch_async(aid, "assigned"))

            # 通知分流：auto-dispatch(有策略) 严格按勾选的通知方式发(勾哪个发哪个,含 opspilot)；
            # manual(无策略) 维持默认邮件。
            if assignment:
                notify_param = self.format_assignment_notify_data(assignment, assignee, alert)
            else:
                notify_param = self.format_notify_data(assignee, alert)
            if notify_param:
                from apps.alerts.common.notify.dispatcher import enqueue_notifications

                enqueue_notifications(notify_param)
            else:
                logger.warning(
                    "[AlertOperator] 分派通知无可用渠道，未发送！alert_id=%s, assignee=%s, assignment_id=%s",
                    alert_id, assignee, assignment_id,
                )

            logger.info(
                "[AlertOperator] 告警分派成功: alert_id=%s, assignee=%s, 状态变更: %s -> %s",
                alert_id, assignee, AlertStatus.UNASSIGNED, AlertStatus.PENDING,
            )

            log_data = {
                "action": LogAction.MODIFY,
                "target_type": LogTargetType.ALERT,
                "operator": self.user,
                "operator_object": "告警处理-分派",
                "target_id": alert.alert_id,
                "overview": f"告警分派成功, 处理人[{assignee}] 告警[{alert.title}]状态变更: {self.status_map[AlertStatus.UNASSIGNED]} -> {self.status_map[AlertStatus.PENDING]}",
            }
            self.operator_log(log_data)

            return {
                "result": True,
                "message": "告警分派成功",
                "data": {
                    "alert_id": alert_id,
                    "status": alert.status,
                    "operator": alert.operator,
                    "updated_at": alert.updated_at.isoformat(),
                },
            }

    def _acknowledge_alert(self, alert_id: str, data: dict) -> dict:
        """
        认领告警：待响应 -> 处理中
        :param alert_id: 告警ID
        :param data: 附加数据
        :return: 操作结果
        """
        logger.info("[AlertOperator] 开始认领告警: alert_id=%s", alert_id)

        with transaction.atomic():
            try:
                alert = self.get_alert(alert_id)
            except Alert.DoesNotExist:
                logger.error("[AlertOperator] 告警不存在: alert_id=%s", alert_id)
                return {"result": False, "message": "告警不存在", "data": {}}

            # 检查当前状态是否为待响应
            if alert.status != AlertStatus.PENDING:
                logger.warning(
                    "[AlertOperator] 告警状态不符合认领条件: alert_id=%s, current_status=%s",
                    alert_id, alert.status,
                )
                return {
                    "result": False,
                    "message": f"告警当前状态为{alert.get_status_display()}，无法进行认领操作",
                    "data": {},
                }

            # 检查是否有权限认领（是否在处理人列表中）
            if self.user not in alert.operator:
                logger.warning(
                    "[AlertOperator] 用户无权限认领告警: alert_id=%s, user=%s, operators=%s",
                    alert_id, self.user, alert.operator,
                )
                return {"result": False, "message": "您没有权限认领此告警", "data": {}}

            # 更新告警状态
            alert.status = AlertStatus.PROCESSING
            alert.operate = AlertOperate.ACKNOWLEDGE
            alert.updated_at = timezone.now()
            alert.save()

            from apps.alerts.action.engine import ActionEngine

            transaction.on_commit(lambda aid=alert.alert_id: ActionEngine.dispatch_async(aid, "acknowledged"))

            logger.info(
                "[AlertOperator] 告警认领成功: alert_id=%s, user=%s, 状态变更: %s -> %s",
                alert_id, self.user, AlertStatus.PENDING, AlertStatus.PROCESSING,
            )

            # 停止相关的提醒任务
            self._stop_reminder_tasks(alert)
            self._stop_escalation_tasks(alert)

            log_data = {
                "action": LogAction.MODIFY,
                "target_type": LogTargetType.ALERT,
                "operator": self.user,
                "operator_object": "告警处理-认领",
                "target_id": alert.alert_id,
                "overview": f"告警认领成功, 认领人[{self.user}] 告警[{alert.title}]状态变更: {self.status_map[AlertStatus.PENDING]} -> {self.status_map[AlertStatus.PROCESSING]}",
            }
            self.operator_log(log_data)

            return {
                "result": True,
                "message": "告警认领成功",
                "data": {
                    "alert_id": alert_id,
                    "status": alert.status,
                    "updated_at": alert.updated_at.isoformat(),
                },
            }

    def _reassign_alert(self, alert_id: str, data: dict) -> dict:
        """
        转派告警：处理中 -> 待响应（重新分配处理人）
        :param alert_id: 告警ID
        :param data: 包含新处理人信息的数据
        :return: 操作结果
        """
        logger.info("[AlertOperator] 开始转派告警: alert_id=%s", alert_id)

        with transaction.atomic():
            try:
                alert = self.get_alert(alert_id)
            except Alert.DoesNotExist:
                logger.error("[AlertOperator] 告警不存在: alert_id=%s", alert_id)
                return {"result": False, "message": "告警不存在", "data": {}}

            # 检查当前状态是否为处理中
            if alert.status != AlertStatus.PROCESSING:
                logger.warning(
                    "[AlertOperator] 告警状态不符合转派条件: alert_id=%s, current_status=%s",
                    alert_id, alert.status,
                )
                return {
                    "result": False,
                    "message": f"告警当前状态为{alert.get_status_display()}，无法进行转派操作",
                    "data": {},
                }

            # 检查是否有权限转派（是否为当前处理人）
            if self.user not in alert.operator:
                logger.warning(
                    "[AlertOperator] 用户无权限转派告警: alert_id=%s, user=%s, operators=%s",
                    alert_id, self.user, alert.operator,
                )
                return {"result": False, "message": "您没有权限转派此告警", "data": {}}

            # 获取新的处理人信息
            new_assignee = data.get("assignee", [])
            if not new_assignee:
                logger.warning("[AlertOperator] 转派操作缺少新处理人信息: alert_id=%s", alert_id)
                return {"result": False, "message": "请指定新的处理人", "data": {}}

            new_assignee, validation_message = validate_alert_assignees(alert, new_assignee)
            if validation_message:
                return {"result": False, "message": validation_message, "data": {}}

            old_assignee = alert.operator.copy()

            # 更新告警状态和处理人
            alert.status = AlertStatus.PENDING
            alert.operate = AlertOperate.REASSIGN
            alert.operator = new_assignee
            alert.updated_at = timezone.now()
            alert.save()

            from apps.alerts.action.engine import ActionEngine

            transaction.on_commit(lambda aid=alert.alert_id: ActionEngine.dispatch_async(aid, "reassigned"))

            logger.info(
                "[AlertOperator] 告警转派成功: alert_id=%s, old_assignee=%s, new_assignee=%s, 状态变更: %s -> %s",
                alert_id, old_assignee, new_assignee, AlertStatus.PROCESSING, AlertStatus.PENDING,
            )

            notify_param = self.format_notify_data(new_assignee, alert)
            if notify_param:
                from apps.alerts.common.notify.dispatcher import enqueue_notifications

                enqueue_notifications(notify_param)
            else:
                logger.warning(
                    "[AlertOperator] 未找到有效的email通知参数，邮件通知失败！alert_id=%s, assignee=%s",
                    alert_id, new_assignee,
                )

            assignment_id = data.get("assignment_id")
            self._ensure_reminder_tasks(alert, assignment_id)
            self._reset_escalation_tasks(alert, assignment_id)

            log_data = {
                "action": LogAction.MODIFY,
                "target_type": LogTargetType.ALERT,
                "operator": self.user,
                "operator_object": "告警处理-转派",
                "target_id": alert.alert_id,
                "overview": f"告警转派成功, 转派处理人[{new_assignee}] 告警[{alert.title}]状态变更: {self.status_map[AlertStatus.PROCESSING]} -> {self.status_map[AlertStatus.PENDING]}",
            }
            self.operator_log(log_data)

            return {
                "result": True,
                "message": "告警转派成功",
                "data": {
                    "alert_id": alert_id,
                    "status": alert.status,
                    "old_operator": old_assignee,
                    "new_operator": alert.operator,
                    "updated_at": alert.updated_at.isoformat(),
                },
            }

    def _close_alert(self, alert_id: str, data: dict) -> dict:
        """
        关闭告警：处理中 -> 已关闭
        :param alert_id: 告警ID
        :param data: 附加数据（可包含关闭原因等）
        :return: 操作结果
        """
        logger.info("[AlertOperator] 开始关闭告警: alert_id=%s", alert_id)

        with transaction.atomic():
            try:
                alert = self.get_alert(alert_id)
            except Alert.DoesNotExist:
                logger.error("[AlertOperator] 告警不存在: alert_id=%s", alert_id)
                return {"result": False, "message": "告警不存在", "data": {}}

            # 检查当前状态是否为处理中
            if alert.status != AlertStatus.PROCESSING:
                logger.warning(
                    "[AlertOperator] 告警状态不符合关闭条件: alert_id=%s, current_status=%s",
                    alert_id, alert.status,
                )
                return {
                    "result": False,
                    "message": f"告警当前状态为{alert.get_status_display()}，无法进行关闭操作",
                    "data": {},
                }

            # 检查是否有权限关闭（是否为当前处理人）
            if self.user not in alert.operator:
                logger.warning(
                    "[AlertOperator] 用户无权限关闭告警: alert_id=%s, user=%s, operators=%s",
                    alert_id, self.user, alert.operator,
                )
                return {"result": False, "message": "您没有权限关闭此告警", "data": {}}

            # 记录关闭原因
            close_reason = data.get("reason", "告警已处理完成")

            # 更新告警状态
            alert.status = AlertStatus.CLOSED
            alert.operate = AlertOperate.CLOSE
            alert.updated_at = timezone.now()
            alert.save()

            from apps.alerts.action.engine import ActionEngine

            transaction.on_commit(lambda aid=alert.alert_id: ActionEngine.dispatch_async(aid, "closed"))

            logger.info(
                "[AlertOperator] 告警关闭成功: alert_id=%s, user=%s, reason=%s, 状态变更: %s -> %s",
                alert_id, self.user, close_reason, AlertStatus.PROCESSING, AlertStatus.CLOSED,
            )

            log_data = {
                "action": LogAction.MODIFY,
                "target_type": LogTargetType.ALERT,
                "operator": self.user,
                "operator_object": "告警处理-关闭",
                "target_id": alert.alert_id,
                "overview": f"告警关闭成功, 告警[{alert.title}]状态变更: {self.status_map[AlertStatus.PROCESSING]} -> {self.status_map[AlertStatus.CLOSED]}",
            }
            self.operator_log(log_data)

            return {
                "result": True,
                "message": "告警关闭成功",
                "data": {
                    "alert_id": alert_id,
                    "status": alert.status,
                    "close_reason": close_reason,
                    "updated_at": alert.updated_at.isoformat(),
                },
            }

    def _resolve_alert(self, alert_id: str, data: dict) -> dict:
        """
        处理告警：处理中 -> 已处理
        :param alert_id: 告警ID
        :param data: 附加数据（可包含处理说明等）
        :return: 操作结果
        """
        logger.info("[AlertOperator] 开始处理告警: alert_id=%s", alert_id)

        with transaction.atomic():
            try:
                alert = self.get_alert(alert_id)
            except Alert.DoesNotExist:
                logger.error("[AlertOperator] 告警不存在: alert_id=%s", alert_id)
                return {"result": False, "message": "告警不存在", "data": {}}

            # 检查当前状态是否为处理中
            if alert.status != AlertStatus.PROCESSING:
                logger.warning(
                    "[AlertOperator] 告警状态不符合处理条件: alert_id=%s, current_status=%s",
                    alert_id, alert.status,
                )
                return {
                    "result": False,
                    "message": f"告警当前状态为{alert.get_status_display()}，无法标记为已处理",
                    "data": {},
                }

            # 检查是否有权限处理（是否为当前处理人）
            if self.user not in alert.operator:
                logger.warning(
                    "[AlertOperator] 用户无权限处理告警: alert_id=%s, user=%s, operators=%s",
                    alert_id, self.user, alert.operator,
                )
                return {"result": False, "message": "您没有权限处理此告警", "data": {}}

            # 记录处理说明
            resolve_note = data.get("note", "告警问题已解决")

            # 更新告警状态
            alert.status = AlertStatus.RESOLVED
            alert.updated_at = timezone.now()
            alert.save()

            from apps.alerts.action.engine import ActionEngine

            transaction.on_commit(lambda aid=alert.alert_id: ActionEngine.dispatch_async(aid, "resolved"))

            logger.info(
                "[AlertOperator] 告警处理成功: alert_id=%s, user=%s, note=%s, 状态变更: %s -> %s",
                alert_id, self.user, resolve_note, AlertStatus.PROCESSING, AlertStatus.RESOLVED,
            )

            log_data = {
                "action": LogAction.MODIFY,
                "target_type": LogTargetType.ALERT,
                "operator": self.user,
                "operator_object": "告警处理-已处理",
                "target_id": alert.alert_id,
                "overview": f"告警处理成功, 告警[{alert.title}]状态变更: {self.status_map[AlertStatus.PROCESSING]} -> {self.status_map[AlertStatus.RESOLVED]}",
            }
            self.operator_log(log_data)

            return {
                "result": True,
                "message": "告警处理成功",
                "data": {
                    "alert_id": alert_id,
                    "status": alert.status,
                    "resolve_note": resolve_note,
                    "updated_at": alert.updated_at.isoformat(),
                },
            }

    def format_notify_data(self, assignee, alert):
        """
        格式化通知数据。走统一通知出口,返回 sync_notify 期望的 list[dict];
        无渠道或无接收人 → 返回 []。
        """
        from apps.alerts.common.notify.dispatcher import build_channel_params

        channel, channel_id = get_default_notify_params()
        if not channel_id:
            return []
        user_list = [i for i in assignee if i != self.user]
        return build_channel_params(
            user_list,
            [{"channel_type": channel, "id": channel_id}],
            [alert],
            alert.alert_id,
        )

    def format_assignment_notify_data(self, assignment, assignee, alert):
        """auto-dispatch：严格按分派策略勾选的通知方式(notify_channels)构造通知，
        勾哪个发哪个(含 opspilot)；无策略 / 无渠道 / 无接收人 → 返回 []。"""
        from apps.alerts.common.notify.dispatcher import build_channel_params

        if not assignment:
            logger.info("[AlertNotify] 分派通知: 无有效策略, 不发送, alert_id=%s", alert.alert_id)
            return []
        channels = assignment.notify_channels or []
        user_list = [i for i in assignee if i != self.user]
        logger.info(
            "[AlertNotify] 分派通知构造: alert_id=%s, assignment_id=%s, team=%s, notify_channels=%s, 接收人=%s",
            alert.alert_id, assignment.id, alert.team, channels, user_list,
        )
        params = build_channel_params(user_list, channels, [alert], alert.alert_id)
        logger.info(
            "[AlertNotify] 分派通知构造结果: alert_id=%s, 参数数=%s, 渠道=%s",
            alert.alert_id, len(params), [(p.get("channel_type"), p.get("channel_id")) for p in params],
        )
        return params

    @staticmethod
    def operator_log(log_data: dict):
        """
        记录告警操作日志
        :param log_data: 日志数据字典
        """
        record_operator_log(**log_data)
