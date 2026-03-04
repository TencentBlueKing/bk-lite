# -- coding: utf-8 --
# @File: alter_operator.py
# @Time: 2025/5/28 16:31
# @Author: windyzhao

from django.utils import timezone
from django.db import transaction

from apps.alerts.common.notify.base import NotifyParamsFormat
from apps.alerts.models.alert_operator import AlertAssignment
from apps.alerts.models.models import Alert
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.constants.constants import (
    AlertStatus,
    AlertOperate,
    LogTargetType,
    LogAction,
)
from apps.alerts.service.base import get_default_notify_params
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

    def __init__(self, user):
        self.user = user
        self.status_map = dict(AlertStatus.CHOICES)

    def operate(self, action: str, alert_id: str, data: dict) -> dict:
        """
        执行告警操作
        :param alert_id: 告警ID
        :param action: 操作类型
        :param data: 附加数据
        :return: 操作结果
        """
        logger.info(
            f"用户 {self.user} 开始执行告警操作: action={action}, alert_id={alert_id}"
        )

        # 查找对应的操作方法
        func = getattr(self, f"_{action}_alert", None)
        if not func:
            logger.error(f"不支持的操作类型: {action}")
            raise ValueError(f"Unsupported action: {action}")

        try:
            result = func(alert_id, data)
            logger.info(
                f"告警操作执行成功: action={action}, alert_id={alert_id}, result={result}"
            )
            return result
        except Exception as e:
            logger.error(
                f"告警操作执行失败: action={action}, alert_id={alert_id}, error={str(e)}"
            )
            raise

    @staticmethod
    def get_alert(alert_id) -> Alert:
        """
        获取告警对象并加锁，告警不存在时抛出 Alert.DoesNotExist
        """
        return Alert.objects.select_for_update().get(alert_id=alert_id)

    def _create_reminder_record(self, alert: Alert, assignment_id: str):
        """创建提醒记录"""
        try:
            from apps.alerts.service.reminder_service import ReminderService

            assignment = AlertAssignment.objects.get(id=assignment_id, is_active=True)
            ReminderService.create_reminder_task(alert, assignment)
        except AlertAssignment.DoesNotExist:
            logger.error(f"分派策略不存在: assignment_id={assignment_id}")
        except Exception as e:
            logger.exception(f"创建提醒记录失败: alert_id={alert.alert_id}")

    def _stop_reminder_tasks(self, alert: Alert):
        """停止告警的提醒任务"""
        try:
            from apps.alerts.service.reminder_service import ReminderService

            ReminderService.stop_reminder_task(alert)
        except Exception as e:
            logger.error(f"停止提醒任务失败: {str(e)}")

    def _assign_alert(self, alert_id: str, data: dict) -> dict:
        """
        分派告警：未分派 -> 待响应
        """
        logger.info(f"开始分派告警: alert_id={alert_id}")

        with transaction.atomic():
            try:
                alert = self.get_alert(alert_id)
            except Alert.DoesNotExist:
                logger.error(f"告警不存在: alert_id={alert_id}")
                return {"result": False, "message": "告警不存在", "data": {}}

            # 检查当前状态
            if alert.status != AlertStatus.UNASSIGNED:
                logger.warning(
                    f"告警状态不符合分派条件: alert_id={alert_id}, current_status={alert.status}"
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

            # 更新告警状态和处理人
            alert.status = AlertStatus.PENDING
            alert.operate = AlertOperate.ASSIGN
            alert.operator = assignee
            alert.updated_at = timezone.now()
            alert.save()

            # 创建提醒记录
            assignment_id = data.get("assignment_id")  # 分派策略ID
            if assignment_id:
                self._create_reminder_record(alert, assignment_id)

            notify_param = self.format_notify_data(assignee, alert)
            if notify_param:
                from apps.alerts.tasks import sync_notify

                transaction.on_commit(lambda: sync_notify.delay(notify_param))
            else:
                logger.warning(
                    f"未找到有效的email通知参数，邮件通知失败！alert_id={alert_id}, assignee={assignee}"
                )

            logger.info(
                f"告警分派成功: alert_id={alert_id}, assignee={assignee}, 状态变更: {AlertStatus.UNASSIGNED} -> {AlertStatus.PENDING}"
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
        logger.info(f"开始认领告警: alert_id={alert_id}")

        with transaction.atomic():
            try:
                alert = self.get_alert(alert_id)
            except Alert.DoesNotExist:
                logger.error(f"告警不存在: alert_id={alert_id}")
                return {"result": False, "message": "告警不存在", "data": {}}

            # 检查当前状态是否为待响应
            if alert.status != AlertStatus.PENDING:
                logger.warning(
                    f"告警状态不符合认领条件: alert_id={alert_id}, current_status={alert.status}"
                )
                return {
                    "result": False,
                    "message": f"告警当前状态为{alert.get_status_display()}，无法进行认领操作",
                    "data": {},
                }

            # 检查是否有权限认领（是否在处理人列表中）
            if self.user not in alert.operator:
                logger.warning(
                    f"用户无权限认领告警: alert_id={alert_id}, user={self.user}, operators={alert.operator}"
                )
                return {"result": False, "message": "您没有权限认领此告警", "data": {}}

            # 更新告警状态
            alert.status = AlertStatus.PROCESSING
            alert.operate = AlertOperate.ACKNOWLEDGE
            alert.updated_at = timezone.now()
            alert.save()

            logger.info(
                f"告警认领成功: alert_id={alert_id}, user={self.user}, 状态变更: {AlertStatus.PENDING} -> {AlertStatus.PROCESSING}"
            )

            # 停止相关的提醒任务
            self._stop_reminder_tasks(alert)

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
        logger.info(f"开始转派告警: alert_id={alert_id}")

        with transaction.atomic():
            try:
                alert = self.get_alert(alert_id)
            except Alert.DoesNotExist:
                logger.error(f"告警不存在: alert_id={alert_id}")
                return {"result": False, "message": "告警不存在", "data": {}}

            # 检查当前状态是否为处理中
            if alert.status != AlertStatus.PROCESSING:
                logger.warning(
                    f"告警状态不符合转派条件: alert_id={alert_id}, current_status={alert.status}"
                )
                return {
                    "result": False,
                    "message": f"告警当前状态为{alert.get_status_display()}，无法进行转派操作",
                    "data": {},
                }

            # 检查是否有权限转派（是否为当前处理人）
            if self.user not in alert.operator:
                logger.warning(
                    f"用户无权限转派告警: alert_id={alert_id}, user={self.user}, operators={alert.operator}"
                )
                return {"result": False, "message": "您没有权限转派此告警", "data": {}}

            # 获取新的处理人信息
            new_assignee = data.get("assignee", [])
            if not new_assignee:
                logger.warning(f"转派操作缺少新处理人信息: alert_id={alert_id}")
                return {"result": False, "message": "请指定新的处理人", "data": {}}

            old_assignee = alert.operator.copy()

            # 更新告警状态和处理人
            alert.status = AlertStatus.PENDING
            alert.operate = AlertOperate.REASSIGN
            alert.operator = new_assignee
            alert.updated_at = timezone.now()
            alert.save()

            logger.info(
                f"告警转派成功: alert_id={alert_id}, old_assignee={old_assignee}, new_assignee={new_assignee}, 状态变更: {AlertStatus.PROCESSING} -> {AlertStatus.PENDING}"
            )

            notify_param = self.format_notify_data(new_assignee, alert)
            if notify_param:
                from apps.alerts.tasks import sync_notify

                transaction.on_commit(lambda: sync_notify.delay(notify_param))
            else:
                logger.warning(
                    f"未找到有效的email通知参数，邮件通知失败！alert_id={alert_id}, assignee={new_assignee}"
                )

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
        logger.info(f"开始关闭告警: alert_id={alert_id}")

        with transaction.atomic():
            try:
                alert = self.get_alert(alert_id)
            except Alert.DoesNotExist:
                logger.error(f"告警不存在: alert_id={alert_id}")
                return {"result": False, "message": "告警不存在", "data": {}}

            # 检查当前状态是否为处理中
            if alert.status != AlertStatus.PROCESSING:
                logger.warning(
                    f"告警状态不符合关闭条件: alert_id={alert_id}, current_status={alert.status}"
                )
                return {
                    "result": False,
                    "message": f"告警当前状态为{alert.get_status_display()}，无法进行关闭操作",
                    "data": {},
                }

            # 检查是否有权限关闭（是否为当前处理人）
            if self.user not in alert.operator:
                logger.warning(
                    f"用户无权限关闭告警: alert_id={alert_id}, user={self.user}, operators={alert.operator}"
                )
                return {"result": False, "message": "您没有权限关闭此告警", "data": {}}

            # 记录关闭原因
            close_reason = data.get("reason", "告警已处理完成")

            # 更新告警状态
            alert.status = AlertStatus.CLOSED
            alert.operate = AlertOperate.CLOSE
            alert.updated_at = timezone.now()
            alert.save()

            logger.info(
                f"告警关闭成功: alert_id={alert_id}, user={self.user}, reason={close_reason}, 状态变更: {AlertStatus.PROCESSING} -> {AlertStatus.CLOSED}"
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
        logger.info(f"开始处理告警: alert_id={alert_id}")

        with transaction.atomic():
            try:
                alert = self.get_alert(alert_id)
            except Alert.DoesNotExist:
                logger.error(f"告警不存在: alert_id={alert_id}")
                return {"result": False, "message": "告警不存在", "data": {}}

            # 检查当前状态是否为处理中
            if alert.status != AlertStatus.PROCESSING:
                logger.warning(
                    f"告警状态不符合处理条件: alert_id={alert_id}, current_status={alert.status}"
                )
                return {
                    "result": False,
                    "message": f"告警当前状态为{alert.get_status_display()}，无法标记为已处理",
                    "data": {},
                }

            # 检查是否有权限处理（是否为当前处理人）
            if self.user not in alert.operator:
                logger.warning(
                    f"用户无权限处理告警: alert_id={alert_id}, user={self.user}, operators={alert.operator}"
                )
                return {"result": False, "message": "您没有权限处理此告警", "data": {}}

            # 记录处理说明
            resolve_note = data.get("note", "告警问题已解决")

            # 更新告警状态
            alert.status = AlertStatus.RESOLVED
            alert.updated_at = timezone.now()
            alert.save()

            logger.info(
                f"告警处理成功: alert_id={alert_id}, user={self.user}, note={resolve_note}, 状态变更: {AlertStatus.PROCESSING} -> {AlertStatus.RESOLVED}"
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
        格式化通知数据
        :return: 格式化后的通知数据
        """
        channel, channel_id = get_default_notify_params()
        if not channel_id:
            return {}
        user_list = [i for i in assignee if i != self.user]
        param_format = NotifyParamsFormat(username_list=user_list, alerts=[alert])
        title = param_format.format_title()
        content = param_format.format_content()
        object_id = alert.alert_id
        result = {
            "username_list": user_list,
            "channel_type": channel,
            "channel_id": channel_id,
            "title": title,
            "content": content,
            "object_id": object_id,
            "notify_action_object": "alert",
        }
        return result

    @staticmethod
    def operator_log(log_data: dict):
        """
        记录告警操作日志
        :param log_data: 日志数据字典
        """
        OperatorLog.objects.create(**log_data)
