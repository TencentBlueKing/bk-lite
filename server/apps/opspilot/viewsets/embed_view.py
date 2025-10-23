from django_filters import filters
from django_filters.rest_framework import FilterSet

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import EmbedProvider
from apps.opspilot.serializers.embed_serializer import EmbedProviderSerializer


class ObjFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    enabled = filters.CharFilter(method="filter_enabled")

    @staticmethod
    def filter_enabled(qs, field_name, value):
        """查询类型"""
        if not value:
            return qs
        enabled = value == "1"
        return qs.filter(enabled=enabled)


class EmbedProviderViewSet(AuthViewSet):
    serializer_class = EmbedProviderSerializer
    queryset = EmbedProvider.objects.all()
    permission_key = "provider.embed_model"
    filterset_class = ObjFilter

    @HasPermission("provide_list-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        return self.query_by_groups(request, queryset)

    @HasPermission("provide_list-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("provide_list-Setting")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("provide_list-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
