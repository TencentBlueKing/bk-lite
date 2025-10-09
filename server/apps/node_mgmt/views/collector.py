from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.node_mgmt.filters.collector import CollectorFilter
from apps.node_mgmt.models.sidecar import Collector
from apps.node_mgmt.serializers.collector import CollectorSerializer
from django.core.cache import cache


class CollectorViewSet(ModelViewSet):
    queryset = Collector.objects.all()
    serializer_class = CollectorSerializer
    filterset_class = CollectorFilter

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

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
