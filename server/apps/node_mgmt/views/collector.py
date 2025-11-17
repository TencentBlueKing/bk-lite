from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.core.utils.loader import LanguageLoader
from apps.node_mgmt.constants.language import LanguageConstants
from apps.node_mgmt.filters.collector import CollectorFilter
from apps.node_mgmt.models.sidecar import Collector
from apps.node_mgmt.serializers.collector import CollectorSerializer
from django.core.cache import cache


class CollectorViewSet(ModelViewSet):
    queryset = Collector.objects.all()
    serializer_class = CollectorSerializer
    filterset_class = CollectorFilter

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)

        for result in results:
            # 采集器ID格式: {name}_{os}，例如 telegraf_linux
            collector_key = result.get('id', '')
            name_key = f"{LanguageConstants.COLLECTOR}.{collector_key}.name"
            desc_key = f"{LanguageConstants.COLLECTOR}.{collector_key}.description"

            result["display_name"] = lan.get(name_key) or result.get("name", "")
            result["display_introduction"] = lan.get(desc_key) or result.get("introduction", "")

        page = self.paginate_queryset(results)
        if page is not None:
            return self.get_paginated_response(page)

        return Response(results)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # 清除cache中的etag
        cache.delete("collectors_etag")

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
