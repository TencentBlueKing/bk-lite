from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets

from apps.cmdb.services.classification import ClassificationManage
from apps.core.decorators.api_perminssion import HasRole
from apps.core.utils.web_utils import WebUtils


class ClassificationViewSet(viewsets.ViewSet):
    @swagger_auto_schema(
        operation_id="classification_create",
        operation_description="创建模型分类",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "classification_id": openapi.Schema(type=openapi.TYPE_STRING, description="模型分类ID"),
                "classification_name": openapi.Schema(type=openapi.TYPE_STRING, description="模型分类名称"),
            },
            required=["classification_id", "classification_name"],
        ),
    )
    @HasRole(["admin"])
    def create(self, request):
        result = ClassificationManage.create_model_classification(request.data)
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="classification_search",
        operation_description="查询模型分类",
    )
    def list(self, request):
        result = ClassificationManage.search_model_classification(request.user.locale)
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="classification_delete",
        operation_description="删除模型分类",
        manual_parameters=[openapi.Parameter("id", openapi.IN_PATH, description="模型分类ID", type=openapi.TYPE_STRING)],
    )
    @HasRole(["admin"])
    def destroy(self, request, pk: str):
        ClassificationManage.check_classification_is_used(pk)
        classification_info = ClassificationManage.search_model_classification_info(pk)
        ClassificationManage.delete_model_classification(classification_info.get("_id"))
        return WebUtils.response_success()

    @swagger_auto_schema(
        operation_id="classification_update",
        operation_description="更改模型分类信息",
        manual_parameters=[openapi.Parameter("id", openapi.IN_PATH, description="模型分类ID", type=openapi.TYPE_STRING)],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "classification_name": openapi.Schema(type=openapi.TYPE_STRING, description="模型分类名称"),
            },
        ),
    )
    @HasRole(["admin"])
    def update(self, request, pk: str):
        classification_info = ClassificationManage.search_model_classification_info(pk)
        data = ClassificationManage.update_model_classification(classification_info.get("_id"), request.data)
        return WebUtils.response_success(data)
