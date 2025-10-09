# -- coding: utf-8 --
# @File: collect.py
# @Time: 2025/2/27 14:00
# @Author: windyzhao
from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse

from apps.cmdb.models import EXECUTE
from apps.cmdb.permission import InstanceTaskPermission
from apps.cmdb.utils.change_record import create_change_record
from apps.core.decorators.api_permission import HasPermission
from apps.rpc.node_mgmt import NodeMgmt
from config.drf.viewsets import ModelViewSet
from rest_framework.decorators import action
from django.db import transaction
from django.utils.timezone import now

from apps.cmdb.celery_tasks import sync_collect_task
from config.drf.pagination import CustomPageNumberPagination
from apps.core.utils.web_utils import WebUtils
from apps.cmdb.constants import COLLECT_OBJ_TREE, CollectRunStatusType, OPERATOR_COLLECT_TASK, CollectPluginTypes
from apps.cmdb.filters.collect_filters import CollectModelFilter, OidModelFilter
from apps.cmdb.models.collect_model import CollectModels, OidMapping
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer, CollectModelLIstSerializer, \
    OidModelSerializer
from apps.cmdb.services.colletc_service import CollectModelService


class CollectModelViewSet(ModelViewSet):
    queryset = CollectModels.objects.all()
    serializer_class = CollectModelSerializer
    ordering_fields = ["updated_at"]
    ordering = ["-updated_at"]
    filterset_class = CollectModelFilter
    pagination_class = CustomPageNumberPagination
    permission_classes = [InstanceTaskPermission]

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path="collect_model_tree")
    def tree(self, request, *args, **kwargs):
        data = COLLECT_OBJ_TREE
        return WebUtils.response_success(data)

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path="search")
    def search(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = CollectModelLIstSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)

        serializer = CollectModelLIstSerializer(queryset, many=True, context={"request": request})
        return WebUtils.response_success(serializer.data)

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
        if instance.exec_status == CollectRunStatusType.RUNNING:
            return WebUtils.response_error(error_message="任务正在执行中!无法重复执行！", status_code=400)

        instance.exec_time = now()
        instance.exec_status = CollectRunStatusType.RUNNING
        instance.format_data = {}
        instance.collect_data = {}
        instance.collect_digest = {}
        instance.save()
        if not settings.DEBUG:
            sync_collect_task.delay(instance.id)
        else:
            sync_collect_task(instance.id)

        create_change_record(operator=request.user.username, model_id=instance.model_id, label="采集任务",
                             _type=EXECUTE, message=f"执行采集任务. 任务名称: {instance.name}",
                             inst_id=instance.id, model_object=OPERATOR_COLLECT_TASK)

        return WebUtils.response_success(instance.id)

    @action(methods=["POST"], detail=True)
    @HasPermission("auto_collection-Add")
    @transaction.atomic
    def approval(self, request, *args, **kwargs):
        """
        任务审批
        """
        instance = self.get_object()
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
        result = [{"id": instance[0]["_id"], "inst_name": instance[0]["inst_name"]} for instance in instances]
        return WebUtils.response_success(result)

    @action(methods=["POST"], detail=False)
    @HasPermission("auto_collection-View")
    def list_regions(self, requests, *args, **kwargs):
        """
        查询云的所有区域
        """
        params = requests.data
        model_id = params.pop("model_id")
        plugin_id = "{}_info".format(model_id.split("_", 1)[0])
        result = CollectModelService.list_regions(plugin_id, params)
        return WebUtils.response_success(result)


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
