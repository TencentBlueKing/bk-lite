from django.http import JsonResponse
from django.utils.translation import gettext as _
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.opspilot import OpsPilot
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import GroupDataRule
from apps.system_mgmt.serializers import GroupDataRuleSerializer


class GroupDataRuleFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    group_id = filters.CharFilter(field_name="group_id", lookup_expr="exact")


class GroupDataRuleViewSet(viewsets.ModelViewSet):
    queryset = GroupDataRule.objects.all()
    serializer_class = GroupDataRuleSerializer
    filterset_class = GroupDataRuleFilter

    @action(methods=["GET"], detail=False)
    def get_app_data(self, request):
        params = request.GET.dict()
        client_map = {"opspilot": OpsPilot, "system-manager": SystemMgmt, "node": NodeMgmt}
        app = params.pop("app")
        if app not in client_map.keys():
            return JsonResponse({"result": False, "message": _("APP not found")})
        client = client_map[app]()
        fun = getattr(client, "get_module_data", None)
        if fun is None:
            return JsonResponse({"result": False, "message": _("Module not found")})
        params["page"] = int(params.get("page", "1"))
        params["page_size"] = int(params.get("page_size", "10"))
        return_data = fun(**params)
        return JsonResponse({"result": True, "data": return_data})
