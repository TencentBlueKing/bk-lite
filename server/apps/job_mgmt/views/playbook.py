"""Playbook视图"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.filters.playbook import PlaybookFilter
from apps.job_mgmt.models import Playbook
from apps.job_mgmt.serializers.playbook import PlaybookBatchDeleteSerializer, PlaybookCreateSerializer, PlaybookSerializer, PlaybookUpdateSerializer


class PlaybookViewSet(AuthViewSet):
    """Playbook视图集"""

    queryset = Playbook.objects.all()
    serializer_class = PlaybookSerializer
    filterset_class = PlaybookFilter
    search_fields = ["name", "description"]
    ORGANIZATION_FIELD = "team"

    def get_serializer_class(self):
        if self.action == "create":
            return PlaybookCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return PlaybookUpdateSerializer
        elif self.action == "batch_delete":
            return PlaybookBatchDeleteSerializer
        return PlaybookSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # 返回完整的对象信息
        instance = Playbook.objects.get(pk=serializer.instance.pk)
        response_serializer = PlaybookSerializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def batch_delete(self, request):
        """批量删除Playbook"""
        serializer = PlaybookBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]

        # 只删除当前用户有权限的Playbook
        queryset = self.filter_queryset(self.get_queryset())
        deleted_count, _ = queryset.filter(id__in=ids).delete()

        return Response({"deleted_count": deleted_count}, status=status.HTTP_200_OK)
