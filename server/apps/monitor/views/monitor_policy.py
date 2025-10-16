import json

from django_celery_beat.models import PeriodicTask, CrontabSchedule
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.filters.monitor_policy import MonitorPolicyFilter
from apps.monitor.models import PolicyOrganization
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.monitor.services.policy import PolicyService
from config.drf.pagination import CustomPageNumberPagination


class MonitorPolicyVieSet(viewsets.ModelViewSet):
    queryset = MonitorPolicy.objects.all()
    serializer_class = MonitorPolicySerializer
    filterset_class = MonitorPolicyFilter
    pagination_class = CustomPageNumberPagination

    def list(self, request, *args, **kwargs):
        monitor_object_id = request.query_params.get('monitor_object_id', None)

        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "monitor",
            f"{PermissionConstants.POLICY_MODULE}.{monitor_object_id}",
        )
        qs = permission_filter(MonitorPolicy, permission, team_key="policyorganization__organization__in", id_key="id__in")

        queryset = self.filter_queryset(qs)

        queryset = queryset.distinct()

        # 获取分页参数
        page = int(request.GET.get('page', 1))  # 默认第1页
        page_size = int(request.GET.get('page_size', 10))  # 默认每页10条数据

        # 计算分页的起始位置
        start = (page - 1) * page_size
        end = start + page_size

        # 获取当前页的数据
        page_data = queryset[start:end]

        # 执行序列化
        serializer = self.get_serializer(page_data, many=True)
        results = serializer.data

        # 如果有权限规则，则添加到数据中
        inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}

        for instance_info in results:
            if instance_info['id'] in inst_permission_map:
                instance_info['permission'] = inst_permission_map[instance_info['id']]
            else:
                instance_info['permission'] = PermissionConstants.DEFAULT_PERMISSION

        return WebUtils.response_success(dict(count=queryset.count(), items=results))

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
            raise BaseAppException('Invalid schedule type')

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

    @action(methods=['post'], detail=False, url_path='template')
    def template(self, request):
        data = PolicyService.get_policy_templates(request.data['monitor_object_name'])
        return WebUtils.response_success(data)

    @action(methods=['get'], detail=False, url_path='template/monitor_object')
    def template_monitor_object(self, request):
        data = PolicyService.get_policy_templates_monitor_object()
        return WebUtils.response_success(data)
