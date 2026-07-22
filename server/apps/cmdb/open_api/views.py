from rest_framework.exceptions import (
    APIException,
    MethodNotAllowed,
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from apps.cmdb.constants.constants import VIEW
from apps.core.exceptions.base_app_exception import BaseAppException

from .auth import CMDBOpenAPIContext
from .errors import CMDBOpenAPIError
from .responses import open_api_error, open_api_success
from .services import CMDBOpenAPIService, serialize_instance


class APISecretRequired(BasePermission):
    def has_permission(self, request, view):
        return bool(getattr(request, "api_pass", False))


class CMDBOpenAPIView(APIView):
    permission_classes = [APISecretRequired]

    def service(self, request):
        return CMDBOpenAPIService(CMDBOpenAPIContext.from_request(request))

    def permission_denied(self, request, message=None, code=None):
        if not getattr(request, "api_pass", False):
            raise CMDBOpenAPIError("cmdb.auth.api_secret_required", "必须使用 API Secret", 403)
        return super().permission_denied(request, message=message, code=code)

    def handle_exception(self, exc):
        if isinstance(exc, CMDBOpenAPIError):
            return open_api_error(exc)
        if isinstance(exc, BaseAppException):
            return open_api_error(
                CMDBOpenAPIError("cmdb.validation.failed", exc.message, 400)
            )
        if isinstance(exc, NotAuthenticated):
            return open_api_error(
                CMDBOpenAPIError("cmdb.auth.authentication_required", "需要认证", exc.status_code)
            )
        if isinstance(exc, PermissionDenied):
            return open_api_error(CMDBOpenAPIError("cmdb.permission.denied", "权限不足", exc.status_code))
        if isinstance(exc, MethodNotAllowed):
            return open_api_error(
                CMDBOpenAPIError("cmdb.request.method_not_allowed", "请求方法不被允许", exc.status_code)
            )
        if isinstance(exc, ValidationError):
            return open_api_error(
                CMDBOpenAPIError("cmdb.validation.failed", "请求参数非法", exc.status_code)
            )
        if isinstance(exc, APIException):
            return open_api_error(CMDBOpenAPIError("cmdb.request.failed", "请求处理失败", exc.status_code))
        return super().handle_exception(exc)


class OpenClassificationListView(CMDBOpenAPIView):
    def get(self, request):
        return open_api_success(self.service(request).list_classifications())


class OpenModelListView(CMDBOpenAPIView):
    def get(self, request):
        return open_api_success(self.service(request).list_models())


class OpenModelDetailView(CMDBOpenAPIView):
    def get(self, request, model_id):
        return open_api_success(self.service(request).get_model(model_id))


class OpenModelAttrsView(CMDBOpenAPIView):
    def get(self, request, model_id):
        return open_api_success(self.service(request).get_model_attrs(model_id))


class OpenModelAssociationsView(CMDBOpenAPIView):
    def get(self, request, model_id):
        return open_api_success(self.service(request).get_model_associations(model_id))


class OpenInstanceCollectionView(CMDBOpenAPIView):
    def get(self, request, model_id):
        return open_api_success(self.service(request).list_instances(model_id, request.query_params))

    def post(self, request, model_id):
        return open_api_success(
            self.service(request).create_instance(model_id, request.data),
            status_code=201,
        )


class OpenInstanceDetailView(CMDBOpenAPIView):
    def get(self, request, model_id, inst_id):
        service = self.service(request)
        service.context.require_feature("asset_info-View")
        return open_api_success(serialize_instance(service._get_instance(model_id, inst_id, VIEW)))

    def patch(self, request, model_id, inst_id):
        return open_api_success(self.service(request).update_instance(model_id, inst_id, request.data))

    def delete(self, request, model_id, inst_id):
        return open_api_success(self.service(request).delete_instance(model_id, inst_id))


class OpenInstanceAssociationsView(CMDBOpenAPIView):
    def get(self, request, model_id, inst_id):
        return open_api_success(self.service(request).list_instance_associations(model_id, inst_id))

    def post(self, request, model_id, inst_id):
        return open_api_success(
            self.service(request).create_instance_association(model_id, inst_id, request.data),
            status_code=201,
        )


class OpenInstanceAssociationDetailView(CMDBOpenAPIView):
    def delete(self, request, model_id, inst_id, association_id):
        return open_api_success(
            self.service(request).delete_instance_association(model_id, inst_id, association_id)
        )


class OpenBatchCreateView(CMDBOpenAPIView):
    def post(self, request, model_id):
        return open_api_success(
            self.service(request).batch_create_instances(model_id, request.data),
            status_code=201,
        )


class OpenBatchUpdateView(CMDBOpenAPIView):
    def post(self, request, model_id):
        return open_api_success(self.service(request).batch_update_instances(model_id, request.data))


class OpenBatchDeleteView(CMDBOpenAPIView):
    def post(self, request, model_id):
        return open_api_success(self.service(request).batch_delete_instances(model_id, request.data))
