from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet
from rest_framework.response import Response

from apps.core.utils.loader import LanguageLoader
from apps.node_mgmt.constants.language import LanguageConstants
from apps.node_mgmt.filters.controller import ControllerFilter
from apps.node_mgmt.models import Controller
from apps.node_mgmt.serializers.controller import ControllerSerializer


class ControllerViewSet(mixins.ListModelMixin,
                       GenericViewSet):
    queryset = Controller.objects.all()
    serializer_class = ControllerSerializer
    filterset_class = ControllerFilter
    search_fields = ['id', 'name', 'introduction']

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)

        for result in results:
            # 获取控制器的翻译名称和描述
            name_key = f"{LanguageConstants.CONTROLLER}.{result['os']}.name"
            desc_key = f"{LanguageConstants.CONTROLLER}.{result['os']}.description"

            result["display_name"] = lan.get(name_key) or result["name"]
            result["display_description"] = lan.get(desc_key) or result.get("description", "")

        page = self.paginate_queryset(results)
        if page is not None:
            return self.get_paginated_response(page)

        return Response(results)
