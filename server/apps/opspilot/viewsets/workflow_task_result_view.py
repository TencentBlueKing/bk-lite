from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import mixins
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.opspilot.enum import WorkFlowExecuteType
from apps.opspilot.models import WorkFlowTaskResult
from apps.opspilot.serializers.workflow_task_result_serializer import WorkFlowTaskResultSerializer


class WorkFlowTaskResultFilter(FilterSet):
    """工作流任务结果过滤器"""

    bot_id = filters.NumberFilter(field_name="bot_work_flow__bot__id")
    execute_type = filters.ChoiceFilter(choices=WorkFlowExecuteType.choices)
    start_time = filters.DateTimeFilter(field_name="run_time", lookup_expr="gte")
    end_time = filters.DateTimeFilter(field_name="run_time", lookup_expr="lte")


class WorkFlowTaskResultViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    """工作流任务执行结果视图集"""

    serializer_class = WorkFlowTaskResultSerializer
    queryset = WorkFlowTaskResult.objects.select_related("bot_work_flow__bot").all()
    filterset_class = WorkFlowTaskResultFilter
    ordering = ["-id"]  # 默认按运行时间倒序排列

    def list(self, request, *args, **kwargs):
        """获取工作流任务执行结果列表"""
        if not request.query_params.get("bot_id"):
            return Response({"detail": "bot_id参数是必需的。"}, status=400)

        return super().list(request, *args, **kwargs)
