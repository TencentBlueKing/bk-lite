# -- coding: utf-8 --
# @File: view.py
# @Time: 2025/5/9 15:14
# @Author: windyzhao
import uuid

from django.contrib.postgres.aggregates import StringAgg
from django.db.models import Count
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction

from apps.alerts.constants import LogAction, LogTargetType
from apps.alerts.filters import AlertSourceModelFilter, AlertModelFilter, EventModelFilter, LevelModelFilter, \
    IncidentModelFilter, SystemSettingModelFilter, OperatorLogModelFilter
from apps.alerts.models import AlertSource, Alert, Event, Level, Incident, SystemSetting, OperatorLog
from apps.alerts.serializers.serializers import AlertSourceModelSerializer, AlertModelSerializer, EventModelSerializer, \
    LevelModelSerializer, IncidentModelSerializer, SystemSettingModelSerializer, OperatorLogModelSerializer
from apps.alerts.service.alter_operator import AlertOperator
from apps.alerts.service.incident_operator import IncidentOperator
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import alert_logger as logger
from apps.core.utils.celery_utils import CeleryUtils
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


def request_test(requests):
    """
    Test function to handle requests.

    :param requests: The request data.
    :return: A response indicating success or failure.
    """
    print("Processing request:", requests)
    return WebUtils.response_success([])


class AlertSourceModelViewSet(ModelViewSet):
    """
    告警源
    """
    queryset = AlertSource.objects.all()
    serializer_class = AlertSourceModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = AlertSourceModelFilter
    pagination_class = CustomPageNumberPagination


class AlterModelViewSet(ModelViewSet):
    """
    告警视图集
    """
    # -level 告警等级排序
    queryset = Alert.objects.all()
    serializer_class = AlertModelSerializer
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    filterset_class = AlertModelFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = Alert.objects.annotate(
            event_count_annotated=Count('events'),
            # 通过事件获取告警源名称（去重）
            source_names_annotated=StringAgg('events__source__name', delimiter=', ', distinct=True),
            incident_title_annotated=StringAgg('incident__title', delimiter=', ', distinct=True)
        ).prefetch_related('events__source')
        return queryset

    @HasPermission("Alarms-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("Alarms-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("Alarms-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("Alarms-Edit")
    @action(methods=['post'], detail=False, url_path='operator/(?P<operator_action>[^/.]+)', url_name='operator')
    @transaction.atomic
    def operator(self, request, operator_action, *args, **kwargs):
        """
        Custom operator method to handle alert operations.
        """
        alert_id_list = request.data["alert_id"]
        operator = AlertOperator(user=self.request.user.username)
        result_list = {}
        status_list = []
        for alert_id in alert_id_list:
            result = operator.operate(action=operator_action, alert_id=alert_id, data=request.data)
            result_list[alert_id] = result
            status_list.append(result["result"])

        if all(status_list):
            return WebUtils.response_success(result_list)
        elif not all(status_list):
            return WebUtils.response_error(
                response_data=result_list,
                error_message="操作失败，请检查日志!",
                status_code=500
            )
        else:
            return WebUtils.response_success(response_data=result_list, message="部分操作成功")


class EventModelViewSet(ModelViewSet):
    """
    事件视图集
    """
    queryset = Event.objects.all()
    serializer_class = EventModelSerializer
    ordering_fields = ["received_at"]
    ordering = ["-received_at"]
    filterset_class = EventModelFilter
    pagination_class = CustomPageNumberPagination

    @HasPermission("Integration-View,Alarms-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class LevelModelViewSet(ModelViewSet):
    """
    告警等级视图集
    """
    # TODO 创建的时候动态增加level_id 锁表
    queryset = Level.objects.all()
    serializer_class = LevelModelSerializer
    filterset_class = LevelModelFilter
    ordering_fields = ["level_id"]
    ordering = ["level_id"]
    pagination_class = CustomPageNumberPagination


class IncidentModelViewSet(ModelViewSet):
    """
    事故视图集
    """
    queryset = Incident.objects.all()
    serializer_class = IncidentModelSerializer
    ordering_fields = ["created_at", "id"]  # 允许按创建时间和ID排序 ?ordering=-id
    ordering = ["-created_at"]  # 默认按创建时间降序排序
    filterset_class = IncidentModelFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = Incident.objects.annotate(
            alert_count=Count('alert')
        ).prefetch_related('alert')
        return queryset

    @HasPermission("Incidents-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("Alarms-Edit")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = request.data
        incident_id = f"INCIDENT-{uuid.uuid4().hex}"
        data["incident_id"] = incident_id
        if not data["alert"]:
            return Response(
                {"detail": "must provide at least one alert to create an incident."},
                status=status.HTTP_400_BAD_REQUEST
            )
        else:
            not_incident_alert_ids = list(
                Alert.objects.filter(id__in=data["alert"], incident__isnull=False).values_list('id', flat=True))
            has_incident_alert_ids = set(data["alert"]) - set(not_incident_alert_ids)
            data["alert"] = list(has_incident_alert_ids)
            if not has_incident_alert_ids:
                logger.warning(
                    f"Some alerts {has_incident_alert_ids} are already associated with an incident. "
                    "They will not be included in the new incident."
                )
                return Response(
                    {"detail": "Some alerts are already associated with an incident and will not be included."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        if not data["operator"]:
            data["operator"] = self.request.user.username

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        log_data = {
            "action": LogAction.ADD,
            "target_type": LogTargetType.INCIDENT,
            "operator": request.user.username,
            "operator_object": "事故-创建",
            "target_id": serializer.data["incident_id"],
            "overview": f"手动创建事故[{serializer.data['title']}]"
        }
        OperatorLog.objects.create(**log_data)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("Incidents-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        log_data = {
            "action": LogAction.MODIFY,
            "target_type": LogTargetType.INCIDENT,
            "operator": request.user.username,
            "operator_object": "事故-更新",
            "target_id": instance.incident_id,
            "overview": f"手动修改事故[{instance.title}]"
        }
        OperatorLog.objects.create(**log_data)

        return Response(serializer.data)

    @HasPermission("Incidents-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)

        log_data = {
            "action": LogAction.DELETE,
            "target_type": LogTargetType.INCIDENT,
            "operator": request.user.username,
            "operator_object": "事故-删除",
            "target_id": instance.incident_id,
            "overview": f"手动删除事故[{instance.title}]"
        }
        OperatorLog.objects.create(**log_data)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @HasPermission("Incidents-Edit")
    @action(methods=['post'], detail=False, url_path='operator/(?P<operator_action>[^/.]+)', url_name='operator')
    @transaction.atomic
    def operator(self, request, operator_action, *args, **kwargs):
        """
        事故操作方法
        """
        incident_id_list = request.data.get("incident_id", [])
        if not incident_id_list:
            return WebUtils.response_error(error_message="incident_id参数不能为空")

        operator = IncidentOperator(user=self.request.user.username)
        result_list = {}
        status_list = []

        for incident_id in incident_id_list:
            result = operator.operate(action=operator_action, incident_id=incident_id, data=request.data)
            result_list[incident_id] = result
            status_list.append(result["result"])

        if all(status_list):
            return WebUtils.response_success(result_list)
        elif not any(status_list):
            return WebUtils.response_error(
                response_data=result_list,
                error_message="操作失败，请检查日志!",
                status_code=500
            )
        else:
            return WebUtils.response_success(response_data=result_list, message="部分操作成功")


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


class SystemLogModelViewSet(ModelViewSet):
    """
    系统日志视图集
    """
    queryset = OperatorLog.objects.all()
    serializer_class = OperatorLogModelSerializer
    filterset_class = OperatorLogModelFilter
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    pagination_class = CustomPageNumberPagination

    @HasPermission("operation_log-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
