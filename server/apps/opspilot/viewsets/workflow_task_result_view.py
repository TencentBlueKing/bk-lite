from django.db.models import Q
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.opspilot.enum import WorkFlowExecuteType
from apps.opspilot.models import WorkFlowTaskNodeResult, WorkFlowTaskResult
from apps.opspilot.serializers.workflow_task_result_serializer import WorkFlowTaskResultSerializer


class WorkFlowTaskResultFilter(FilterSet):
    """工作流任务结果过滤器"""

    bot_id = filters.NumberFilter(field_name="bot_work_flow__bot__id")
    execute_type = filters.ChoiceFilter(choices=WorkFlowExecuteType.choices)
    execution_id = filters.CharFilter(field_name="execution_id")
    start_time = filters.DateTimeFilter(field_name="run_time", lookup_expr="gte")
    end_time = filters.DateTimeFilter(field_name="run_time", lookup_expr="lte")


class WorkFlowTaskResultViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    """工作流任务执行结果视图集"""

    serializer_class = WorkFlowTaskResultSerializer
    queryset = WorkFlowTaskResult.objects.select_related("bot_work_flow__bot").all()
    filterset_class = WorkFlowTaskResultFilter
    ordering = ["-id"]  # 默认按运行时间倒序排列

    def _resolve_execution_context(self, execution_id: str, task_result_id: str):
        """解析 execution_id 与 task_result 上下文"""
        if not execution_id and not task_result_id:
            return None, None, Response({"detail": "execution_id或id参数至少提供一个。"}, status=400)

        task_result = None
        if task_result_id:
            task_result = WorkFlowTaskResult.objects.filter(id=task_result_id).first()
            if not task_result:
                return None, None, Response({"detail": "未找到对应的workflow_task_result记录。"}, status=404)

            if execution_id and task_result.execution_id != execution_id:
                return None, None, Response({"detail": "execution_id与id不匹配。"}, status=400)

        if not execution_id and task_result:
            execution_id = task_result.execution_id

        if not task_result and execution_id:
            task_result = WorkFlowTaskResult.objects.filter(execution_id=execution_id).order_by("-id").first()

        return execution_id, task_result, None

    @staticmethod
    def _build_node_filters(execution_id: str, task_result=None, node_id: str = ""):
        """构建节点查询过滤条件"""
        node_filters = Q(execution_id=execution_id)
        if node_id:
            node_filters &= Q(node_id=node_id)
        if task_result and task_result.id:
            node_filters &= Q(task_result=task_result) | Q(task_result__isnull=True)
        return node_filters

    @staticmethod
    def _format_node_output_data(node: WorkFlowTaskNodeResult):
        """格式化单节点输出结构"""
        node_data = {
            "name": node.node_name,
            "type": node.node_type,
            "index": node.node_index,
            "output": node.output_data or {},
            "status": node.status,
            "input_data": node.input_data or {},
        }
        if node.error_message:
            node_data["error"] = node.error_message
        return node_data

    def list(self, request, *args, **kwargs):
        """获取工作流任务执行结果列表"""
        if not request.query_params.get("bot_id"):
            return Response({"detail": "bot_id参数是必需的。"}, status=400)

        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="execution_detail")
    def execution_detail(self, request):
        """按 execution_id 查询节点进度列表"""
        execution_id = request.query_params.get("execution_id", "")
        if not execution_id:
            return Response({"detail": "execution_id参数是必需的。"}, status=400)

        node_results = (
            WorkFlowTaskNodeResult.objects.filter(execution_id=execution_id)
            .order_by("node_index", "id")
            .values(
                "node_id",
                "node_name",
                "node_type",
                "node_index",
                "status",
                "error_message",
                "start_time",
                "end_time",
                "duration_ms",
            )
        )
        return Response(list(node_results))

    @action(detail=False, methods=["GET"])
    def execution_output_data(self, request):
        """按 execution_id + id 查询节点详情，返回旧版 output_data 结构"""
        execution_id = request.query_params.get("execution_id", "")
        task_result_id = request.query_params.get("id", "")

        execution_id, task_result, error_response = self._resolve_execution_context(execution_id, task_result_id)
        if error_response:
            return error_response

        node_filters = self._build_node_filters(execution_id, task_result)

        node_results = WorkFlowTaskNodeResult.objects.filter(node_filters).order_by("node_index", "id")

        output_data = {}
        for node in node_results:
            output_data[node.node_id] = self._format_node_output_data(node)

        return Response(output_data)

    @action(detail=False, methods=["get"], url_path="node_execution_detail")
    def node_execution_detail(self, request):
        """按 execution_id + node_id 查询单节点输入/输出参数"""
        execution_id = request.query_params.get("execution_id", "")
        task_result_id = request.query_params.get("id", "")
        node_id = request.query_params.get("node_id", "")

        if not node_id:
            return Response({"detail": "node_id参数是必需的。"}, status=400)

        execution_id, task_result, error_response = self._resolve_execution_context(execution_id, task_result_id)
        if error_response:
            return error_response

        node_filters = self._build_node_filters(execution_id, task_result, node_id=node_id)

        node = WorkFlowTaskNodeResult.objects.filter(node_filters).order_by("-id").first()
        if not node:
            return Response({"detail": "未找到对应的节点执行记录。"}, status=404)

        return Response({"input_params": node.input_data or {}, "output_params": node.output_data or {}, "status": node.status})
