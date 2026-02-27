# -- coding: utf-8 --
# @File: collect.py
# @Time: 2025/2/27 14:00
# @Author: windyzhao
import re
from pathlib import Path
from django.conf import settings
from django.db.models import Q
from django.db import transaction
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.permissions.inst_task_permission import InstanceTaskPermission
from apps.cmdb.utils.base import get_current_team_from_request
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.core.utils.permission_utils import get_permission_rules
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.rpc.node_mgmt import NodeMgmt
from config.drf.viewsets import ModelViewSet
from config.drf.pagination import CustomPageNumberPagination
from apps.core.utils.web_utils import WebUtils
from apps.cmdb.constants.constants import COLLECT_OBJ_TREE, CollectRunStatusType, CollectPluginTypes, PERMISSION_TASK
from apps.cmdb.filters.collect_filters import CollectModelFilter, OidModelFilter
from apps.cmdb.models.collect_model import CollectModels, OidMapping
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer, CollectModelLIstSerializer, \
    OidModelSerializer, CollectModelIdStatusSerializer
from apps.cmdb.services.collect_service import CollectModelService


class CollectModelViewSet(AuthViewSet):
    queryset = CollectModels.objects.all()
    serializer_class = CollectModelSerializer
    ordering_fields = ["updated_at"]
    ordering = ["-updated_at"]
    filterset_class = CollectModelFilter
    pagination_class = CustomPageNumberPagination
    permission_classes = [InstanceTaskPermission]
    permission_key = PERMISSION_TASK

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path="collect_model_tree")
    def tree(self, request, *args, **kwargs):
        data = COLLECT_OBJ_TREE
        return WebUtils.response_success(data)

    def get_serializer_class(self):
        if self.action == "list":
            return CollectModelLIstSerializer
        return super().get_serializer_class()

    @HasPermission("auto_collection-View")
    def list(self, request, *args, **kwargs):
        return super(CollectModelViewSet, self).list(request, *args, **kwargs)

    def get_queryset_by_permission(self, request, queryset, permission_key=None):
        current_team = get_current_team_from_request(request, required=False)
        if not current_team:
            return queryset.filter(id=0)
        include_children = request.COOKIES.get("include_children", "0") == "1"
        if include_children:
            query_groups = GroupUtils.get_group_with_descendants(current_team)
        else:
            query_groups = [current_team]
        if not query_groups:
            query_groups = [current_team]

        team_query = Q()
        for team_id in query_groups:
            team_query = team_query | Q(team__contains=[team_id]) | Q(team__contains=[str(team_id)])
        base_queryset = queryset.filter(team_query)
        permission_key = permission_key or getattr(self, "permission_key", None)
        if not permission_key:
            return base_queryset

        if not include_children:
            app_name = self._get_app_name()
            current_team = request.COOKIES.get("current_team", "0")
            permission_data = get_permission_rules(
                request.user, current_team, app_name, permission_key, include_children
            )
            if not isinstance(permission_data, dict) or not permission_data:
                return base_queryset
            instance_ids = [
                i["id"] for i in permission_data.get("instance", []) if isinstance(i, dict) and "id" in i
            ]
            team_entries = permission_data.get("team", [])
            allowed_teams = set()
            for team_entry in team_entries:
                if isinstance(team_entry, dict) and "id" in team_entry:
                    allowed_teams.add(team_entry["id"])
                elif isinstance(team_entry, int):
                    allowed_teams.add(team_entry)
            allowed_teams &= set(query_groups)
            allowed_team_query = Q()
            for team_id in allowed_teams:
                allowed_team_query = allowed_team_query | Q(team__contains=[team_id]) | Q(team__contains=[str(team_id)])
            if instance_ids:
                if allowed_teams:
                    return base_queryset.filter(Q(id__in=instance_ids) | allowed_team_query)
                return base_queryset.filter(id__in=instance_ids)
            if allowed_teams:
                return base_queryset.filter(allowed_team_query)
        return base_queryset

    @HasPermission("auto_collection-Add")
    def create(self, request, *args, **kwargs):
        data = CollectModelService.create(request, self)
        return WebUtils.response_success(data)

    @HasPermission("auto_collection-Edit")
    def update(self, request, *args, **kwargs):
        data = CollectModelService.update(request, self)
        return WebUtils.response_success(data)

    @HasPermission("auto_collection-Delete")
    def destroy(self, request, *args, **kwargs):
        data = CollectModelService.destroy(request, self)
        return WebUtils.response_success(data)

    @action(methods=["GET"], detail=True)
    @HasPermission("auto_collection-View")
    def info(self, request, *args, **kwargs):
        instance = self.get_object()
        return WebUtils.response_success(instance.info)

    @HasPermission("auto_collection-Execute")
    @action(methods=["POST"], detail=True)
    def exec_task(self, request, *args, **kwargs):
        instance = self.get_object()
        result = CollectModelService.exec_task(instance=instance, request=request, view_self=self)
        return result

    @action(methods=["POST"], detail=True)
    @HasPermission("auto_collection-Add")
    @transaction.atomic
    def approval(self, request, *args, **kwargs):
        """
        任务审批
        """
        instance = self.get_object()
        CollectModelService.has_permission(instance=instance, request=request, view_self=self)
        if instance.exec_status != CollectRunStatusType.EXAMINE and not instance.input_method:
            return WebUtils.response_error(error_message="任务状态错误或录入方式不正确，无法审批！", status_code=400)
        if instance.examine:
            return WebUtils.response_error(error_message="任务已审批！无法再次审批！", status_code=400)

        data = request.data
        instances = data["instances"]
        model_map = {instance['model_id']: instance for instance in instances}
        CollectModelService.collect_controller(instance, model_map)
        return WebUtils.response_success()

    @action(methods=["GET"], detail=False)
    @HasPermission("auto_collection-View")
    def nodes(self, request, *args, **kwargs):
        """
        获取所有节点
        """
        params = request.GET.dict()
        query_data = {
            "page": int(params.get("page", 1)),
            "page_size": int(params.get("page_size", 10)),
            "name": params.get("name", ""),
            "permission_data": {
                "username": request.user.username,
                "domain": request.user.domain,
                "current_team": request.COOKIES.get("current_team"),
            },
        }
        node = NodeMgmt()
        data = node.node_list(query_data)
        return WebUtils.response_success(data)

    @action(methods=["GET"], detail=False)
    @HasPermission("auto_collection-View")
    def model_instances(self, requests, *args, **kwargs):
        """
        获取此模型下发过任务的实例
        """
        params = requests.GET.dict()
        task_type = params["task_type"]
        # 云对象可以重复选择不做过滤
        instances = CollectModels.objects.filter(~Q(instances=[]), ~Q(task_type=CollectPluginTypes.CLOUD),
                                                 task_type=task_type).values_list("instances", flat=True)
        result = []
        for instance in instances:
            if not isinstance(instance, list) or not instance:
                continue
            instance_data = instance[0]
            if not isinstance(instance_data, dict):
                continue
            instance_id = instance_data.get("_id")
            instance_name = instance_data.get("inst_name")
            if instance_id is None or instance_name is None:
                continue
            result.append({"id": instance_id, "inst_name": instance_name})
        return WebUtils.response_success(result)

    @action(methods=["POST"], detail=False)
    @HasPermission("auto_collection-View")
    def list_regions(self, requests, *args, **kwargs):
        """
        查询云的所有区域
        """
        params = requests.data
        cloud_id = requests.data["cloud_id"]
        cloud_list = NodeMgmt().cloud_region_list()
        cloud_id_map = {i["id"]: i["name"] for i in cloud_list}
        cloud_name = cloud_id_map.get(cloud_id)
        if not cloud_name:
            return WebUtils.response_error(error_message="cloud_id 不存在", status_code=400)
        params["model_id"] = params["model_id"].split("_account", 1)[0]
        task_id = params.pop("task_id", None)
        if task_id:
            node_object = NodeParamsFactory.get_node_params(instance=self.queryset.get(id=task_id))
            params.update(node_object.password)
        result = CollectModelService.list_regions(params, cloud_name=cloud_name)
        return WebUtils.response_success(result)

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path="task_status")
    def task_status(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        filter_queryset = self.get_queryset_by_permission(request=request, queryset=queryset)
        filter_queryset = filter_queryset.only("model_id", "exec_status")
        serializer = CollectModelIdStatusSerializer(filter_queryset, many=True, context={"request": request})
        data = {}
        for model_data in serializer.data:
            if not data.get(model_data['model_id'], False):
                data[model_data['model_id']] = {'success': 0, 'failed': 0, 'running': 0}
            if model_data['exec_status'] == CollectRunStatusType.SUCCESS:
                data[model_data['model_id']]['success'] += 1
            elif model_data['exec_status'] == CollectRunStatusType.ERROR:
                data[model_data['model_id']]['failed'] += 1
            elif model_data['exec_status'] == CollectRunStatusType.RUNNING:
                data[model_data['model_id']]['running'] += 1
        return WebUtils.response_success(data)

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path="collect_model_doc")
    def model_doc(self, request, *args, **kwargs):
        model_id = (request.GET.get("id") or "").strip()
        if not model_id:
            return WebUtils.response_error(error_message="id 不能为空", status_code=400)
        if not re.fullmatch(r"[A-Za-z0-9_]+", model_id):
            return WebUtils.response_error(error_message="id 参数非法", status_code=400)

        template_dir = (Path(settings.BASE_DIR) / "apps/cmdb/support-files/plugins_doc").resolve()
        file_path = (template_dir / f"{model_id}.md").resolve()
        if template_dir not in file_path.parents:
            return WebUtils.response_error(error_message="非法文档路径", status_code=400)

        data = ""
        if file_path.exists():
            with file_path.open("r", encoding="utf-8") as f:
                data = f.read()
        else:
            data = "未找到对应的文档！"
        return WebUtils.response_success(data)


class OidModelViewSet(ModelViewSet):
    queryset = OidMapping.objects.all()
    serializer_class = OidModelSerializer
    ordering_fields = ["updated_at"]
    ordering = ["-updated_at"]
    filterset_class = OidModelFilter
    pagination_class = CustomPageNumberPagination

    @HasPermission("soid_library-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("soid_library-Add")
    def create(self, request, *args, **kwargs):
        oid = request.data["oid"]
        if OidMapping.objects.filter(oid=oid).exists():
            return JsonResponse({"data": [], "result": False, "message": "OID已存在！"})

        return super().create(request, *args, **kwargs)

    @HasPermission("soid_library-Edit")
    def update(self, request, *args, **kwargs):
        oid = request.data["oid"]
        if OidMapping.objects.filter(~Q(id=self.get_object().id), oid=oid).exists():
            return JsonResponse({"data": [], "result": False, "message": "OId已存在！"})

        return super().update(request, *args, **kwargs)

    @HasPermission("soid_library-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
