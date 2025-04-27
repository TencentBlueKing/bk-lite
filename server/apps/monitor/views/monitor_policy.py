import json

from django_celery_beat.models import PeriodicTask, CrontabSchedule
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.web_utils import WebUtils
from apps.monitor.filters.monitor_policy import MonitorPolicyFilter
from apps.monitor.models import PolicyOrganization
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.policy_template.common import load_json
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from config.drf.pagination import CustomPageNumberPagination


class MonitorPolicyVieSet(viewsets.ModelViewSet):
    queryset = MonitorPolicy.objects.all()
    serializer_class = MonitorPolicySerializer
    filterset_class = MonitorPolicyFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        group_ids = [i["id"] for i in request.user.group_list]
        queryset = queryset.filter(policyorganization__organization__in=group_ids).distinct()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return WebUtils.response_success(serializer.data)

    def create(self, request, *args, **kwargs):
        # 补充创建人
        request.data['created_by'] = request.user.username
        response = super().create(request, *args, **kwargs)
        policy_id = response.data['id']
        schedule = request.data.get('schedule')
        organizations = request.data.get('organizations', [])
        self.update_or_create_task(policy_id, schedule)
        self.update_policy_organizations(policy_id, organizations)
        return response

    def update(self, request, *args, **kwargs):
        # 补充更新人
        request.data['updated_by'] = request.user.username
        response = super().update(request, *args, **kwargs)
        policy_id = kwargs['pk']
        schedule = request.data.get('schedule')
        if schedule:
            self.update_or_create_task(policy_id, schedule)
        organizations = request.data.get('organizations', [])
        if organizations:
            self.update_policy_organizations(policy_id, organizations)
        return response

    def partial_update(self, request, *args, **kwargs):
        # 补充更新人
        request.data['updated_by'] = request.user.username
        response = super().partial_update(request, *args, **kwargs)
        policy_id = kwargs['pk']
        schedule = request.data.get('schedule')
        if schedule:
            self.update_or_create_task(policy_id, schedule)
        organizations = request.data.get('organizations', [])
        if organizations:
            self.update_policy_organizations(policy_id, organizations)
        return response

    def destroy(self, request, *args, **kwargs):
        policy_id = kwargs['pk']
        PeriodicTask.objects.filter(name=f'scan_policy_task_{policy_id}').delete()
        PolicyOrganization.objects.filter(policy_id=policy_id).delete()
        return super().destroy(request, *args, **kwargs)

    def format_crontab(self, schedule):
        """
            将 schedule 格式化为 CrontabSchedule 实例
            """
        schedule_type = schedule.get('type')
        value = schedule.get('value')

        if schedule_type == 'min':
            return CrontabSchedule.objects.get_or_create(
                minute=f'*/{value}', hour='*', day_of_month='*', month_of_year='*', day_of_week='*'
            )[0]
        elif schedule_type == 'hour':
            return CrontabSchedule.objects.get_or_create(
                minute=0, hour=f'*/{value}', day_of_month='*', month_of_year='*', day_of_week='*'
            )[0]
        elif schedule_type == 'day':
            return CrontabSchedule.objects.get_or_create(
                minute=0, hour=0, day_of_month=f'*/{value}', month_of_year='*', day_of_week='*'
            )[0]
        else:
            raise ValueError('Invalid schedule type')

    def update_or_create_task(self, policy_id, schedule):
        task_name = f'scan_policy_task_{policy_id}'

        # 删除旧的定时任务
        PeriodicTask.objects.filter(name=task_name).delete()

        # 解析 schedule，并创建相应的调度
        format_crontab = self.format_crontab(schedule)
        # 创建新的 PeriodicTask
        PeriodicTask.objects.create(
            name=task_name,
            task='apps.monitor.tasks.monitor_policy.scan_policy_task',
            args=json.dumps([policy_id]),  # 任务参数，使用 JSON 格式存储
            crontab=format_crontab,
            enabled=True
        )

    def update_policy_organizations(self, policy_id, organizations):
        """更新策略的组织"""
        old_organizations = PolicyOrganization.objects.filter(policy_id=policy_id)
        old_set = set([org.organization for org in old_organizations])
        new_set = set(organizations)
        # 删除不存在的组织
        delete_set = old_set - new_set
        PolicyOrganization.objects.filter(policy_id=policy_id, organization__in=delete_set).delete()
        # 添加新的组织
        create_set = new_set - old_set
        create_objs = [PolicyOrganization(policy_id=policy_id, organization=org_id) for org_id in create_set]
        PolicyOrganization.objects.bulk_create(create_objs, batch_size=200)

    @swagger_auto_schema(
        operation_id="policy_template",
        operation_description="获取策略模板",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "monitor_object_name": openapi.Schema(type=openapi.TYPE_STRING, description="监控对象名称")
            },
            required=["monitor_object_name"]
        )
    )
    @action(methods=['post'], detail=False, url_path='template')
    def template(self, request):
        data = load_json(request.data.get('monitor_object_name'))
        return WebUtils.response_success(data)
