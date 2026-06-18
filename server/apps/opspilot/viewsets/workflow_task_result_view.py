from django.db.models import Q
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.decorators.api_permission import HasPermission
from apps.opspilot.enum import WorkFlowExecuteType
from apps.opspilot.models import WorkFlowTaskNodeResult, WorkFlowTaskResult
from apps.opspilot.serializers.workflow_task_result_serializer import WorkFlowTaskResultSerializer
from apps.opspilot.utils.team_permission_mixin import TeamPermissionMixin


class WorkFlowTaskResultFilter(FilterSet):
    """工作流任务结果过滤器"""

    bot_id = filters.NumberFilter(field_name="bot_work_flow__bot__id")
    execute_type = filters.ChoiceFilter(choices=WorkFlowExecuteType.choices)
    execution_id = filters.CharFilter(field_name="execution_id")
    is_test = filters.BooleanFilter(field_name="is_test")
    start_time = filters.DateTimeFilter(field_name="run_time", lookup_expr="gte")
    end_time = filters.DateTimeFilter(field_name="run_time", lookup_expr="lte")


class WorkFlowTaskResultViewSet(TeamPermissionMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    """工作流任务执行结果视图集"""

    serializer_class = WorkFlowTaskResultSerializer
    queryset = WorkFlowTaskResult.objects.select_related("bot_work_flow__bot").all()
    filterset_class = WorkFlowTaskResultFilter
    ordering = ["-id"]  # 默认按运行时间倒序排列

    def get_queryset(self):
        """根据 current_team 过滤工作流任务结果"""
        queryset = super().get_queryset()
        current_team = self._validate_current_team_permission(self.request)
        # 根据 bot.team 过滤
        queryset = queryset.filter(bot_work_flow__bot__team__contains=[current_team])
        return queryset

    def _authorize_execution(self, execution_id: str, task_result_id: str):
        """解析并按当前 team 鉴权执行上下文。

        通过 team 作用域的 get_queryset() 解析 WorkFlowTaskResult，确保只有当前 team
        拥有的执行实例可被访问（WorkFlowTaskNodeResult 自身无 team 字段，只能经同
        execution_id 的 WorkFlowTaskResult → bot.team 判定归属）。找不到（不存在 / 属于
        他团队）一律 404，两种情况不区分，避免 execution_id 存在性枚举。

        返回 (authorized_execution_id, task_result)。
        """
        scoped = self.get_queryset()  # 内含 _validate_current_team_permission + team 过滤
        if task_result_id:
            task_result = scoped.filter(id=task_result_id).first()
            if not task_result:
                raise NotFound("未找到对应的执行记录。")
            if execution_id and task_result.execution_id != execution_id:
                raise NotFound("execution_id 与 id 不匹配。")
            execution_id = task_result.execution_id
        elif execution_id:
            task_result = scoped.filter(execution_id=execution_id).first()
            if not task_result:
                raise NotFound("未找到对应的执行记录。")
        else:
            raise ValidationError("execution_id 或 id 参数至少提供一个。")

        if not execution_id:
            raise NotFound("执行记录缺少有效的 execution_id。")
        return execution_id, task_result

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

    @HasPermission("bot_conversation_log-View")
    def list(self, request, *args, **kwargs):
        """获取工作流任务执行结果列表"""
        bot_id = request.query_params.get("bot_id")
        if not bot_id:
            return Response({"detail": "bot_id参数是必需的。"}, status=400)

        # 验证用户有权限访问该 bot
        self._validate_bot_permission(request, bot_id)

        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="execution_detail")
    @HasPermission("bot_conversation_log-View")
    def execution_detail(self, request):
        """按 execution_id 查询节点进度列表"""
        execution_id = request.query_params.get("execution_id", "")
        if not execution_id:
            return Response({"detail": "execution_id参数是必需的。"}, status=400)

        # 按当前 team 鉴权 execution_id（非本团队 / 不存在 → 404），再用已鉴权的 id 查节点
        execution_id, _task_result = self._authorize_execution(execution_id, "")

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
                "input_data",
                "output_data",
            )
        )
        return Response(list(node_results))

    @action(detail=False, methods=["GET"])
    @HasPermission("bot_conversation_log-View")
    def execution_output_data(self, request):
        """按 execution_id + id 查询节点详情，返回旧版 output_data 结构"""
        execution_id = request.query_params.get("execution_id", "")
        task_result_id = request.query_params.get("id", "")

        # 按当前 team 鉴权（非本团队 / 不存在 → 404），节点查询基于已鉴权的 execution_id
        execution_id, task_result = self._authorize_execution(execution_id, task_result_id)

        node_filters = self._build_node_filters(execution_id, task_result)

        node_results = WorkFlowTaskNodeResult.objects.filter(node_filters).order_by("node_index", "id")

        output_data = {}
        for node in node_results:
            output_data[node.node_id] = self._format_node_output_data(node)

        return Response(output_data)

    @action(detail=False, methods=["get"], url_path="node_execution_detail")
    @HasPermission("bot_conversation_log-View")
    def node_execution_detail(self, request):
        """按 execution_id + node_id 查询单节点输入/输出参数"""
        execution_id = request.query_params.get("execution_id", "")
        task_result_id = request.query_params.get("id", "")
        node_id = request.query_params.get("node_id", "")

        if not node_id:
            return Response({"detail": "node_id参数是必需的。"}, status=400)

        # 按当前 team 鉴权（非本团队 / 不存在 → 404），节点查询基于已鉴权的 execution_id
        execution_id, task_result = self._authorize_execution(execution_id, task_result_id)

        node_filters = self._build_node_filters(execution_id, task_result, node_id=node_id)

        node = WorkFlowTaskNodeResult.objects.filter(node_filters).order_by("-id").first()
        if not node:
            return Response({"detail": "未找到对应的节点执行记录。"}, status=404)

        return Response({"input_params": node.input_data or {}, "output_params": node.output_data or {}, "status": node.status})
