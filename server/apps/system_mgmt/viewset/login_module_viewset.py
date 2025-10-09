from django.http import JsonResponse
from django.utils.translation import gettext as _
from django_celery_beat.models import PeriodicTask
from rest_framework import viewsets

from apps.system_mgmt.models import Group, LoginModule, User
from apps.system_mgmt.serializers.login_module_serializer import LoginModuleSerializer
from apps.system_mgmt.tasks import sync_user_and_group_by_login_module


class LoginModuleViewSet(viewsets.ModelViewSet):
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
                return JsonResponse({"result": False, "message": _("Domain is required for creating a login module.")})
            if LoginModule.objects.filter(name=request.data["name"], source_type=request.data["source_type"]).exists():
                return JsonResponse({"result": False, "message": _("Login module with this name and source type already exists.")})
            exist_login_module = list(LoginModule.objects.filter(source_type="bk_lite").values_list("other_config", flat=True))
            domain_list = [i.get("domain") for i in exist_login_module]
            if domain in domain_list:
                return JsonResponse({"result": False, "message": _("Login module with this domain already exists.")})
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """
        Update an existing login module.
        """
        obj = self.get_object()
        if obj.source_type == "bk_lite":
            domain = request.data.get("other_config", {}).get("domain", "")
            if not domain:
                return JsonResponse({"result": False, "message": _("Domain is required for creating a login module.")})
            if LoginModule.objects.filter(name=request.data["name"], source_type=request.data["source_type"]).exclude(id=obj.id).exists():
                return JsonResponse({"result": False, "message": _("Login module with this name and source type already exists.")})
            exist_login_module = list(LoginModule.objects.filter(source_type="bk_lite").exclude(id=obj.id).values_list("other_config", flat=True))
            domain_list = [i.get("domain") for i in exist_login_module]
            if domain in domain_list:
                return JsonResponse({"result": False, "message": _("Login module with this domain already exists.")})
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Delete a login module.
        """
        obj = self.get_object()
        if obj.source_type == "bk_lite":
            domain = obj.other_config.get("domain", "")
            group_name = obj.other_config.get("root_group", "")
            top_group = Group.objects.get(parent_id=0, name=group_name)
            User.objects.filter(domain=domain).delete()
            Group.objects.filter(description=top_group.description).delete()
            task_name = f"sync_user_group_{obj.name}"
            PeriodicTask.objects.filter(name=task_name).delete()

        return super().destroy(request, *args, **kwargs)

    def sync_data(self, request, *args, **kwargs):
        obj = self.get_object()
        sync_user_and_group_by_login_module.delay(obj.id)
        return JsonResponse({"result": True, "message": _("Sync task has been initiated.")})
