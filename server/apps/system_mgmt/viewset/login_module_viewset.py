from django.http import JsonResponse
from django_celery_beat.models import PeriodicTask

from apps.core.utils.viewset_utils import LanguageViewSet
from apps.system_mgmt.models import Group, LoginModule, User
from apps.system_mgmt.serializers.login_module_serializer import LoginModuleSerializer
from apps.system_mgmt.tasks import sync_user_and_group_by_login_module
from apps.system_mgmt.utils.operation_log_utils import log_operation


class LoginModuleViewSet(LanguageViewSet):
    queryset = LoginModule.objects.all()
    serializer_class = LoginModuleSerializer

    def list(self, request, *args, **kwargs):
        """
        List all login modules.
        """
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        Create a new login module.
        """
        source_type = request.data["source_type"]
        if source_type != "bk_login":
            domain = request.data.get("other_config", {}).get("domain", "")
            if not domain:
                message = (
                    self.loader.get("error.domain_required_for_login_module") if self.loader else "Domain is required for creating a login module."
                )
                return JsonResponse({"result": False, "message": message})
            if LoginModule.objects.filter(name=request.data["name"], source_type=request.data["source_type"]).exists():
                message = (
                    self.loader.get("error.login_module_name_exists")
                    if self.loader
                    else "Login module with this name and source type already exists."
                )
                return JsonResponse({"result": False, "message": message})
            exist_login_module = list(LoginModule.objects.filter(source_type="bk_lite").values_list("other_config", flat=True))
            domain_list = [i.get("domain") for i in exist_login_module]
            if domain in domain_list:
                message = self.loader.get("error.login_module_domain_exists") if self.loader else "Login module with this domain already exists."
                return JsonResponse({"result": False, "message": message})

        response = super().create(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 201:
            module_name = response.data.get("name", "")
            log_operation(request, "create", "login_module", f"新增认证源: {module_name}")

        return response

    def update(self, request, *args, **kwargs):
        """
        Update an existing login module.
        """
        obj = self.get_object()
        if obj.source_type == "bk_lite":
            domain = request.data.get("other_config", {}).get("domain", "")
            if not domain:
                message = (
                    self.loader.get("error.domain_required_for_login_module") if self.loader else "Domain is required for creating a login module."
                )
                return JsonResponse({"result": False, "message": message})
            if LoginModule.objects.filter(name=request.data["name"], source_type=request.data["source_type"]).exclude(id=obj.id).exists():
                message = (
                    self.loader.get("error.login_module_name_exists")
                    if self.loader
                    else "Login module with this name and source type already exists."
                )
                return JsonResponse({"result": False, "message": message})
            exist_login_module = list(LoginModule.objects.filter(source_type="bk_lite").exclude(id=obj.id).values_list("other_config", flat=True))
            domain_list = [i.get("domain") for i in exist_login_module]
            if domain in domain_list:
                message = self.loader.get("error.login_module_domain_exists") if self.loader else "Login module with this domain already exists."
                return JsonResponse({"result": False, "message": message})

        response = super().update(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 200:
            module_name = response.data.get("name", "")
            log_operation(request, "update", "login_module", f"编辑认证源: {module_name}")

        return response

    def destroy(self, request, *args, **kwargs):
        """
        Delete a login module.
        """
        obj = self.get_object()
        module_name = obj.name

        if obj.source_type == "bk_lite":
            domain = obj.other_config.get("domain", "")
            group_name = obj.other_config.get("root_group", "")
            top_group = Group.objects.get(parent_id=0, name=group_name)
            User.objects.filter(domain=domain).delete()
            Group.objects.filter(description=top_group.description).delete()
            task_name = f"sync_user_group_{obj.name}"
            PeriodicTask.objects.filter(name=task_name).delete()

        response = super().destroy(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 204:
            log_operation(request, "delete", "login_module", f"删除认证源: {module_name}")

        return response

    def sync_data(self, request, *args, **kwargs):
        obj = self.get_object()
        sync_user_and_group_by_login_module.delay(obj.id)

        # 记录操作日志
        log_operation(request, "execute", "login_module", f"开启认证源: {obj.name}")

        message = self.loader.get("success.sync_task_initiated") if self.loader else "Sync task has been initiated."
        return JsonResponse({"result": True, "message": message})
