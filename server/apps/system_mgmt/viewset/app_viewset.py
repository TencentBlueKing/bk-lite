from django.db.models import Q
from django.http import JsonResponse

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.permission_cache import clear_users_permission_cache
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.system_mgmt.models import App, Group, Role, User
from apps.system_mgmt.serializers.app_serializer import AppSerializer
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.system_mgmt.utils.operation_log_utils import log_operation


class AppViewSet(LanguageViewSet):
    queryset = App.objects.all().order_by("name")
    serializer_class = AppSerializer

    @staticmethod
    def _get_users_affected_by_roles(role_ids):
        if not role_ids:
            return User.objects.none()
        query = Q()
        for role_id in role_ids:
            query |= Q(role_list__contains=int(role_id))
        role_group_ids = Group.objects.filter(roles__id__in=role_ids).values_list("id", flat=True)
        for group_id in GroupUtils.get_group_with_descendants(role_group_ids):
            query |= Q(group_list__contains=int(group_id))
        return User.objects.filter(query).distinct()

    @HasPermission("application_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.is_build_in:
            message = self.loader.get("error.cannot_delete_builtin_app") if self.loader else "Cannot delete built-in application"
            return JsonResponse({"result": False, "message": message})

        app_name = obj.name
        role_ids = list(Role.objects.filter(app=app_name).values_list("id", flat=True))
        affected_users = list(self._get_users_affected_by_roles(role_ids).values("username", "domain"))
        Role.objects.filter(app=app_name).delete()
        response = super().destroy(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 204:
            if affected_users:
                clear_users_permission_cache(affected_users)
            log_operation(request, "delete", "system-manager", f"删除应用: {app_name}")

        return response

    @HasPermission("application_list-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        if response.status_code == 201:
            app_name = response.data.get("name", "")
            Role.objects.get_or_create(name="user", app=app_name)
            log_operation(request, "create", "system-manager", f"新增应用: {app_name}")

        return response

    @HasPermission("application_list-Edit")
    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        old_name = obj.name
        role_ids = list(Role.objects.filter(app=old_name).values_list("id", flat=True))
        affected_users = list(self._get_users_affected_by_roles(role_ids).values("username", "domain"))
        response = super().update(request, *args, **kwargs)

        if response.status_code == 200:
            new_name = response.data.get("name", "")
            if old_name != new_name:
                Role.objects.filter(app=old_name).update(app=new_name)
                if affected_users:
                    clear_users_permission_cache(affected_users)
            log_operation(request, "update", "system-manager", f"编辑应用: {new_name}")

        return response

    @HasPermission("application_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
