from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.rpc.cmdb import CMDB
from apps.rpc.log import Log
from apps.rpc.monitor import Monitor
from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.opspilot import OpsPilot
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import GroupDataRule
from apps.system_mgmt.serializers import GroupDataRuleSerializer


class GroupDataRuleFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    group_id = filters.CharFilter(field_name="group_id", lookup_expr="exact")
    app = filters.CharFilter(field_name="app", lookup_expr="exact")


class GroupDataRuleViewSet(LanguageViewSet):
    queryset = GroupDataRule.objects.all().order_by("-id")
    serializer_class = GroupDataRuleSerializer
    filterset_class = GroupDataRuleFilter

    @HasPermission("data_permission-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("data_permission-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("data_permission-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("data_permission-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(methods=["GET"], detail=False)
    @HasPermission("data_permission-View")
    def get_app_data(self, request):
        params = request.GET.dict()
        try:
            client = self.get_client(params)
        except Exception as e:
            return JsonResponse({"result": False, "message": str(e)})
        fun = getattr(client, "get_module_data", None)
        if fun is None:
            message = self.loader.get("error.module_not_found") if self.loader else "Module not found"
            return JsonResponse({"result": False, "message": message})
        params["page"] = int(params.get("page", "1"))
        params["page_size"] = int(params.get("page_size", "10"))
        return_data = fun(**params)
        return JsonResponse({"result": True, "data": return_data})

    @action(methods=["GET"], detail=False)
    @HasPermission("data_permission-View")
    def get_app_module(self, request):
        params = request.GET.dict()
        try:
            client = self.get_client(params)
        except Exception as e:
            return JsonResponse({"result": False, "message": str(e)})
        fun = getattr(client, "get_module_list", None)
        if fun is None:
            message = self.loader.get("error.module_not_found") if self.loader else "Module not found"
            return JsonResponse({"result": False, "message": message})
        return_data = fun()
        for i in return_data:
            translated_name = self.loader.get(f"base_constant.{i['display_name']}") if self.loader else None
            i["display_name"] = translated_name or i["display_name"]
            if "children" in i:
                for child in i["children"]:
                    translated_child_name = self.loader.get(f"base_constant.{child['display_name']}") if self.loader else None
                    child["display_name"] = translated_child_name or child["display_name"]
        return JsonResponse({"result": True, "data": return_data})

    @staticmethod
    def get_client(params):
        client_map = {
            "opspilot": OpsPilot,
            "system-manager": SystemMgmt,
            "node": NodeMgmt,
            "monitor": Monitor,
            "log": Log,
            "cmdb": CMDB,
        }
        app = params.pop("app")
        if app not in client_map.keys():
            raise Exception("APP not found")
        client = client_map[app]()
        return client
