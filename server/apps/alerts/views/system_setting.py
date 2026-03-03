# -- coding: utf-8 --
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.filters import SystemSettingModelFilter
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.models.sys_setting import SystemSetting
from apps.alerts.serializers import SystemSettingModelSerializer
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import alert_logger as logger
from apps.core.utils.celery_utils import CeleryUtils
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class SystemSettingModelViewSet(ModelViewSet):
    """
    系统设置视图集
    no_dispatch_alert_notice: 未分派告警通知
    """
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingModelSerializer
    filterset_class = SystemSettingModelFilter
    pagination_class = CustomPageNumberPagination

    @HasPermission("global_config-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("global_config-View")
    @action(methods=['get'], detail=False, url_path='get_setting_key/(?P<setting_key>[^/.]+)')
    def get_setting_key(self, requests, setting_key):
        """
        获取系统设置的特定键值
        :param requests: 请求对象
        :param setting_key: 设置键
        :return: 返回特定设置键的值
        """
        try:
            setting = SystemSetting.objects.get(key=setting_key)
            data = {
                "id": setting.id,
                "key": setting.key,
                "value": setting.value,
                "description": setting.description,
                "is_activate": setting.is_activate,
                "is_build": setting.is_build
            }
            return WebUtils.response_success(data)
        except SystemSetting.DoesNotExist:
            return WebUtils.response_error(error_message="Setting not found", status_code=status.HTTP_404_NOT_FOUND)

    @HasPermission("global_config-Add")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        log_data = {
            "action": LogAction.ADD,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "系统配置-创建",
            "target_id": serializer.data["key"],
            "overview": f"创建系统配置: key:{serializer.data['key']}"
        }
        OperatorLog.objects.create(**log_data)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("global_config-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """
        更新完成系统配置后 若修改了时间频率 即修改celery任务
        """
        instance = self.get_object()
        old_instance_data = {
            'is_activate': instance.is_activate,
            'value': instance.value
        }

        if instance.key == "no_dispatch_alert_notice":
            self.update_no_dispatch_celery_task(request.data, old_instance_data)

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        log_data = {
            "action": LogAction.MODIFY,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "系统配置-修改",
            "target_id": instance.key,
            "overview": f"修改系统配置: key:{instance.key}"
        }
        OperatorLog.objects.create(**log_data)

        self.perform_update(serializer)
        return WebUtils.response_success(serializer.data)

    def update_no_dispatch_celery_task(self, new_data, old_data):
        """
        处理未分派告警通知的celery任务管理
        """
        task_name = "no_dispatch_alert_notice"
        task = "apps.alerts.tasks.sync_no_dispatch_alert_notice_task"

        old_is_activate = old_data.get('is_activate', False)
        old_notify_every = old_data.get('value', {}).get('notify_every', 60) if old_data.get('value') else 60

        new_is_activate = new_data.get("is_activate")
        new_value = new_data.get("value", {})
        new_notify_every = new_value.get("notify_every", old_notify_every)

        logger.info(f"更新未分派告警通知配置: old_activate={old_is_activate}, new_activate={new_is_activate}, "
                    f"old_notify_every={old_notify_every}, new_notify_every={new_notify_every}")

        # 获取当前任务状态
        current_task_enabled = CeleryUtils.is_task_enabled(task_name)

        # 处理激活状态变化
        if new_is_activate is not None:
            if new_is_activate and not old_is_activate:
                # 从未激活变为激活
                if current_task_enabled is None:
                    # 任务不存在，创建新任务
                    crontab = self._convert_minutes_to_crontab(new_notify_every)
                    CeleryUtils.create_or_update_periodic_task(
                        name=task_name,
                        crontab=crontab,
                        task=task,
                        enabled=True
                    )
                    logger.info(f"创建未分派告警通知任务: {task_name}, crontab={crontab}")
                else:
                    # 任务存在，启用任务并更新配置
                    crontab = self._convert_minutes_to_crontab(new_notify_every)
                    CeleryUtils.create_or_update_periodic_task(
                        name=task_name,
                        crontab=crontab,
                        task=task,
                        enabled=True
                    )
                    logger.info(f"启用并更新未分派告警通知任务: {task_name}, crontab={crontab}")

            elif not new_is_activate and old_is_activate:
                # 从激活变为未激活，禁用任务而不删除
                if current_task_enabled is not None:
                    CeleryUtils.disable_periodic_task(task_name)
                    logger.info(f"禁用未分派告警通知任务: {task_name}")

            elif new_is_activate and old_is_activate:
                # 保持激活状态，检查是否需要更新时间间隔
                if new_notify_every != old_notify_every:
                    crontab = self._convert_minutes_to_crontab(new_notify_every)
                    CeleryUtils.create_or_update_periodic_task(
                        name=task_name,
                        crontab=crontab,
                        task=task,
                        enabled=True
                    )
                    logger.info(f"更新未分派告警通知任务时间间隔: {task_name}, crontab={crontab}")
        else:
            # 如果is_activate没有变化，但仍然是激活状态且notify_every有变化
            if old_is_activate and new_notify_every != old_notify_every:
                crontab = self._convert_minutes_to_crontab(new_notify_every)
                CeleryUtils.create_or_update_periodic_task(
                    name=task_name,
                    crontab=crontab,
                    task=task,
                    enabled=True
                )
                logger.info(f"更新未分派告警通知任务时间间隔: {task_name}, crontab={crontab}")

    @staticmethod
    def _convert_minutes_to_crontab(minutes):
        """
        将分钟转换为crontab格式
        :param minutes: 分钟数
        :return: crontab格式字符串 "minute hour day_of_month month_of_year day_of_week"
        """
        try:
            minutes = int(minutes)
        except (ValueError, TypeError):
            logger.warning(f"无效的分钟数: {minutes}, 使用默认值60分钟")
            raise Exception("无效的分钟数，必须是整数! ")

        if minutes <= 0:
            logger.warning(f"分钟数不能小于等于0: {minutes}, 使用默认值60分钟")
            minutes = 60

        if minutes < 60:
            # 小于60分钟，每隔指定分钟执行一次
            return f"*/{minutes} * * * *"
        elif minutes == 60:
            # 每小时执行一次
            return "0 * * * *"
        elif minutes % 60 == 0:
            # 每隔几小时执行一次
            hours = minutes // 60
            if hours >= 24:
                # 如果超过24小时，改为每天执行一次
                return "0 0 * * *"
            else:
                return f"0 */{hours} * * *"
        else:
            # 不能整除60的情况，转换为小时+分钟格式
            # 例如90分钟 = 1小时30分钟，可能需要复杂的crontab表达式
            # 简化处理：如果大于60分钟且不能整除，按每小时执行
            logger.warning(f"复杂时间间隔{minutes}分钟，简化为每小时执行")
            return "0 * * * *"

    # @HasPermission("global_config-View")
    @action(methods=['get'], detail=False, url_path='get_channel_list')
    def get_channel_list(self, request):
        """
        获取告警通知通道列表: 存在配置
        """

        result = []

        from apps.system_mgmt.models.channel import Channel

        channel_list = Channel.objects.all()
        for channel in channel_list:
            result.append(
                {
                    "id": channel.id,
                    "name": f"{channel.name}【{channel.get_channel_type_display()}】",
                    "channel_type": channel.channel_type,
                }
            )

        return WebUtils.response_success(result)
