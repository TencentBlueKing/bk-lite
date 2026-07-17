from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.loader import LanguageLoader
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.constants.language import LanguageConstants
from apps.node_mgmt.filters.collector import CollectorFilter
from apps.node_mgmt.models.sidecar import Collector
from apps.node_mgmt.serializers.collector import CollectorSerializer
from apps.node_mgmt.utils.architecture import display_cpu_architecture
from django.core.cache import cache


class CollectorViewSet(ModelViewSet):
    queryset = Collector.objects.exclude(id__in=CollectorConstants.IGNORE_COLLECTORS)
    serializer_class = CollectorSerializer
    filterset_class = CollectorFilter

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)
        for result in results:
            self._decorate_result(result, lan)

        page = self.paginate_queryset(results)
        if page is not None:
            return self.get_paginated_response(page)

        return Response(results)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)
        self._decorate_result(response.data, lan)
        return response

    @staticmethod
    def _decorate_result(result, lan):
        collector_key = result.get("id", "")
        name_key = f"{LanguageConstants.COLLECTOR}.{collector_key}.name"
        desc_key = f"{LanguageConstants.COLLECTOR}.{collector_key}.description"
        arch_display = display_cpu_architecture(result.get("cpu_architecture") or "")

        base_display_name = lan.get(name_key) or result.get("name", "")
        if arch_display != "--":
            result["display_name"] = f"{base_display_name}（{arch_display}）"
        else:
            result["display_name"] = base_display_name
        result["display_introduction"] = lan.get(desc_key) or result.get("introduction", "")
        result["architecture_display"] = arch_display

    @HasPermission("collector_list-Add")
    def create(self, request, *args, **kwargs):
        data = request.data
        data.update(is_pre=False)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # 清除cache中的etag
        cache.delete("collectors_etag")

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("collector_list-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("collector_list-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
