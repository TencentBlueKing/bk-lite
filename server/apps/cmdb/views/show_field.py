from rest_framework import viewsets
from rest_framework import status
from rest_framework.decorators import action

from apps.cmdb.models.show_field import ShowField
from apps.core.utils.web_utils import WebUtils


class ShowFieldViewSet(viewsets.ViewSet):
    @action(methods=["post"], detail=False, url_path="(?P<model_id>.+?)/settings")
    def create_or_update(self, request, model_id):
        show_fields = request.data.get("show_fields")
        if not isinstance(show_fields, list):
            return WebUtils.response_error(
                error_message="show_fields 必须是数组",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        data = dict(
            model_id=model_id,
            created_by=request.user.username,
            show_fields=show_fields,
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
