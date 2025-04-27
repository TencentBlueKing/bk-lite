from rest_framework import viewsets
from rest_framework.decorators import action

from apps.cmdb.models.show_field import ShowField
from apps.core.utils.web_utils import WebUtils


class ShowFieldViewSet(viewsets.ViewSet):
    @action(methods=["post"], detail=False, url_path="(?P<model_id>.+?)/settings")
    def create_or_update(self, request, model_id):
        data = dict(
            model_id=model_id,
            created_by=request.user.username,
            show_fields=request.data["show_fields"],
        )
        ShowField.objects.update_or_create(
            defaults=data,
            model_id=model_id,
            created_by=request.user.username,
        )
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="(?P<model_id>.+?)/detail")
    def get_info(self, request, model_id):
        obj = ShowField.objects.filter(created_by=request.user.username, model_id=model_id).first()
        result = dict(model_id=obj.model_id, show_fields=obj.show_fields) if obj else None
        return WebUtils.response_success(result)
