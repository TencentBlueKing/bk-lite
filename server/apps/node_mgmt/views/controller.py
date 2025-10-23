from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet

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
        return super().list(request, *args, **kwargs)
