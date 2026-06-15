from rest_framework import status, viewsets
from rest_framework.decorators import action

from apps.cmdb.custom_reporting.extensions import get_custom_reporting_extension
from apps.cmdb.serializers.custom_reporting import CustomReportingCreateSerializer, CustomReportingUpdateSerializer
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.core.utils.open_base import OpenAPIViewSet
from apps.core.utils.web_utils import WebUtils


class CustomReportingTaskViewSet(CmdbPermissionMixin, viewsets.ViewSet):
    def list(self, request):
        return WebUtils.response_success(get_custom_reporting_extension().list_tasks(request, request.query_params.dict()))

    def create(self, request):
        ser = CustomReportingCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return WebUtils.response_success(get_custom_reporting_extension().create_task(request, ser.validated_data))

    def retrieve(self, request, pk=None):
        return WebUtils.response_success(get_custom_reporting_extension().get_task(request, pk))

    def update(self, request, pk=None):
        ser = CustomReportingUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return WebUtils.response_success(get_custom_reporting_extension().update_task(request, pk, ser.validated_data))

    def destroy(self, request, pk=None):
        get_custom_reporting_extension().delete_task(request, pk)
        return WebUtils.response_success({})

    @action(detail=True, methods=["get"], url_path="batch_activity")
    def batch_activity(self, request, pk=None):
        return WebUtils.response_success(get_custom_reporting_extension().get_batch_activity(request, pk))

    @action(detail=True, methods=["get"], url_path="onboarding_document")
    def onboarding_document(self, request, pk=None):
        return WebUtils.response_success(get_custom_reporting_extension().get_onboarding_document(request, pk))

    @action(detail=True, methods=["post"], url_path="issue_credential")
    def issue_credential(self, request, pk=None):
        return WebUtils.response_success(get_custom_reporting_extension().issue_credential(request, pk, request.data))

    @action(detail=True, methods=["post"], url_path="rotate_credential")
    def rotate_credential(self, request, pk=None):
        credential_id = request.data.get("credential_id")
        if not credential_id:
            return WebUtils.response_error(error_message="credential_id is required", status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(get_custom_reporting_extension().rotate_credential(request, pk, credential_id))

    @action(detail=True, methods=["post"], url_path="revoke_credential")
    def revoke_credential(self, request, pk=None):
        credential_id = request.data.get("credential_id")
        if not credential_id:
            return WebUtils.response_error(error_message="credential_id is required", status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(get_custom_reporting_extension().revoke_credential(request, pk, credential_id))

    @action(detail=True, methods=["post"], url_path=r"reviews/(?P<review_id>[^/]+)/approve")
    def approve_review(self, request, pk=None, review_id=None):
        return WebUtils.response_success(get_custom_reporting_extension().approve_cleanup_review(request, pk, review_id))

    @action(detail=True, methods=["post"], url_path=r"reviews/(?P<review_id>[^/]+)/reject")
    def reject_review(self, request, pk=None, review_id=None):
        return WebUtils.response_success(get_custom_reporting_extension().reject_cleanup_review(request, pk, review_id))


class CustomReportingIngestViewSet(OpenAPIViewSet):
    authentication_classes = []

    def create(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        token = auth[7:] if auth.startswith("Bearer ") else None
        return WebUtils.response_success(get_custom_reporting_extension().ingest(request, token, request.data))
