from rest_framework import viewsets

from apps.cmdb.services.classification import ClassificationManage
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils


class ClassificationViewSet(viewsets.ViewSet):
    @HasPermission("model_management-Add Group")
    def create(self, request):
        result = ClassificationManage.create_model_classification(request.data)
        return WebUtils.response_success(result)

    @HasPermission("model_management-View")
    def list(self, request):
        result = ClassificationManage.search_model_classification(request.user.locale)
        return WebUtils.response_success(result)

    @HasPermission("model_management-Delete Group")
    def destroy(self, request, pk: str):
        ClassificationManage.check_classification_is_used(pk)
        classification_info = ClassificationManage.search_model_classification_info(pk)
        ClassificationManage.delete_model_classification(classification_info.get("_id"))
        return WebUtils.response_success()

    @HasPermission("model_management-Edit Group")
    def update(self, request, pk: str):
        classification_info = ClassificationManage.search_model_classification_info(pk)
        data = ClassificationManage.update_model_classification(classification_info.get("_id"), request.data)
        return WebUtils.response_success(data)
