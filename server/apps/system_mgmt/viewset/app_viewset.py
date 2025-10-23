from django.http import JsonResponse

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.system_mgmt.models import App
from apps.system_mgmt.serializers.app_serializer import AppSerializer


class AppViewSet(LanguageViewSet):
    queryset = App.objects.all().order_by("name")
    serializer_class = AppSerializer

    @HasPermission("application_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.is_build_in:
            message = self.loader.get("error.cannot_delete_builtin_app") if self.loader else "Cannot delete built-in application"
            return JsonResponse({"result": False, "message": message})
        return super().destroy(request, *args, **kwargs)

    @HasPermission("application_list-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("application_list-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("application_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
